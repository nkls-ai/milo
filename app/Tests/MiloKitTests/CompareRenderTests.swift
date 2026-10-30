import AppKit
import SwiftUI
import Testing
@testable import MiloKit

/// Renders Milo in a few states, one PNG each, for side-by-side design comparisons:
/// `MILO_COMPARE_DIR=/tmp/milo-compare MILO_COMPARE_TAG=now swift test --filter CompareRender`.
@Suite(.enabled(if: ProcessInfo.processInfo.environment["MILO_COMPARE_DIR"] != nil))
@MainActor
struct CompareRenderTests {
    let dir = URL(fileURLWithPath: ProcessInfo.processInfo.environment["MILO_COMPARE_DIR"] ?? "/tmp")
    let tag = ProcessInfo.processInfo.environment["MILO_COMPARE_TAG"] ?? "now"

    static let states: [(String, FigureInput)] = [
        ("idle", FigureInput()),
        ("listening", FigureInput(state: .listening, level: 0.5,
                                  pose: LifePose(gaze: CGVector(dx: -0.15, dy: -0.1), lean: -1, tilt: -4))),
        ("thinking", FigureInput(state: .thinking, emotion: .thinking, pose: LifePose(gaze: CGVector(dx: 0.7, dy: -0.75)))),
        ("speaking", FigureInput(state: .speaking, level: 0.7)),
        ("happy", FigureInput(emotion: .happy)),
    ]

    @Test func renderStates() throws {
        _ = NSApplication.shared
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        for dark in [false, true] {
            for (name, input) in Self.states {
                let view = CharacterFigure(input: input, size: 132, time: 1.3)
                    .frame(width: 150, height: 150)
                    .background(Wallpaper(dark: dark))
                    .environment(\.colorScheme, dark ? .dark : .light)
                let renderer = ImageRenderer(content: view)
                renderer.scale = 3
                let image = try #require(renderer.cgImage)
                let png = try #require(NSBitmapImageRep(cgImage: image).representation(using: .png, properties: [:]))
                try png.write(to: dir.appendingPathComponent("\(tag)-\(name)-\(dark ? "dark" : "light").png"))
            }
            // the same states at helper size, where cute has to survive too
            let small = HStack(spacing: 4) {
                ForEach(Self.states, id: \.0) { _, input in CharacterFigure(input: input, size: 36, time: 1.3) }
            }
            .padding(6)
            .background(Wallpaper(dark: dark))
            .environment(\.colorScheme, dark ? .dark : .light)
            let renderer = ImageRenderer(content: small)
            renderer.scale = 3
            let image = try #require(renderer.cgImage)
            let png = try #require(NSBitmapImageRep(cgImage: image).representation(using: .png, properties: [:]))
            try png.write(to: dir.appendingPathComponent("\(tag)-small-\(dark ? "dark" : "light").png"))
        }
    }
}
