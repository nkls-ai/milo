import CoreGraphics
import Foundation

/// Milo's colours, from the design page.
enum WrenColors {
    static let bodyHi = rgb(0xC6BCF0), bodyMid = rgb(0x9688D6), bodyLo = rgb(0x5E4FA4)
    static let lidLine = rgb(0x3F3373)
    static let bellyHi = rgb(0xFBF3E8), bellyLo = rgb(0xE9D5C0)
    static let brow = rgb(0xF6F2FE)
    static let wingHi = rgb(0x8A7CCB), wingLo = rgb(0x54468F), wingBar = rgb(0xB9AEEA)
    static let tail = rgb(0x6C5DB2), tailLo = rgb(0x4C3F8A), tailBar = rgb(0x43377D)
    static let eye = rgb(0x1E1730), eyeHi = rgb(0x4F4276)
    static let beakHi = rgb(0xE6B274), beakLo = rgb(0xB27744), mouth = rgb(0x6E2F3C)
    static let scarfHi = rgb(0xF0B649), scarfLo = rgb(0xC98526), scarfRib = rgb(0xFAD58A), scarfEdge = rgb(0xFFE2A6)
    static let feet = rgb(0xB17C50), blush = rgb(0xEE9AA6)
    static let shade = rgb(0x2E2463), ground = rgb(0x2A2050), rim = rgb(0xF1ECFF)
    static let ink = rgb(0x1B1430)

    static func rgb(_ hex: UInt32, _ alpha: CGFloat = 1) -> CGColor {
        CGColor(srgbRed: CGFloat((hex >> 16) & 0xFF) / 255, green: CGFloat((hex >> 8) & 0xFF) / 255,
                blue: CGFloat(hex & 0xFF) / 255, alpha: alpha)
    }
}

/// One drawable piece of the rig: its drawing in local coordinates (y down), the box that drawing fits in,
/// and where it sits. A live layer redraws a part only when its `key` changes; every other change is a
/// transform, which Core Animation composites outside Milo's process.
struct WrenPart {
    enum ID: Int, CaseIterable {
        case shadow, feet, tail, wingFoldL, wingOpenL, wingFoldR, wingOpenR, body, scarfEnd, knot
        case blush, eyeL, eyeR, browL, browR, beak
    }

    let id: ID
    var box: CGRect
    /// The inputs the drawing depends on, rounded. Equal keys draw equal pixels.
    var key: [Int]
    var draw: (CGContext) -> Void
    /// Local to parent coordinates.
    var transform: CGAffineTransform = .identity
    var opacity: Double = 1
    /// Back to front within its group.
    var z: Int
}

/// The rig at one pose: the shadow on the ground, the body group (everything that leans, lifts and
/// squashes with him) and the face group inside it (everything that tilts with his head).
struct WrenFrame {
    var shadow: WrenPart
    var body: CGAffineTransform
    var bodyParts: [WrenPart]
    var face: CGAffineTransform
    var faceParts: [WrenPart]

    /// Draws the whole figure into `ctx`, whose coordinates are figure space (y down).
    func draw(in ctx: CGContext) {
        func paint(_ part: WrenPart) {
            guard part.opacity > 0.001 else { return }
            ctx.saveGState()
            ctx.concatenate(part.transform)
            ctx.setAlpha(CGFloat(part.opacity))
            if part.opacity < 0.999 { ctx.beginTransparencyLayer(auxiliaryInfo: nil) }
            part.draw(ctx)
            if part.opacity < 0.999 { ctx.endTransparencyLayer() }
            ctx.restoreGState()
        }
        paint(shadow)
        ctx.saveGState()
        ctx.concatenate(body)
        let faceZ = WrenRig.faceZ
        for part in bodyParts.sorted(by: { $0.z < $1.z }) where part.z < faceZ { paint(part) }
        ctx.saveGState()
        ctx.concatenate(face)
        for part in faceParts.sorted(by: { $0.z < $1.z }) { paint(part) }
        ctx.restoreGState()
        for part in bodyParts.sorted(by: { $0.z < $1.z }) where part.z > faceZ { paint(part) }
        ctx.restoreGState()
    }
}

/// Builds Milo from a pose. All geometry is in figure space (see `WrenPose`).
enum WrenRig {
    static let ground = 182.0
    /// The face group's place among the body parts.
    static let faceZ = 7
    /// The part of figure space a 120 pt box shows: his middle at x 60, his feet at y 107.
    static let viewBox = CGRect(x: 100 - 60 / scale, y: ground - 107 / scale, width: 120 / scale, height: 120 / scale)
    /// Points per figure unit in a 120 pt box.
    static let scale = 0.62

