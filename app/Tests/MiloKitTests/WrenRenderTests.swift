import AppKit
import Testing
@testable import MiloKit

/// Renders Milo's rig at hand-set poses into a contact sheet, for checking the drawing itself:
/// `MILO_RENDER_DIR=/tmp/milo-wren swift test --filter WrenRender`.
@Suite(.enabled(if: ProcessInfo.processInfo.environment["MILO_RENDER_DIR"] != nil))
struct WrenRenderTests {
    let dir = URL(fileURLWithPath: ProcessInfo.processInfo.environment["MILO_RENDER_DIR"] ?? "/tmp")

    static let poses: [(String, WrenPose)] = {
        var list: [(String, WrenPose)] = [("rest", .rest)]
        func add(_ name: String, _ change: (inout WrenPose) -> Void) {
            var p = WrenPose.rest
            change(&p)
            list.append((name, p))
        }
        add("blink") { $0.lidL = 1; $0.lidR = 1 }
        add("happy") { $0.lowerL = 1; $0.lowerR = 1; $0.blush = 1; $0.tail = 14; $0.browL = 0.5; $0.browR = 0.5 }
        add("speaking") { $0.beak = 0.8; $0.browL = 0.3; $0.browR = 0.3 }
        add("concerned") { $0.browTiltL = 1; $0.browTiltR = 1; $0.lidL = 0.35; $0.lidR = 0.35; $0.tail = -10 }
        add("look") { $0.gazeX = -1; $0.gazeY = -0.6; $0.headTilt = -8 }
        add("front") { $0.turn = 0 }
        add("right") { $0.turn = 0.35 }
        add("wing up") { $0.wingL = 30; $0.openL = 1 }
        add("flying") { $0.turn = -0.3; $0.fly = 1; $0.lean = -8; $0.wingL = 45; $0.wingR = 45; $0.feet = 0 }
        add("toss") { $0.scarfToss = 1 }
        add("asleep") { $0.lidL = 1; $0.lidR = 1; $0.scarfUp = 1; $0.squash = -0.06; $0.headY = 3; $0.tail = -12 }
        add("squash") { $0.squash = -0.18 }
        add("stretch") { $0.squash = 0.15; $0.lift = 10 }
        add("lean") { $0.lean = -10; $0.headTilt = -12; $0.scarf = 25 }
        add("thinking") { $0.gazeX = 0.8; $0.gazeY = -0.8; $0.browR = 0.8; $0.browTiltL = -0.4; $0.headTilt = 8 }
        return list
    }()

    @Test func renderSheet() throws {
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let cell: CGFloat = 240, cols = 4
        let rows = (Self.poses.count + cols - 1) / cols
        for dark in [false, true] {
            let bg = dark ? WrenColors.rgb(0x1E2128) : WrenColors.rgb(0xE9ECF1)
            let ctx = try #require(CGContext(data: nil, width: Int(cell) * cols, height: Int(cell) * rows, bitsPerComponent: 8,
                                             bytesPerRow: 0, space: CGColorSpace(name: CGColorSpace.sRGB)!,
                                             bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue))
            ctx.setFillColor(bg)
            ctx.fill(CGRect(x: 0, y: 0, width: cell * CGFloat(cols), height: cell * CGFloat(rows)))
            for (i, (_, pose)) in Self.poses.enumerated() {
                let x = CGFloat(i % cols) * cell, y = CGFloat(rows - 1 - i / cols) * cell
                WrenRender.draw(pose, in: ctx, rect: CGRect(x: x, y: y, width: cell, height: cell), flipped: false)
            }
            let image = try #require(ctx.makeImage())
            try write(image, "wren-poses-\(dark ? "dark" : "light")")
        }
        for (name, pose) in Self.poses.prefix(4) {
            let image = try #require(WrenRender.image(pose, points: 120, scale: 4))
            try write(image, "wren-zoom-\(name)")
        }
        for name in ["rest", "happy", "flying"] {
            let pose = Self.poses.first { $0.0 == name }!.1
            let image = try #require(WrenRender.image(pose, small: true, points: 36, scale: 2))
            try write(image, "wren-small-\(name)")
        }
    }

    private func write(_ image: CGImage, _ name: String) throws {
        let png = try #require(NSBitmapImageRep(cgImage: image).representation(using: .png, properties: [:]))
        try png.write(to: dir.appendingPathComponent("\(name).png"))
    }
}
