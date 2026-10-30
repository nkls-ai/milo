import AppKit
import SwiftUI
import Testing
@testable import MiloKit

/// Renders Pip's key frames on a light and a dark wallpaper, at real size and at 3x, into PNGs:
/// `MILO_RENDER_DIR=/tmp/milo-pip swift test --filter PipRender`.
@Suite(.enabled(if: ProcessInfo.processInfo.environment["MILO_RENDER_DIR"] != nil))
@MainActor
struct PipRenderTests {
    let dir = URL(fileURLWithPath: ProcessInfo.processInfo.environment["MILO_RENDER_DIR"] ?? "/tmp")

    struct Frame {
        var name: String
        var state: MiloState = .idle
        var emotion: Emotion = .neutral
        var asleep = false
        var level = 0.0
        var pose = LifePose()
        var flight: Flight = .perched
        var character: CharacterStyle = .pip
    }

    static let frames: [Frame] = [
        Frame(name: "idle"),
        Frame(name: "glance", pose: LifePose(gaze: CGVector(dx: -0.8, dy: 0.3))),
        Frame(name: "blink", pose: LifePose(blink: true)),
        Frame(name: "listening", state: .listening, level: 0.5,
              pose: LifePose(gaze: CGVector(dx: -0.15, dy: -0.1), lean: -1, tilt: -4)),
        Frame(name: "dictating", state: .dictating, level: 0.4),
        Frame(name: "thinking", state: .thinking, emotion: .thinking, pose: LifePose(gaze: CGVector(dx: 0.7, dy: -0.75))),
        Frame(name: "speaking", state: .speaking, level: 0.7),
        Frame(name: "happy", emotion: .happy),
        Frame(name: "excited", emotion: .excited),
        Frame(name: "concerned", emotion: .concerned),
        Frame(name: "sad", emotion: .sad),
        Frame(name: "confused", emotion: .confused),
        Frame(name: "sleepy", asleep: true),
        Frame(name: "yawn", pose: LifePose(yawn: true)),
        Frame(name: "flying", flight: .flying(heading: CGVector(dx: -0.8, dy: -0.6))),
        Frame(name: "pointing", flight: .pointing(toward: CGVector(dx: -0.97, dy: -0.24))),
        Frame(name: "pointing right", flight: .pointing(toward: CGVector(dx: 0.9, dy: -0.4))),
        Frame(name: "classic", character: .classic),
    ]

    @Test func renderKeyFrames() throws {
        _ = NSApplication.shared
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        for dark in [false, true] {
            let sheet = Sheet(frames: Self.frames, dark: dark)
            try save(sheet, name: "pip-\(dark ? "dark" : "light")", scale: 2)
        }
        for frame in Self.frames where ["idle", "speaking", "sleepy", "pointing"].contains(frame.name) {
            try save(Cell(frame: frame, dark: false, label: false), name: "pip-zoom-\(frame.name)", scale: 4)
        }
        try save(Corner(dark: false), name: "pip-corner-light", scale: 2)
        try save(Corner(dark: true), name: "pip-corner-dark", scale: 2)
    }

    private func save(_ view: some View, name: String, scale: CGFloat) throws {
        let renderer = ImageRenderer(content: view)
        renderer.scale = scale
        let image = try #require(renderer.cgImage)
        let png = try #require(NSBitmapImageRep(cgImage: image).representation(using: .png, properties: [:]))
        try png.write(to: dir.appendingPathComponent("\(name).png"))
    }

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

    struct Cell: View {
        var frame: Frame
        var dark: Bool
        var label = true

        var body: some View {
            VStack(spacing: 2) {
                figure.frame(width: 132, height: 132)
                if label {
                    Text(frame.name).font(.system(size: 11, weight: .medium))
                        .foregroundStyle(dark ? Color.white.opacity(0.7) : Color.black.opacity(0.6))
                }
            }
            .padding(6)
            .background(Wallpaper(dark: dark))
        }

        @ViewBuilder private var figure: some View {
            if frame.character == .classic {
                CharacterFigure(state: frame.state, emotion: frame.emotion, asleep: frame.asleep, level: frame.level,
                                connected: true, pose: frame.pose, floating: false)
            } else {
                PipFigure(state: frame.state, emotion: frame.emotion, asleep: frame.asleep, level: frame.level,
                          connected: true, pose: frame.pose, flight: frame.flight, time: 1.3)
            }
        }
    }

    struct Sheet: View {
        var frames: [Frame]
        var dark: Bool

        var body: some View {
            let rows = stride(from: 0, to: frames.count, by: 6).map { Array(frames[$0..<min($0 + 6, frames.count)]) }
            VStack(spacing: 0) {
                ForEach(rows.indices, id: \.self) { r in
                    HStack(spacing: 0) {
                        ForEach(rows[r].indices, id: \.self) { i in Cell(frame: rows[r][i], dark: dark) }
                    }
                }
            }
        }
    }

    /// Pip at real size in the corner of a wallpaper.
    struct Corner: View {
        var dark: Bool

        var body: some View {
            ZStack(alignment: .bottomTrailing) {
                Wallpaper(dark: dark)
                VStack(alignment: .trailing, spacing: 6) {
                    PipFigure(state: .idle, emotion: .neutral, asleep: false, level: 0, connected: true,
                              pose: LifePose(gaze: CGVector(dx: -0.3, dy: -0.4)), time: 0.4)
                        .frame(width: 132, height: 132)
                        .padding(.trailing, 8)
                }
                .padding(12)
            }
            .frame(width: 420, height: 300)
            .environment(\.colorScheme, dark ? .dark : .light)
        }
    }
}