    static func frame(_ p: WrenPose, small: Bool = false) -> WrenFrame {
        let t = p.turn
        let th = t * 50
        let R = 52.0
        let fx = { (a: Double) in 100 + R * sin(a * .pi / 180) }

        var parts: [WrenPart] = []
        let flight = smooth(0.3, 0.7, p.fly)

        // Ground shadow: shrinks and fades as he rises; gone while he flies between windows.
        let lift = p.lift + p.fly * 16
        let ss = max(0.35, 1 - lift / 70)
        let shadow = WrenPart(id: .shadow, box: CGRect(x: -50, y: -10, width: 100, height: 20), key: [], draw: { ctx in
            softEllipse(ctx, center: .zero, rx: 46, ry: 7.5, color: WrenColors.ground, alpha: 0.24)
        }, transform: CGAffineTransform(translationX: 100, y: ground + 1).scaledBy(x: ss, y: ss),
           opacity: (1 - flight) * (0.4 + 0.6 * ss), z: 0)

        // Feet
        let feetX = [87 + t * 8, 113 + t * 8]
        parts.append(WrenPart(id: .feet, box: CGRect(x: 75, y: 170, width: 52, height: 16), key: keys(t), draw: { ctx in
            let path = CGMutablePath()
            for x in feetX {
                path.move(to: CGPoint(x: x, y: 174)); path.addLine(to: CGPoint(x: x, y: 181))
                path.move(to: CGPoint(x: x - 5, y: 182)); path.addLine(to: CGPoint(x: x, y: 180.5))
                path.addLine(to: CGPoint(x: x + 5.5, y: 182))
                path.move(to: CGPoint(x: x, y: 180.5)); path.addLine(to: CGPoint(x: x + 1.4, y: 182.6))
            }
            stroke(ctx, path, WrenColors.feet, width: small ? 3.2 : 2.4)
        }, opacity: p.feet * (1 - flight), z: 0))

        // Tail: one barred feather fan cocked up behind his back, on the side he faces away from.
        let back = t > 0.02 ? -1.0 : 1.0
        let tailL = 74 * (1 - p.fly * 0.3)
        let tailW = ((7.5 + max(p.tailFan, p.fly) * 3.5) * 4).rounded() / 4
        let tailAngle = back * (27 + p.tail * 0.8 + abs(t) * 10 + p.fly * 42)
        parts.append(WrenPart(id: .tail, box: CGRect(x: -16, y: -tailL - 8, width: 32, height: tailL + 12),
                              key: keys(tailL, tailW, small ? 1 : 0), draw: { ctx in
            drawTail(ctx, length: tailL, width: tailW, small: small)
        }, transform: CGAffineTransform(translationX: 100 + back * (26 + abs(t) * 34), y: 146).rotated(by: rad(tailAngle)), z: 1))

        // Wings: each a folded wing and an open one, cross-faded as it opens so the shape never swaps.
        // Turned far enough, the far wing slips behind him; open, it shows behind the body instead.
        let far: Character? = t > 0.05 ? "R" : t < -0.05 ? "L" : nil
        let farHidden = smooth(0.2, 0.3, abs(t))
        for side in ["L", "R"] as [Character] {
            let s = side == "L" ? -1.0 : 1.0
            let angle = side == "L" ? p.wingL : p.wingR
            let open = max(p.fly, side == "L" ? p.openL : p.openR)
            // the open wing is solid before the folded one fades, so the swap never shows through him
            let shown = smooth(0.2, 0.5, open)
            let folded = 1 - smooth(0.45, 0.75, open)
            let x = (side == "L" ? 50 : 150) + t * 20
            let isFar = far == side
            parts.append(WrenPart(id: side == "L" ? .wingFoldL : .wingFoldR, box: CGRect(x: -18, y: -8, width: 36, height: 56),
                                  key: keys(s, small ? 1 : 0), draw: { ctx in
                drawFoldedWing(ctx, side: s, length: 46, small: small)
            }, transform: CGAffineTransform(translationX: x, y: 112).rotated(by: rad(-s * (angle + open * 80))),
               opacity: folded * (isFar ? 1 - farHidden : 1), z: 4))
            let flap = -s * (angle - (1 - open) * 80)
            parts.append(WrenPart(id: side == "L" ? .wingOpenL : .wingOpenR, box: CGRect(x: -60, y: -24, width: 120, height: 36),
                                  key: keys(s, small ? 1 : 0), draw: { ctx in
                drawOpenWing(ctx, side: s, k: 0.8, small: small)
            }, transform: CGAffineTransform(translationX: x, y: 108).rotated(by: rad(flap)), opacity: shown, z: isFar ? 2 : 4))
        }

        // Body, belly, shading and the scarf band
        parts.append(WrenPart(id: .body, box: CGRect(x: 36, y: 50, width: 128, height: 136),
                              key: keys(t, p.scarfUp, small ? 1 : 0), draw: { ctx in
            drawBody(ctx, turn: t, scarfUp: p.scarfUp, small: small)
        }, z: 3))

        // The scarf's loose end, swinging from the knot, and the knot over it
        let sy = 121 - p.scarfUp * 8
        let knotX = fx(th + 32)
        let knotY = sy + 10 + (1 - pow((knotX - 100) / 56, 2)) * 2
        let endLen = 38 * (1 + p.scarfToss * 0.2)
        let endAngle = -12 + p.scarf + p.scarfToss * -118 + p.fly * -70
        parts.append(WrenPart(id: .scarfEnd, box: CGRect(x: -12, y: -4, width: 24, height: endLen + 12),
                              key: keys(endLen, small ? 1 : 0), draw: { ctx in
            drawScarfEnd(ctx, length: endLen, small: small)
        }, transform: CGAffineTransform(translationX: knotX, y: knotY).rotated(by: rad(endAngle)), z: 5))
        parts.append(WrenPart(id: .knot, box: CGRect(x: -10, y: -8, width: 20, height: 16), key: [], draw: { ctx in
            let knot = CGPath(ellipseIn: CGRect(x: -8, y: -6.5, width: 16, height: 13), transform: nil)
            fillLinear(ctx, knot, [WrenColors.scarfHi, WrenColors.scarfLo], top: -6.5, bottom: 6.5)
            let crease = CGMutablePath()
            crease.move(to: CGPoint(x: -5, y: -1)); crease.addQuadCurve(to: CGPoint(x: 5, y: -1), control: CGPoint(x: 0, y: 2))
            stroke(ctx, crease, WrenColors.scarfLo, width: 1.2, alpha: 0.7)
        }, transform: CGAffineTransform(translationX: knotX, y: knotY), z: 6))

        // Face
        var face: [WrenPart] = []
        let gx = p.gazeX * 4.5, gy = p.gazeY * 3.5
        let eyeY = 99 + gy - p.scarfUp * 4
        let eyes: [(Character, Double)] = [("L", th - 23), ("R", th + 23)]
        let bodyCenter = CGPoint(x: 84 + t * 12, y: 90)
        if p.blush > 0.01 {
            let spots = eyes.map { side, a in
                (CGPoint(x: fx(a + (side == "L" ? -9 : 9)) + gx, y: eyeY + 13), 7 * cos(rad(a)))
            }
            face.append(WrenPart(id: .blush, box: CGRect(x: 40, y: 90, width: 120, height: 40), key: keys(t, gx, gy), draw: { ctx in
                for (c, rx) in spots { softEllipse(ctx, center: c, rx: rx + 3, ry: 6, color: WrenColors.blush, alpha: 0.6) }
            }, opacity: min(1, p.blush), z: 0))
        }
        for (side, a) in eyes {
            let s = side == "L" ? -1.0 : 1.0
            let x = fx(a) + gx
            let fore = max(0.35, cos(rad(a)))
            let lid = side == "L" ? p.lidL : p.lidR
            let lower = side == "L" ? p.lowerL : p.lowerR
            let es = (side == "L" ? p.eyeL : p.eyeR) * (small ? 1.12 : 1)
            let center = CGPoint(x: x, y: eyeY)
            let catchlight = CGPoint(x: (p.gazeX * 10).rounded() / 10, y: (p.gazeY * 10).rounded() / 10)
            face.append(WrenPart(id: side == "L" ? .eyeL : .eyeR, box: CGRect(x: -14, y: -15, width: 28, height: 30),
                                 key: keys(lid, lower, es, fore, catchlight.x, catchlight.y, t),
                                 draw: { ctx in
                drawEye(ctx, lid: lid, lower: lower, sx: fore * es, sy: es, look: catchlight,
                        bodyCenter: CGPoint(x: bodyCenter.x - center.x, y: bodyCenter.y - center.y))
            }, transform: CGAffineTransform(translationX: x, y: eyeY), z: side == "L" ? 1 : 2))

            // Brow stripe: a pale sweep over the eye, running back toward the side of the head.
            let raise = (side == "L" ? p.browL : p.browR) * 4.5
            let tilt = (side == "L" ? p.browTiltL : p.browTiltR) * 16 * s
            face.append(WrenPart(id: side == "L" ? .browL : .browR, box: CGRect(x: -24, y: -10, width: 48, height: 20),
                                 key: keys(s, fore), draw: { ctx in
                let path = taper(CGPoint(x: -s * 8 * fore, y: 2.5), CGPoint(x: s * 3 * fore, y: -4.5),
                                 CGPoint(x: s * 18 * fore, y: 6), width: small ? 6.5 : 5.4, end: 1.4)
                ctx.addPath(path)
                ctx.setFillColor(WrenColors.brow.copy(alpha: 0.96)!)
                ctx.fillPath()
            }, transform: CGAffineTransform(translationX: x, y: eyeY - 13.5 - raise).rotated(by: rad(tilt)), z: side == "L" ? 3 : 4))
        }
        // Beak: thin and a touch long; the tip swings toward the turn.
        let bx = fx(th) + gx * 1.1, by = 109 + gy - p.scarfUp * 6
        let tip = t * 9 + p.gazeX * 2
        // in twentieths: finer steps don't show, and each step redraws the beak
        let open = (min(1, max(0, p.beak)) * 20).rounded() / 20
        face.append(WrenPart(id: .beak, box: CGRect(x: -12, y: -8, width: 24, height: 30),
                             key: keys(open, tip, t), draw: { ctx in
            drawBeak(ctx, open: open, tip: tip, turn: t)
        }, transform: CGAffineTransform(translationX: bx, y: by), z: 5))

        let lean = rad(p.lean)
        let body = CGAffineTransform(translationX: 0, y: -lift)
            .concatenating(.identity)
        let pivot = CGPoint(x: 100, y: ground)
        let breathe = p.breath * 0.012
        let squash = CGAffineTransform(translationX: pivot.x, y: pivot.y)
            .scaledBy(x: 1 - p.squash * 0.6 - breathe * 0.3, y: 1 + p.squash + breathe)
            .translatedBy(x: -pivot.x, y: -pivot.y)
        let tilt = CGAffineTransform(translationX: pivot.x, y: pivot.y).rotated(by: lean).translatedBy(x: -pivot.x, y: -pivot.y)
        let bodyTransform = squash.concatenating(tilt).concatenating(body)
        let facePivot = CGPoint(x: fx(th), y: 104)
        let faceTransform = CGAffineTransform(translationX: facePivot.x + p.headX, y: facePivot.y + p.headY)
            .rotated(by: rad(p.headTilt))
            .translatedBy(x: -facePivot.x, y: -facePivot.y)
        return WrenFrame(shadow: shadow, body: bodyTransform, bodyParts: parts, face: faceTransform, faceParts: face)
    }

