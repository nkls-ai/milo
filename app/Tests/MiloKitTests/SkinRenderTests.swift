import AppKit
import SwiftUI
import Testing
@testable import MiloKit

/// Renders every skin's key frames on a light and a dark wallpaper into PNGs, plus close-ups, a line-up and
/// the skins at helper size: `MILO_RENDER_DIR=/tmp/milo-skins swift test --filter SkinRender`.
/// `MILO_SKINS=dragon,kit` renders only those.
@Suite(.enabled(if: ProcessInfo.processInfo.environment["MILO_RENDER_DIR"] != nil))
@MainActor
struct SkinRenderTests {
    let dir = URL(fileURLWithPath: ProcessInfo.processInfo.environment["MILO_RENDER_DIR"] ?? "/tmp")
    let skins: [CharacterStyle] = {
        let wanted = ProcessInfo.processInfo.environment["MILO_SKINS"]?.split(separator: ",").map(String.init) ?? []
        return CharacterStyle.allCases.filter { wanted.isEmpty || wanted.contains($0.rawValue) }
    }()

    struct Frame {
        var name: String
        var state: MiloState = .idle
        var emotion: Emotion = .neutral
        var asleep = false
        var level = 0.0
        var pose = LifePose()
        var flight: Flight = .perched
        var time = 1.3

        var input: FigureInput {
            FigureInput(state: state, emotion: emotion, asleep: asleep, level: level, pose: pose, flight: flight)
        }
    }

    static let frames: [Frame] = [
        Frame(name: "idle"),
        Frame(name: "glance", pose: LifePose(gaze: CGVector(dx: -0.8, dy: 0.3))),
        Frame(name: "blink", pose: LifePose(blink: true)),
        Frame(name: "listening", state: .listening, level: 0.5,
              pose: LifePose(gaze: CGVector(dx: -0.15, dy: -0.1), lean: -1, tilt: -4)),
        Frame(name: "dictating", state: .dictating, level: 0.4),
        Frame(name: "thinking", state: .thinking, emotion: .thinking, pose: LifePose(gaze: CGVector(dx: 0.7, dy: -0.75))),
        Frame(name: "thinking later", state: .thinking, emotion: .thinking,
              pose: LifePose(gaze: CGVector(dx: -0.7, dy: -0.75)), time: 2.2),
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
    ]

    @Test func renderKeyFrames() throws {
        _ = NSApplication.shared
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        for skin in skins {
            for dark in [false, true] {
                try save(Sheet(skin: skin, frames: Self.frames, dark: dark), name: "\(skin)-\(dark ? "dark" : "light")", scale: 2)
            }
            for frame in Self.frames where ["idle", "speaking", "sleepy", "pointing", "thinking"].contains(frame.name) {
                try save(Cell(skin: skin, frame: frame, dark: false, label: false), name: "\(skin)-zoom-\(frame.name)", scale: 4)
            }
            try save(Corner(skin: skin, dark: false), name: "\(skin)-corner-light", scale: 2)
            try save(Corner(skin: skin, dark: true), name: "\(skin)-corner-dark", scale: 2)
        }
        try save(LineUp(skins: skins, dark: false), name: "skins-lineup-light", scale: 2)
        try save(LineUp(skins: skins, dark: true), name: "skins-lineup-dark", scale: 2)
        try save(Small(skins: skins), name: "skins-small", scale: 2)
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
        var skin: CharacterStyle
        var frame: Frame
        var dark: Bool
        var label = true

        var body: some View {
            VStack(spacing: 2) {
                CharacterFigure(for: skin, input: frame.input, time: frame.time)
                    .frame(width: 132, height: 132)
                if label {
                    Text(frame.name).font(.system(size: 11, weight: .medium))
                        .foregroundStyle(dark ? Color.white.opacity(0.7) : Color.black.opacity(0.6))
                }
            }
            .padding(6)
            .background(Wallpaper(dark: dark))
            .environment(\.colorScheme, dark ? .dark : .light)
        }
    }

    struct Sheet: View {
        var skin: CharacterStyle
        var frames: [Frame]
        var dark: Bool

        var body: some View {
            let rows = stride(from: 0, to: frames.count, by: 6).map { Array(frames[$0..<min($0 + 6, frames.count)]) }
            VStack(spacing: 0) {
                ForEach(rows.indices, id: \.self) { r in
                    HStack(spacing: 0) {
                        ForEach(rows[r].indices, id: \.self) { i in Cell(skin: skin, frame: rows[r][i], dark: dark) }
                    }
                }
            }
        }
    }

    /// The skin at real size in the corner of a wallpaper.
    struct Corner: View {
        var skin: CharacterStyle
        var dark: Bool

        var body: some View {
            ZStack(alignment: .bottomTrailing) {
                Wallpaper(dark: dark)
                CharacterFigure(for: skin, pose: LifePose(gaze: CGVector(dx: -0.3, dy: -0.4)), time: 0.4)
                    .frame(width: 132, height: 132)
                    .padding(.trailing, 8)
                    .padding(12)
            }
            .frame(width: 420, height: 300)
            .environment(\.colorScheme, dark ? .dark : .light)
        }
    }

    /// Every skin side by side, idle and happy.
    struct LineUp: View {
        var skins: [CharacterStyle]
        var dark: Bool

        var body: some View {
            VStack(spacing: 0) {
                ForEach([Emotion.neutral, .happy, .sleepy], id: \.self) { emotion in
                    HStack(spacing: 0) {
                        ForEach(skins, id: \.self) { skin in
                            Cell(skin: skin, frame: Frame(name: skin.rawValue, emotion: emotion == .sleepy ? .neutral : emotion,
                                                          asleep: emotion == .sleepy),
                                 dark: dark)
                        }
                    }
                }
            }
        }
    }

    /// The skins at helper size, 36 pt, idle, thinking and pointing, on both wallpapers.
    struct Small: View {
        var skins: [CharacterStyle]

        var body: some View {
            VStack(spacing: 0) {
                ForEach([false, true], id: \.self) { dark in
                    HStack(spacing: 10) {
                        ForEach(skins, id: \.self) { skin in
                            HStack(spacing: 4) {
                                CharacterFigure(for: skin, size: 36, time: 1)
                                CharacterFigure(for: skin, state: .thinking, emotion: .thinking, size: 36, time: 1)
                                CharacterFigure(for: skin, flight: .pointing(toward: CGVector(dx: -0.9, dy: -0.3)), size: 36,
                                                time: 1)
                            }
                        }
                    }
                    .padding(10)
                    .background(Wallpaper(dark: dark))
                    .environment(\.colorScheme, dark ? .dark : .light)
                }
            }
        }
    }
}
