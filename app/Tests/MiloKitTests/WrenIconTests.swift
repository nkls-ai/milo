import AppKit
import Testing
@testable import MiloKit

/// Milo's icons come from the rig. `MILO_ICONSET=/tmp/Milo.iconset swift test --filter WrenIconTests` writes the
/// app icon's sizes for `iconutil` (scripts/make-icon.sh does both).
@Suite struct WrenIconTests {
    @Test func theMenuBarIconIsATemplateOfHisShape() throws {
        let icon = WrenIcon.menuBar
        #expect(icon.isTemplate && icon.size == NSSize(width: 18, height: 18))
        let cg = try #require(icon.cgImage(forProposedRect: nil, context: nil, hints: nil))
        #expect(cg.width >= 18)
    }

    @Test func writesTheAppIconSet() throws {
        guard let path = ProcessInfo.processInfo.environment["MILO_ICONSET"] else { return }
        let dir = URL(fileURLWithPath: path)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        for points in [16, 32, 128, 256, 512] {
            for scale in [1, 2] {
                let image = try #require(WrenIcon.appIcon(pixels: points * scale))
                let png = try #require(NSBitmapImageRep(cgImage: image).representation(using: .png, properties: [:]))
                let name = "icon_\(points)x\(points)\(scale == 2 ? "@2x" : "").png"
                try png.write(to: dir.appendingPathComponent(name))
            }
        }
    }
}