    // MARK: Parts

    private static func drawTail(_ ctx: CGContext, length L: Double, width w: Double, small: Bool) {
        let path = CGMutablePath()
        path.move(to: CGPoint(x: -w * 0.5, y: 0))
        path.addCurve(to: CGPoint(x: -w, y: -L + 2), control1: CGPoint(x: -w * 0.75, y: -L * 0.45), control2: CGPoint(x: -w - 1.2, y: -L * 0.78))
        for cx in [-w * 0.33, w * 0.33, w] {
            path.addQuadCurve(to: CGPoint(x: cx, y: -L - 0.6), control: CGPoint(x: cx - w * 0.36, y: -L - 3.2))
        }
        path.addCurve(to: CGPoint(x: w * 0.5, y: 0), control1: CGPoint(x: w + 1.2, y: -L * 0.78), control2: CGPoint(x: w * 0.75, y: -L * 0.45))
        path.closeSubpath()
        fillLinear(ctx, path, [WrenColors.tail, WrenColors.tailLo], top: -L - 3, bottom: 0)
        guard !small else { return }
        let bars = CGMutablePath()
        for y in [0.56, 0.7, 0.84] {
            bars.move(to: CGPoint(x: -w * 0.85, y: -L * y + 1.8))
            bars.addQuadCurve(to: CGPoint(x: w * 0.85, y: -L * y + 1.8), control: CGPoint(x: 0, y: -L * y - 1.6))
        }
        ctx.saveGState()
        ctx.addPath(path); ctx.clip()
        stroke(ctx, bars, WrenColors.tailBar, width: 1.7, alpha: 0.5)
        ctx.restoreGState()
        let shine = CGMutablePath()
        shine.move(to: CGPoint(x: -w + 2, y: -L + 6)); shine.addQuadCurve(to: CGPoint(x: w - 3, y: -L + 5), control: CGPoint(x: 0, y: -L - 1))
        stroke(ctx, shine, CGColor(gray: 1, alpha: 1), width: 1, alpha: 0.25)
    }

