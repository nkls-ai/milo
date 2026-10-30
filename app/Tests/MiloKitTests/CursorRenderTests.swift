import AppKit
import SwiftUI
import Testing
@testable import MiloKit

/// Offscreen pictures of Milo's cursor and the working-window outline, on a mock desktop:
/// `MILO_RENDER_DIR=/tmp/milo-cursor swift test --filter CursorRender`.
@Suite(.enabled(if: ProcessInfo.processInfo.environment["MILO_RENDER_DIR"] != nil))
@MainActor
struct CursorRenderTests {
    let dir = URL(fileURLWithPath: ProcessInfo.processInfo.environment["MILO_RENDER_DIR"] ?? "/tmp")

    @Test func renderCursorStates() throws {
        for (gesture, name) in [(MiloCursorView.Gesture.none, "pointer"), (.click, "click"), (.typing, "typing")] {
            try save(Scene { MiloCursorView(gesture: gesture, presence: 1, clickTick: 1) }, name: "cursor-\(name)")
        }
    }

    @Test func renderWorkingOutline() throws {
        try save(ZStack {
            Mock()
            WorkingOutlineView(onStop: {}).frame(width: 360, height: 240)
        }.frame(width: 440, height: 320), name: "outline")
    }

    private func save(_ view: some View, name: String) throws {
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let renderer = ImageRenderer(content: view)
        renderer.scale = 2
        let image = try #require(renderer.cgImage)
        let png = try #require(NSBitmapImageRep(cgImage: image).representation(using: .png, properties: [:]))
        try png.write(to: dir.appendingPathComponent("\(name).png"))
    }

    private struct Scene<Content: View>: View {
        @ViewBuilder var content: Content
        var body: some View {
            ZStack(alignment: .topLeading) { Mock(); content.offset(x: 40, y: 20) }.frame(width: 180, height: 150)
        }
    }

    private struct Mock: View {
        var body: some View {
            LinearGradient(colors: [Color(red: 0.93, green: 0.95, blue: 0.99), Color(red: 0.86, green: 0.90, blue: 0.96)],
                           startPoint: .top, endPoint: .bottom)
        }
    }
}
