import CoreGraphics
import Foundation

/// Milo drawn in one go, for snapshots, icons and anywhere a live rig isn't worth it.
enum WrenRender {
    /// Milo at `pose` in a square of `points`, framed like the 120 pt corner figure (feet near the bottom).
    static func image(_ pose: WrenPose, small: Bool = false, points: CGFloat = 120, scale: CGFloat = 2,
                      viewBox: CGRect = WrenRig.viewBox, background: CGColor? = nil) -> CGImage? {
        let pixels = Int((points * scale).rounded())
        guard let ctx = CGContext(data: nil, width: pixels, height: pixels, bitsPerComponent: 8, bytesPerRow: 0,
                                  space: CGColorSpace(name: CGColorSpace.sRGB)!,
                                  bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return nil }
        if let background {
            ctx.setFillColor(background)
            ctx.fill(CGRect(x: 0, y: 0, width: pixels, height: pixels))
        }
        draw(pose, small: small, in: ctx, rect: CGRect(x: 0, y: 0, width: points * scale, height: points * scale),
             viewBox: viewBox, flipped: false)
        return ctx.makeImage()
    }

    /// Draws Milo into `rect` of `ctx`. `flipped` says the context already counts y down (an NSView's).
    static func draw(_ pose: WrenPose, small: Bool = false, in ctx: CGContext, rect: CGRect,
                     viewBox: CGRect = WrenRig.viewBox, flipped: Bool) {
        ctx.saveGState()
        ctx.setShouldAntialias(true)
        ctx.interpolationQuality = .high
        if flipped {
            ctx.translateBy(x: rect.minX, y: rect.minY)
        } else {
            ctx.translateBy(x: rect.minX, y: rect.maxY)
            ctx.scaleBy(x: 1, y: -1)
        }
        let k = min(rect.width / viewBox.width, rect.height / viewBox.height)
        ctx.scaleBy(x: k, y: k)
        ctx.translateBy(x: -viewBox.minX, y: -viewBox.minY)
        WrenRig.frame(pose, small: small).draw(in: ctx)
        ctx.restoreGState()
    }
}