    private static func drawFoldedWing(_ ctx: CGContext, side s: Double, length L: Double, small: Bool) {
        let path = CGMutablePath()
        path.move(to: CGPoint(x: 2 * s, y: -5))
        path.addCurve(to: CGPoint(x: -15 * s, y: L * 0.42), control1: CGPoint(x: -9 * s, y: -5), control2: CGPoint(x: -15 * s, y: 8))
        path.addCurve(to: CGPoint(x: -4 * s, y: L), control1: CGPoint(x: -15 * s, y: L * 0.72), control2: CGPoint(x: -9 * s, y: L * 0.9))
        path.addCurve(to: CGPoint(x: 11 * s, y: L * 0.36), control1: CGPoint(x: 4 * s, y: L * 0.82), control2: CGPoint(x: 11 * s, y: L * 0.6))
        path.addCurve(to: CGPoint(x: 2 * s, y: -5), control1: CGPoint(x: 11 * s, y: 8), control2: CGPoint(x: 10 * s, y: -5))
        path.closeSubpath()
        fillLinear(ctx, path, [WrenColors.wingHi, WrenColors.wingLo], top: -5, bottom: L)
        guard !small else { return }
        let bars = CGMutablePath()
        for (i, k) in [0.56, 0.7, 0.84].enumerated() {
            let i = Double(i)
            bars.move(to: CGPoint(x: -12 * s + i * 2.5 * s, y: L * k))
            bars.addQuadCurve(to: CGPoint(x: 5 * s - i * 2.5 * s, y: L * k - 1.5), control: CGPoint(x: -4 * s, y: L * k + 2.6))
        }
        stroke(ctx, bars, WrenColors.wingBar, width: 1.3, alpha: 0.4)
    }

    private static func drawOpenWing(_ ctx: CGContext, side s: Double, k: Double, small: Bool) {
        func q(_ x: Double, _ y: Double) -> CGPoint { CGPoint(x: s * x * k, y: y * k) }
        let path = CGMutablePath()
        path.move(to: q(0, -6))
        path.addCurve(to: q(62, -20), control1: q(16, -16), control2: q(40, -24))
        path.addQuadCurve(to: q(62, -12), control: q(68, -17))
        path.addQuadCurve(to: q(58, -5), control: q(66, -8))
        path.addQuadCurve(to: q(52, 1), control: q(61, 0))
        path.addQuadCurve(to: q(44, 6), control: q(54, 6))
        path.addQuadCurve(to: q(34, 10), control: q(44, 11))
        path.addCurve(to: q(0, 6), control1: q(22, 10), control2: q(8, 9))
        path.closeSubpath()
        fillLinear(ctx, path, [WrenColors.wingHi, WrenColors.wingLo], top: -24 * k, bottom: 11 * k)
        guard !small else { return }
        let bars = CGMutablePath()
        for (a, b, c, e) in [(30.0, -14.0, 32.0, 7.0), (42, -17, 44, 3), (52, -18, 53, 0)] {
            bars.move(to: q(a, b)); bars.addLine(to: q(c, e))
        }
        stroke(ctx, bars, WrenColors.wingBar, width: 1.2, alpha: 0.45)
        let edge = CGMutablePath()
        edge.move(to: q(4, -6)); edge.addCurve(to: q(60, -19), control1: q(18, -14), control2: q(40, -21))
        stroke(ctx, edge, CGColor(gray: 1, alpha: 1), width: 1.2, alpha: 0.3)
    }

