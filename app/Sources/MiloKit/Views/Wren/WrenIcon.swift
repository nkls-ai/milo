import AppKit
import CoreGraphics

/// Milo's icons, drawn from the rig so they always match him: the menu bar silhouette and the app icon.
enum WrenIcon {
    /// An 18 pt template image: his round body, the cocked tail and the beak, with the eye cut out so it
    /// reads as him and not any bird. (The scarf, cut out as a line, split him in two at that size.) It takes the menu bar's colour like every icon there.
    static let menuBar: NSImage = {
        let image = NSImage(size: NSSize(width: 18, height: 18), flipped: true) { rect in
            guard let ctx = NSGraphicsContext.current?.cgContext else { return false }
            silhouette(ctx, in: rect.insetBy(dx: 0.5, dy: 0.5))
            return true
        }
        image.isTemplate = true
        image.accessibilityDescription = "Milo"
        return image
    }()

    /// The part of figure space the silhouette shows: the body, the tail tip and the feet.
    static let silhouetteBox = CGRect(x: 14, y: 72, width: 182, height: 114)

    /// Draws the silhouette in black into `rect` of a context that counts y down.
    static func silhouette(_ ctx: CGContext, in rect: CGRect) {
        let box = silhouetteBox
        let k = min(rect.width / box.width, rect.height / box.height)
        ctx.saveGState()
        ctx.translateBy(x: rect.midX - box.midX * k, y: rect.maxY - box.maxY * k)
        ctx.scaleBy(x: k, y: k)
        let t = -0.2
        let black = CGColor(gray: 0, alpha: 1)
        ctx.beginTransparencyLayer(auxiliaryInfo: nil)
        ctx.setFillColor(black)
        ctx.addPath(WrenRig.bodyPath(turn: t, scarfUp: 0))
        ctx.fillPath()
        // the tail, a single wide feather cocked up behind him
        ctx.saveGState()
        ctx.translateBy(x: 100 + 30 + 0.2 * 34, y: 152)
        ctx.rotate(by: WrenRig.rad(34))
        let tail = CGMutablePath()
        tail.move(to: CGPoint(x: -8, y: 0))
        tail.addLine(to: CGPoint(x: -15, y: -80))
        tail.addQuadCurve(to: CGPoint(x: 15, y: -80), control: CGPoint(x: 0, y: -90))
        tail.addLine(to: CGPoint(x: 8, y: 0))
        tail.closeSubpath()
        ctx.addPath(tail)
        ctx.fillPath()
        ctx.restoreGState()
        // the beak, poking out of his front past the outline, so it shows in silhouette
        let th = t * 50
        let beak = CGMutablePath()
        beak.move(to: CGPoint(x: 46, y: 108))
        beak.addLine(to: CGPoint(x: 18, y: 120))
        beak.addLine(to: CGPoint(x: 48, y: 128))
        beak.closeSubpath()
        ctx.addPath(beak)
        ctx.fillPath()
        // cut out: the near eye
        ctx.setBlendMode(.clear)
        let ex = 100 + 52 * sin(WrenRig.rad(th + WrenRig.eyeAngle)), ey = WrenRig.eyeHeight
        ctx.fillEllipse(in: CGRect(x: ex - 9, y: ey - 10.5, width: 18, height: 21))
        ctx.endTransparencyLayer()
        ctx.restoreGState()
    }

    /// The app icon at `pixels` square: Milo, mid-hop, on a soft lavender tile.
    static func appIcon(pixels: Int) -> CGImage? {
        let n = CGFloat(pixels)
        guard let ctx = CGContext(data: nil, width: pixels, height: pixels, bitsPerComponent: 8, bytesPerRow: 0,
                                  space: CGColorSpace(name: CGColorSpace.sRGB)!,
                                  bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return nil }
        // macOS icon grid: the tile is 824 of 1024, with a soft shadow under it.
        let inset = n * 100 / 1024
        let tile = CGRect(x: inset, y: inset, width: n - inset * 2, height: n - inset * 2)
        let shape = CGPath(roundedRect: tile, cornerWidth: tile.width * 0.225, cornerHeight: tile.width * 0.225, transform: nil)
        ctx.saveGState()
        ctx.setShadow(offset: CGSize(width: 0, height: -n * 0.01), blur: n * 0.025, color: CGColor(gray: 0, alpha: 0.3))
        ctx.addPath(shape)
        ctx.setFillColor(WrenColors.rgb(0xF4F0FD))
        ctx.fillPath()
        ctx.restoreGState()
        ctx.saveGState()
        ctx.addPath(shape)
        ctx.clip()
        ctx.drawLinearGradient(WrenRig.gradient([WrenColors.rgb(0xFBF8FF), WrenColors.rgb(0xDCD3F7)]),
                               start: CGPoint(x: 0, y: tile.maxY), end: CGPoint(x: 0, y: tile.minY), options: [])
        // a warm marigold sun behind him
        let sun = CGPoint(x: tile.midX + tile.width * 0.2, y: tile.midY + tile.height * 0.2)
        ctx.drawRadialGradient(WrenRig.gradient([WrenColors.rgb(0xFAD58A, 0.75), WrenColors.rgb(0xFAD58A, 0)]),
                               startCenter: sun, startRadius: 0, endCenter: sun, endRadius: tile.width * 0.42, options: [])
        var pose = WrenPose.rest
        pose.lidL = 0.12; pose.lidR = 0.12
        pose.tail = 10
        pose.browL = 0.2; pose.browR = 0.2
        pose.gazeX = -0.15; pose.gazeY = -0.1
        let figure = CGRect(x: tile.minX + tile.width * 0.04, y: tile.minY + tile.height * 0.02,
                            width: tile.width * 0.92, height: tile.height * 0.92)
        WrenRender.draw(pose, small: pixels <= 64, in: ctx, rect: figure,
                        viewBox: CGRect(x: 16, y: 50, width: 172, height: 150), flipped: false)
        ctx.restoreGState()
        return ctx.makeImage()
    }
}
