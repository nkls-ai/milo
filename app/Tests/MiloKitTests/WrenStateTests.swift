import AppKit
import SwiftUI
import Testing
@testable import MiloKit

/// A test wallpaper behind overlay renders: a soft light desktop or a dark one.
struct Wallpaper: View {
    var dark: Bool
    var body: some View {
        if dark {
            LinearGradient(colors: [Color(red: 0.10, green: 0.11, blue: 0.20), Color(red: 0.20, green: 0.16, blue: 0.30)],
                           startPoint: .topLeading, endPoint: .bottomTrailing)
        } else {
            LinearGradient(colors: [Color(red: 0.91, green: 0.93, blue: 0.97), Color(red: 0.85, green: 0.88, blue: 0.94),
                                    Color(red: 0.98, green: 0.88, blue: 0.82)],
                           startPoint: .topLeading, endPoint: .bottomTrailing)
        }
    }
}

/// Every state Milo can be in, as the app draws him, on light and dark wallpaper and at helper size:
/// `MILO_RENDER_DIR=/tmp/milo-wren swift test --filter WrenStateTests`.
@Suite(.enabled(if: ProcessInfo.processInfo.environment["MILO_RENDER_DIR"] != nil))
@MainActor
struct WrenStateTests {
    let dir = URL(fileURLWithPath: ProcessInfo.processInfo.environment["MILO_RENDER_DIR"] ?? "/tmp")

    static let states: [(String, FigureInput)] = [
        ("idle", FigureInput()),
        ("blink", FigureInput(pose: LifePose(blink: true))),
        ("glance", FigureInput(pose: LifePose(gaze: CGVector(dx: -0.8, dy: 0.3)))),
        ("listening", FigureInput(state: .listening, level: 0.5, pose: LifePose(gaze: CGVector(dx: -0.15, dy: -0.1), lean: -1, tilt: -4))),
        ("dictating", FigureInput(state: .dictating, level: 0.4)),
        ("thinking", FigureInput(state: .thinking, emotion: .thinking, pose: LifePose(gaze: CGVector(dx: 0.7, dy: -0.75)))),
        ("speaking", FigureInput(state: .speaking, level: 0.7)),
        ("working", FigureInput(flight: .pointing(toward: CGVector(dx: -0.6, dy: 0.8)), working: true)),
        ("asking", FigureInput(asking: true)),
        ("happy", FigureInput(emotion: .happy)),
        ("excited", FigureInput(emotion: .excited)),
        ("concerned", FigureInput(emotion: .concerned)),
        ("sad", FigureInput(emotion: .sad)),
        ("confused", FigureInput(emotion: .confused)),
        ("asleep", FigureInput(asleep: true)),
        ("yawn", FigureInput(pose: LifePose(yawn: true))),
        ("flying", FigureInput(flight: .flying(heading: CGVector(dx: -0.8, dy: -0.6)))),
        ("pointing", FigureInput(flight: .pointing(toward: CGVector(dx: -0.97, dy: -0.24)))),
        ("pointing right", FigureInput(flight: .pointing(toward: CGVector(dx: 0.9, dy: -0.4)))),
        ("offline", FigureInput(connected: false)),
    ]

    @Test func renderEveryState() throws {
        _ = NSApplication.shared
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        for dark in [false, true] {
            try save(Sheet(dark: dark, size: 120), name: "wren-states-\(dark ? "dark" : "light")")
        }
        try save(Sheet(dark: false, size: 40), name: "wren-states-helper")
        for pixels in [16, 32, 128, 256, 512, 1024] {
            let image = try #require(WrenIcon.appIcon(pixels: pixels))
            try write(image, "wren-icon-\(pixels)")
        }
        // the silhouette large, to judge its shape
        let big = try #require(CGContext(data: nil, width: 288, height: 288, bitsPerComponent: 8, bytesPerRow: 0,
                                         space: CGColorSpace(name: CGColorSpace.sRGB)!,
                                         bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue))
        big.setFillColor(CGColor(gray: 0.93, alpha: 1))
        big.fill(CGRect(x: 0, y: 0, width: 288, height: 288))
        big.translateBy(x: 0, y: 288)
        big.scaleBy(x: 1, y: -1)
        WrenIcon.silhouette(big, in: CGRect(x: 16, y: 16, width: 256, height: 256))
        try write(try #require(big.makeImage()), "wren-menubar-large")
        let bar = WrenIcon.menuBar
        for (name, color) in [("light", NSColor.black), ("dark", NSColor.white)] {
            let image = NSImage(size: NSSize(width: 18 * 4, height: 18 * 4), flipped: false) { rect in
                (name == "light" ? NSColor(white: 0.93, alpha: 1) : NSColor(white: 0.16, alpha: 1)).setFill()
                rect.fill()
                color.set()
                let tinted = bar.copy() as! NSImage
                tinted.lockFocus()
                color.set()
                NSRect(origin: .zero, size: tinted.size).fill(using: .sourceAtop)
                tinted.unlockFocus()
                tinted.draw(in: rect.insetBy(dx: 8, dy: 8))
                return true
            }
            let cg = try #require(image.cgImage(forProposedRect: nil, context: nil, hints: nil))
            try write(cg, "wren-menubar-\(name)")
        }
    }

    struct Sheet: View {
        var dark: Bool
        var size: CGFloat

        var body: some View {
            let columns = Array(repeating: GridItem(.fixed(size + 24), spacing: 6), count: 5)
            LazyVGrid(columns: columns, spacing: 8) {
                ForEach(WrenStateTests.states, id: \.0) { name, input in
                    VStack(spacing: 2) {
                        CharacterFigure(input: input, size: size, time: 0)
                        Text(name).font(.system(size: 10, weight: .medium, design: .rounded))
                            .foregroundStyle(dark ? Color.white.opacity(0.7) : Color.black.opacity(0.6))
                    }
                }
            }
            .padding(14)
            .background(Wallpaper(dark: dark))
            .environment(\.colorScheme, dark ? .dark : .light)
        }
    }

    private func save(_ view: some View, name: String) throws {
        let renderer = ImageRenderer(content: view)
        renderer.scale = 2
        let image = try #require(renderer.cgImage)
        try write(image, name)
    }

    private func write(_ image: CGImage, _ name: String) throws {
        let png = try #require(NSBitmapImageRep(cgImage: image).representation(using: .png, properties: [:]))
        try png.write(to: dir.appendingPathComponent("\(name).png"))
    }
}