    static func bodyPath(turn t: Double, scarfUp: Double) -> CGPath {
        let top = 58 + scarfUp * 2
        let xr = 157 + max(t, 0) * 5, xl = 43 + min(t, 0) * 5
        let path = CGMutablePath()
        path.move(to: CGPoint(x: 100 + t * 9, y: top))
        path.addCurve(to: CGPoint(x: xr, y: 126), control1: CGPoint(x: 134 + t * 6, y: top), control2: CGPoint(x: xr, y: top + 34))
        path.addCurve(to: CGPoint(x: 100, y: 180), control1: CGPoint(x: xr, y: 160), control2: CGPoint(x: 133, y: 180))
        path.addCurve(to: CGPoint(x: xl, y: 126), control1: CGPoint(x: 67, y: 180), control2: CGPoint(x: xl, y: 160))
        path.addCurve(to: CGPoint(x: 100 + t * 9, y: top), control1: CGPoint(x: xl, y: top + 34), control2: CGPoint(x: 66 + t * 8, y: top))
        path.closeSubpath()
        return path
    }

    /// The body's gradient, in figure space, so lids can paint with the same colours and vanish into him.
    static func bodyGradient(_ ctx: CGContext, center: CGPoint) {
        ctx.drawRadialGradient(gradient([WrenColors.bodyHi, WrenColors.bodyMid, WrenColors.bodyLo], [0, 0.5, 1]),
                               startCenter: center, startRadius: 0, endCenter: center, endRadius: 100,
                               options: [.drawsAfterEndLocation])
    }

    private static func drawBody(_ ctx: CGContext, turn t: Double, scarfUp: Double, small: Bool) {
        let th = t * 50
        let body = bodyPath(turn: t, scarfUp: scarfUp)
        let top = 58 + scarfUp * 2
        ctx.saveGState()
        ctx.addPath(body); ctx.clip()
        bodyGradient(ctx, center: CGPoint(x: 84 + t * 12, y: 90))
        // belly
        let bellyX = 100 + 52 * sin(rad(th * 0.75))
        let brx = 36 - abs(t) * 4
        let belly = CGPath(ellipseIn: CGRect(x: bellyX - brx, y: 115, width: brx * 2, height: 70), transform: nil)
        fillLinear(ctx, belly, [WrenColors.bellyHi, WrenColors.bellyLo], top: 115, bottom: 185)
        // ambient occlusion where he meets the ground, and the key light on his crown
        softEllipse(ctx, center: CGPoint(x: 100, y: 188), rx: 76, ry: 32, color: WrenColors.shade, alpha: 0.36)
        softEllipse(ctx, center: CGPoint(x: 78 + t * 8, y: top + 17), rx: 25, ry: 13, color: CGColor(gray: 1, alpha: 1),
                    alpha: 0.32, rotation: -24)
        // scarf band, with the soft shadow it casts on him
        let sy = 121 - scarfUp * 8
        let band = CGMutablePath()
        band.move(to: CGPoint(x: 44, y: sy - 5))
        band.addQuadCurve(to: CGPoint(x: 156, y: sy - 5), control: CGPoint(x: 100, y: sy + 12))
        band.addLine(to: CGPoint(x: 157, y: sy + 8))
        band.addQuadCurve(to: CGPoint(x: 43, y: sy + 8), control: CGPoint(x: 100, y: sy + 26))
        band.closeSubpath()
        ctx.saveGState()
        ctx.setShadow(offset: CGSize(width: 0, height: -device(ctx, 4)), blur: device(ctx, 5), color: WrenColors.shade.copy(alpha: 0.42))
        fillLinear(ctx, band, [WrenColors.scarfHi, WrenColors.scarfLo], top: sy - 5, bottom: sy + 17)
        ctx.restoreGState()
        fillLinear(ctx, band, [WrenColors.scarfHi, WrenColors.scarfLo], top: sy - 5, bottom: sy + 17)
        if !small {
            let ribs = CGMutablePath()
            for i in 0...14 {
                let x = 50 + Double(i) * 7.2
                let y = sy - 5 + (1 - pow((x - 100) / 56, 2)) * 8.5
                ribs.move(to: CGPoint(x: x, y: y + 2)); ribs.addLine(to: CGPoint(x: x + 0.6, y: y + 12.5))
            }
            stroke(ctx, ribs, WrenColors.scarfRib, width: 1.1, alpha: 0.55)
        }
        let edge = CGMutablePath()
        edge.move(to: CGPoint(x: 44, y: sy - 5)); edge.addQuadCurve(to: CGPoint(x: 156, y: sy - 5), control: CGPoint(x: 100, y: sy + 12))
        stroke(ctx, edge, WrenColors.scarfEdge, width: 1.4, alpha: 0.7)
        // rim light: a soft crescent on the side away from the key light
        ctx.beginTransparencyLayer(auxiliaryInfo: nil)
        ctx.addPath(body); ctx.setFillColor(WrenColors.rim.copy(alpha: 0.55)!); ctx.fillPath()
        ctx.setBlendMode(.destinationOut)
        ctx.setShadow(offset: .zero, blur: device(ctx, 3), color: CGColor(gray: 0, alpha: 1))
        var shift = CGAffineTransform(translationX: -5, y: 3.5)
        if let moved = body.copy(using: &shift) { ctx.addPath(moved) }
        ctx.setFillColor(CGColor(gray: 0, alpha: 1)); ctx.fillPath()
        ctx.endTransparencyLayer()
        ctx.restoreGState()
    }

