import AppKit
import Testing
@testable import MiloKit

/// The live layer rig draws the same Milo as the one-shot renderer, and only redraws what changed.
@Suite @MainActor
struct WrenViewTests {
    private func host(_ input: FigureInput, size: CGFloat = 132) -> (NSWindow, WrenView) {
        _ = NSApplication.shared
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: size, height: size), styleMask: .borderless,
                              backing: .buffered, defer: true)
        let view = WrenView(frame: NSRect(x: 0, y: 0, width: size, height: size))
        window.contentView = view
        view.layoutSubtreeIfNeeded()
        view.update(input)
        return (window, view)
    }

    private func snapshot(_ view: WrenView) -> CGImage? {
        let scale = view.window?.backingScaleFactor ?? 2
        let w = Int(view.bounds.width * scale), h = Int(view.bounds.height * scale)
        guard let ctx = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: 0,
                                  space: CGColorSpace(name: CGColorSpace.sRGB)!,
                                  bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return nil }
        ctx.scaleBy(x: scale, y: scale)
        // render(in:) draws in the layer's own coordinates; a flipped layer needs the bitmap flipped to match.
        if view.layer?.isGeometryFlipped == true {
            ctx.translateBy(x: 0, y: view.bounds.height)
            ctx.scaleBy(x: 1, y: -1)
        }
        view.layer?.render(in: ctx)
        return ctx.makeImage()
    }

    /// Mean difference per channel, 0...255, between two images of one size.
    private func difference(_ a: CGImage, _ b: CGImage) -> Double {
        func bytes(_ image: CGImage) -> [UInt8] {
            var data = [UInt8](repeating: 0, count: image.width * image.height * 4)
            let ctx = CGContext(data: &data, width: image.width, height: image.height, bitsPerComponent: 8,
                                bytesPerRow: image.width * 4, space: CGColorSpace(name: CGColorSpace.sRGB)!,
                                bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
            ctx.draw(image, in: CGRect(x: 0, y: 0, width: image.width, height: image.height))
            return data
        }
        let x = bytes(a), y = bytes(b)
        guard x.count == y.count else { return 255 }
        return Double(zip(x, y).reduce(0) { $0 + abs(Int($1.0) - Int($1.1)) }) / Double(x.count)
    }

    @Test func liveRigMatchesTheStillDrawing() throws {
        for input in [FigureInput(), FigureInput(emotion: .happy), FigureInput(state: .speaking, level: 0.8),
                      FigureInput(flight: .pointing(toward: CGVector(dx: -0.97, dy: -0.24)))] {
            let (window, view) = host(input)
            let live = try #require(snapshot(view))
            let scale = window.backingScaleFactor
            let still = try #require(WrenRender.image(WrenFigure.stillPose(input, small: false), points: 132, scale: scale))
            if let dir = ProcessInfo.processInfo.environment["MILO_RENDER_DIR"] {
                for (name, image) in [("live", live), ("still", still)] {
                    let png = NSBitmapImageRep(cgImage: image).representation(using: .png, properties: [:])
                    try png?.write(to: URL(fileURLWithPath: dir).appendingPathComponent("wren-view-\(name)-\(input.state)-\(input.emotion)-\(input.flight.airborne).png"))
                }
            }
            #expect(difference(live, still) < 2.5, "\(input.state) \(input.emotion)")
            window.contentView = nil
        }
    }
}