    private static func drawScarfEnd(_ ctx: CGContext, length E: Double, small: Bool) {
        let path = CGMutablePath()
        path.move(to: CGPoint(x: -6, y: 0))
        path.addCurve(to: CGPoint(x: -9, y: E), control1: CGPoint(x: -7, y: E * 0.4), control2: CGPoint(x: -8.5, y: E * 0.8))
        path.addLine(to: CGPoint(x: 9, y: E + 2))
        path.addCurve(to: CGPoint(x: 6, y: 0), control1: CGPoint(x: 7.5, y: E * 0.7), control2: CGPoint(x: 6.5, y: E * 0.35))
        path.closeSubpath()
        fillLinear(ctx, path, [WrenColors.scarfHi, WrenColors.scarfLo], top: 0, bottom: E + 2)
        let crease = CGMutablePath()
        crease.move(to: CGPoint(x: -6, y: 0)); crease.addLine(to: CGPoint(x: 6, y: 0))
        stroke(ctx, crease, WrenColors.shade, width: 2, alpha: 0.18, cap: .butt)
        guard !small else { return }
        let ribs = CGMutablePath()
        ribs.move(to: CGPoint(x: -2, y: 5)); ribs.addLine(to: CGPoint(x: -3, y: E - 2))
        ribs.move(to: CGPoint(x: 2.5, y: 5)); ribs.addLine(to: CGPoint(x: 3, y: E - 1))
        stroke(ctx, ribs, WrenColors.scarfRib, width: 1, alpha: 0.5)
        let fringe = CGMutablePath()
        for x in [-7.0, -3.5, 0, 3.5, 7] {
            fringe.move(to: CGPoint(x: x, y: E + 1 + x * 0.1)); fringe.addLine(to: CGPoint(x: x * 1.08, y: E + 6 + x * 0.1))
        }
        stroke(ctx, fringe, WrenColors.scarfLo, width: 1.7)
    }

    private static func drawEye(_ ctx: CGContext, lid: Double, lower: Double, sx: Double, sy: Double, look: CGPoint,
                                bodyCenter: CGPoint) {
        let rx = 7.4, ry = 8.8
        let yl = -ry + lid * ry * 2.1
        let sag = -1.6 + 5 * lid * lid
        let yb = ry - lower * ry * 1.25
        let smile = smooth(0.7, 0.9, lower)
        ctx.saveGState()
        ctx.scaleBy(x: sx, y: sy)
        let eye = CGPath(ellipseIn: CGRect(x: -rx, y: -ry, width: rx * 2, height: ry * 2), transform: nil)
        let bigger = CGPath(ellipseIn: CGRect(x: -rx - 1.2, y: -ry - 1.2, width: rx * 2 + 2.4, height: ry * 2 + 2.4), transform: nil)
        if smile < 1 {
            ctx.beginTransparencyLayer(auxiliaryInfo: nil)
            ctx.setAlpha(CGFloat(1 - smile))
            if lid < 0.97 {
                ctx.saveGState()
                ctx.addPath(eye); ctx.clip()
                ctx.drawRadialGradient(gradient([WrenColors.eyeHi, WrenColors.eye], [0, 1]),
                                       startCenter: CGPoint(x: 0, y: ry * 0.7), startRadius: 0,
                                       endCenter: CGPoint(x: 0, y: ry * 0.7), endRadius: ry * 1.5, options: [.drawsAfterEndLocation])
                fill(ctx, CGPath(ellipseIn: CGRect(x: 2.4 + look.x * 0.7 - 2.6, y: -2.6 + look.y * 0.6 - 2.6, width: 5.2, height: 5.2), transform: nil),
                     CGColor(gray: 1, alpha: 1))
                fill(ctx, CGPath(ellipseIn: CGRect(x: -3.7, y: 2.2, width: 2.2, height: 2.2), transform: nil), CGColor(gray: 1, alpha: 0.75))
                // the shadow the upper lid casts on the eye
                fill(ctx, lidPath(yl: yl + 1.6, sag: sag), WrenColors.ink.copy(alpha: 0.3)!)
                ctx.restoreGState()
            }
            // lids paint with the body's own gradient, so at rest they disappear into him
            ctx.saveGState()
            ctx.addPath(bigger); ctx.clip()
            let lids = CGMutablePath()
            lids.addPath(lidPath(yl: yl, sag: sag))
            if lower > 0.001 {
                lids.move(to: CGPoint(x: -11, y: 12)); lids.addLine(to: CGPoint(x: -11, y: yb + 3))
                lids.addQuadCurve(to: CGPoint(x: 11, y: yb + 3), control: CGPoint(x: 0, y: yb - 6))
                lids.addLine(to: CGPoint(x: 11, y: 12)); lids.closeSubpath()
            }
            ctx.addPath(lids); ctx.clip()
            ctx.scaleBy(x: 1 / sx, y: 1 / sy)
            bodyGradient(ctx, center: bodyCenter)
            ctx.restoreGState()
            if lid > 0.04 {
                let closed = min(yl, ry - 0.5)
                let line = CGMutablePath()
                line.move(to: CGPoint(x: -rx - 0.4, y: closed))
                line.addQuadCurve(to: CGPoint(x: rx + 0.4, y: closed), control: CGPoint(x: 0, y: closed + sag))
                stroke(ctx, line, WrenColors.lidLine, width: lid > 0.95 ? 2.1 : 1.1, alpha: lid > 0.95 ? 1 : 0.6 + 0.4 * smooth(0.5, 0.95, lid))
            }
            if lower > 0.3 {
                let line = CGMutablePath()
                line.move(to: CGPoint(x: -rx + 0.5, y: yb + 2.6))
                line.addQuadCurve(to: CGPoint(x: rx - 0.5, y: yb + 2.6), control: CGPoint(x: 0, y: yb - 5.6))
                stroke(ctx, line, WrenColors.lidLine, width: 1 + 0.8 * smooth(0.4, 0.8, lower), alpha: 0.5 + 0.4 * smooth(0.4, 0.8, lower))
            }
            ctx.endTransparencyLayer()
        }
        if smile > 0 {
            // smiling: a clean arch
            let arch = CGMutablePath()
            arch.move(to: CGPoint(x: -6.8, y: 4.6)); arch.addQuadCurve(to: CGPoint(x: 6.8, y: 4.6), control: CGPoint(x: 0, y: -5.4))
            stroke(ctx, arch, WrenColors.eye, width: 3, alpha: smile)
        }
        ctx.restoreGState()
    }

    private static func lidPath(yl: Double, sag: Double) -> CGPath {
        let path = CGMutablePath()
        path.move(to: CGPoint(x: -11, y: -12)); path.addLine(to: CGPoint(x: 11, y: -12)); path.addLine(to: CGPoint(x: 11, y: yl))
        path.addQuadCurve(to: CGPoint(x: -11, y: yl), control: CGPoint(x: 0, y: yl + sag))
        path.closeSubpath()
        return path
    }

    /// The beak: a short upper bill pointing down at the viewer, the lower bill swinging down below it to
    /// open the mouth. Open, the upper bill lifts a touch and shortens, as the head tips back to speak.
    private static func drawBeak(_ ctx: CGContext, open: Double, tip: Double, turn t: Double) {
        let d = open * 11
        let upperTip = 13 - open * 3
        if open > 0.03 {
            // the lower bill: a V-shaped band whose tip drops as he opens
            let lower = CGMutablePath()
            lower.move(to: CGPoint(x: -6, y: 3 + d * 0.4))
            lower.addQuadCurve(to: CGPoint(x: tip * 0.8 - 0.4, y: 10.5 + d), control: CGPoint(x: -2.8, y: 8.5 + d))
            lower.addQuadCurve(to: CGPoint(x: 6, y: 3 + d * 0.4), control: CGPoint(x: 2.6, y: 8.5 + d))
            lower.closeSubpath()
            fillLinear(ctx, lower, [WrenColors.beakHi, WrenColors.beakLo], top: 3, bottom: 11 + d)
            // the mouth inside it, with a hint of tongue once it is properly open
            let mouth = CGMutablePath()
            mouth.move(to: CGPoint(x: -5, y: 2.5))
            mouth.addQuadCurve(to: CGPoint(x: tip * 0.8 - 0.3, y: 8.2 + d * 0.86), control: CGPoint(x: -2.6, y: 6 + d * 0.8))
            mouth.addQuadCurve(to: CGPoint(x: 5, y: 2.5), control: CGPoint(x: 2.4, y: 6 + d * 0.8))
            mouth.closeSubpath()
            fill(ctx, mouth, WrenColors.mouth)
            if open > 0.3 {
                ctx.saveGState()
                ctx.addPath(mouth); ctx.clip()
                let k = smooth(0.3, 0.8, open)
                fill(ctx, CGPath(ellipseIn: CGRect(x: tip * 0.6 - 3.4, y: 5 + d * 0.62, width: 6.8, height: 5 * k + 1),
                                 transform: nil), WrenColors.rgb(0xC25466))
                ctx.restoreGState()
            }
        }
        let upper = CGMutablePath()
        upper.move(to: CGPoint(x: -6.5, y: 0))
        upper.addQuadCurve(to: CGPoint(x: 6.5, y: 0), control: CGPoint(x: 0, y: -4.5))
        upper.addQuadCurve(to: CGPoint(x: tip, y: upperTip), control: CGPoint(x: 3 + t * 3, y: 6))
        upper.addQuadCurve(to: CGPoint(x: -6.5, y: 0), control: CGPoint(x: -3 + t * 3, y: 6))
        upper.closeSubpath()
        fillLinear(ctx, upper, [WrenColors.beakHi, WrenColors.beakLo], top: -4, bottom: 13)
        let shine = CGMutablePath()
        shine.move(to: CGPoint(x: -3, y: -1.2)); shine.addQuadCurve(to: CGPoint(x: 2.5, y: -1.4), control: CGPoint(x: 0, y: -2.6))
        stroke(ctx, shine, CGColor(gray: 1, alpha: 1), width: 1, alpha: 0.5)
    }

    // MARK: Helpers

    static func rad(_ degrees: Double) -> Double { degrees * .pi / 180 }

    static func smooth(_ a: Double, _ b: Double, _ x: Double) -> Double {
        let t = min(1, max(0, (x - a) / (b - a)))
        return t * t * (3 - 2 * t)
    }

    /// Shape inputs rounded to hundredths, so tiny spring wobble doesn't redraw a part.
    static func keys(_ values: Double...) -> [Int] { values.map { Int(($0 * 100).rounded()) } }

    private static var gradients: [String: CGGradient] = [:]
    private static let gradientLock = NSLock()

    static func gradient(_ colors: [CGColor], _ stops: [CGFloat]? = nil) -> CGGradient {
        let id = colors.map { "\($0.components ?? [])" }.joined() + "\(stops ?? [])"
        gradientLock.lock(); defer { gradientLock.unlock() }
        if let g = gradients[id] { return g }
        let g = CGGradient(colorsSpace: CGColorSpace(name: CGColorSpace.sRGB), colors: colors as CFArray, locations: stops)!
        gradients[id] = g
        return g
    }

    static func fillLinear(_ ctx: CGContext, _ path: CGPath, _ colors: [CGColor], top: Double, bottom: Double) {
        ctx.saveGState()
        ctx.addPath(path); ctx.clip()
        ctx.drawLinearGradient(gradient(colors), start: CGPoint(x: 0, y: top), end: CGPoint(x: 0, y: bottom),
                               options: [.drawsBeforeStartLocation, .drawsAfterEndLocation])
        ctx.restoreGState()
    }

    static func fill(_ ctx: CGContext, _ path: CGPath, _ color: CGColor) {
        ctx.addPath(path); ctx.setFillColor(color); ctx.fillPath()
    }

    static func stroke(_ ctx: CGContext, _ path: CGPath, _ color: CGColor, width: Double, alpha: Double = 1, cap: CGLineCap = .round) {
        ctx.saveGState()
        ctx.addPath(path)
        ctx.setStrokeColor(color.copy(alpha: color.alpha * CGFloat(alpha))!)
        ctx.setLineWidth(width); ctx.setLineCap(cap); ctx.setLineJoin(.round)
        ctx.strokePath()
        ctx.restoreGState()
    }

    /// An ellipse that fades to nothing at its edge: shadows, occlusion, light.
    static func softEllipse(_ ctx: CGContext, center: CGPoint, rx: Double, ry: Double, color: CGColor, alpha: Double,
                            rotation: Double = 0) {
        ctx.saveGState()
        ctx.translateBy(x: center.x, y: center.y)
        ctx.rotate(by: rad(rotation))
        ctx.scaleBy(x: rx, y: ry)
        let g = gradient([color.copy(alpha: alpha)!, color.copy(alpha: alpha * 0.55)!, color.copy(alpha: 0)!], [0, 0.45, 1])
        ctx.drawRadialGradient(g, startCenter: .zero, startRadius: 0, endCenter: .zero, endRadius: 1, options: [])
        ctx.restoreGState()
    }

    /// Figure units in the context's device pixels. Shadows ignore the transform, and count y up in bitmaps.
    private static func device(_ ctx: CGContext, _ amount: Double) -> Double {
        let m = ctx.ctm
        return amount * sqrt(abs(m.a * m.d - m.b * m.c))
    }

    /// A tapered stroke along a quadratic curve as a filled shape: thick in the middle, thin at the ends.
    static func taper(_ a: CGPoint, _ c: CGPoint, _ b: CGPoint, width: Double, end: Double) -> CGPath {
        let n = 14
        var left: [CGPoint] = [], right: [CGPoint] = []
        for i in 0...n {
            let t = Double(i) / Double(n)
            let x = pow(1 - t, 2) * a.x + 2 * (1 - t) * t * c.x + t * t * b.x
            let y = pow(1 - t, 2) * a.y + 2 * (1 - t) * t * c.y + t * t * b.y
            let dx = 2 * (1 - t) * (c.x - a.x) + 2 * t * (b.x - c.x)
            let dy = 2 * (1 - t) * (c.y - a.y) + 2 * t * (b.y - c.y)
            let len = max(hypot(dx, dy), 1e-6)
            let w = (end + (width - end) * sin(.pi * t)) / 2
            left.append(CGPoint(x: x - dy / len * w, y: y + dx / len * w))
            right.append(CGPoint(x: x + dy / len * w, y: y - dx / len * w))
        }
        let path = CGMutablePath()
        path.addLines(between: left + right.reversed())
        path.closeSubpath()
        return path
    }
}
