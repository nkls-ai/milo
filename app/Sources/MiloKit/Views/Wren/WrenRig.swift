import CoreGraphics
import Foundation

/// Milo's colours, from the design page (protocol/design.json, through DesignTokens.swift).
enum WrenColors {
    static let bodyHi = rgb(DesignTokens.Rig.bodyHi), bodyMid = rgb(DesignTokens.Rig.bodyMid), bodyLo = rgb(DesignTokens.Rig.bodyLo)
    static let lidLine = rgb(DesignTokens.Rig.lidLine)
    static let bellyHi = rgb(DesignTokens.Rig.bellyHi), bellyLo = rgb(DesignTokens.Rig.bellyLo)
    static let brow = rgb(DesignTokens.Rig.brow), crestHi = rgb(DesignTokens.Rig.crestHi), crestLo = rgb(DesignTokens.Rig.crestLo), fluff = rgb(DesignTokens.Rig.fluff)
    static let wingHi = rgb(DesignTokens.Rig.wingHi), wingLo = rgb(DesignTokens.Rig.wingLo), wingBar = rgb(DesignTokens.Rig.wingBar)
    static let tail = rgb(DesignTokens.Rig.tail), tailLo = rgb(DesignTokens.Rig.tailLo), tailBar = rgb(DesignTokens.Rig.tailBar)
    static let eye = rgb(DesignTokens.Rig.eye), eyeHi = rgb(DesignTokens.Rig.eyeHi)
    static let beakHi = rgb(DesignTokens.Rig.beakHi), beakLo = rgb(DesignTokens.Rig.beakLo), mouth = rgb(DesignTokens.Rig.mouth)
    static let scarfHi = rgb(DesignTokens.Rig.scarfHi), scarfLo = rgb(DesignTokens.Rig.scarfLo), scarfRib = rgb(DesignTokens.Rig.scarfRib), scarfEdge = rgb(DesignTokens.Rig.scarfEdge)
    static let feet = rgb(DesignTokens.Rig.feet), blush = rgb(DesignTokens.Rig.blush)
    static let paperHi = rgb(DesignTokens.Rig.paperHi), paperLo = rgb(DesignTokens.Rig.paperLo), paperLine = rgb(DesignTokens.Rig.paperLine), writing = rgb(DesignTokens.Rig.writing)
    static let pencil = rgb(DesignTokens.Rig.pencil), pencilLo = rgb(DesignTokens.Rig.pencilLo), wood = rgb(DesignTokens.Rig.wood), lead = rgb(DesignTokens.Rig.lead)
    static let eraser = rgb(DesignTokens.Rig.eraser), ferrule = rgb(DesignTokens.Rig.ferrule)
    static let shade = rgb(DesignTokens.Rig.shade), ground = rgb(DesignTokens.Rig.ground), rim = rgb(DesignTokens.Rig.rim)
    static let ink = rgb(DesignTokens.Rig.ink)

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
        case shadow, feet, tail, crest, wingFoldL, wingOpenL, wingFoldR, wingOpenR, body, scarfEnd, knot
        case blush, eyeL, eyeR, browL, browR, beak
        case notepad, pencil
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
    /// Where the scarf's band sits on him, figure y.
    static let scarfY = 131.0
    /// Eyes: how far round his face from the middle (degrees) and how high, figure y.
    static let eyeAngle = 30.0, eyeHeight = 111.0

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
        let tailL = 64 * (1 - p.fly * 0.3)
        let tailW = ((7.5 + max(p.tailFan, p.fly) * 3.5) * 4).rounded() / 4
        let tailAngle = back * (27 + p.tail * 0.8 + abs(t) * 10 + p.fly * 42)
        parts.append(WrenPart(id: .tail, box: CGRect(x: -16, y: -tailL - 8, width: 32, height: tailL + 12),
                              key: keys(tailL, tailW, small ? 1 : 0), draw: { ctx in
            drawTail(ctx, length: tailL, width: tailW, small: small)
        }, transform: CGAffineTransform(translationX: 100 + back * (30 + abs(t) * 34), y: 152).rotated(by: rad(tailAngle)), z: 1))

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
            let x = (side == "L" ? 48 : 152) + t * 20
            let isFar = far == side
            parts.append(WrenPart(id: side == "L" ? .wingFoldL : .wingFoldR, box: CGRect(x: -18, y: -8, width: 36, height: 56),
                                  key: keys(s, small ? 1 : 0), draw: { ctx in
                drawFoldedWing(ctx, side: s, length: 42, small: small)
            }, transform: CGAffineTransform(translationX: x, y: 127).rotated(by: rad(-s * (angle + open * 80))).scaledBy(x: 0.82, y: 0.8),
               opacity: folded * (isFar ? 1 - farHidden : 1), z: 4))
            let flap = -s * (angle - (1 - open) * 80)
            parts.append(WrenPart(id: side == "L" ? .wingOpenL : .wingOpenR, box: CGRect(x: -60, y: -24, width: 120, height: 36),
                                  key: keys(s, small ? 1 : 0), draw: { ctx in
                drawOpenWing(ctx, side: s, k: 0.72, small: small)
            }, transform: CGAffineTransform(translationX: x, y: 123).rotated(by: rad(flap)), opacity: shown, z: isFar ? 2 : 4))
        }

        // Body, belly, shading and the scarf band
        parts.append(WrenPart(id: .body, box: CGRect(x: 32, y: 60, width: 136, height: 126),
                              key: keys(t, p.scarfUp, small ? 1 : 0), draw: { ctx in
            drawBody(ctx, turn: t, scarfUp: p.scarfUp, small: small)
        }, z: 3))

        // The scarf's loose end, swinging from the knot, and the knot over it
        let sy = Self.scarfY - p.scarfUp * 4
        let knotX = fx(th + 32)
        let knotY = sy + 6 + (1 - pow((knotX - 100) / 60, 2)) * 2
        let endLen = 25 * (1 + p.scarfToss * 0.25)
        let endAngle = -12 + p.scarf + p.scarfToss * -118 + p.fly * -70
        parts.append(WrenPart(id: .scarfEnd, box: CGRect(x: -12, y: -4, width: 24, height: endLen + 12),
                              key: keys(endLen, small ? 1 : 0), draw: { ctx in
            drawScarfEnd(ctx, length: endLen, small: small)
        }, transform: CGAffineTransform(translationX: knotX, y: knotY).rotated(by: rad(endAngle)), z: 5))
        parts.append(WrenPart(id: .knot, box: CGRect(x: -10, y: -8, width: 20, height: 16), key: [], draw: { ctx in
            let knot = CGPath(ellipseIn: CGRect(x: -6.5, y: -5.5, width: 13, height: 11), transform: nil)
            fillLinear(ctx, knot, [WrenColors.scarfHi, WrenColors.scarfLo], top: -5.5, bottom: 5.5)
            let crease = CGMutablePath()
            crease.move(to: CGPoint(x: -4, y: -0.8)); crease.addQuadCurve(to: CGPoint(x: 4, y: -0.8), control: CGPoint(x: 0, y: 1.6))
            stroke(ctx, crease, WrenColors.scarfLo, width: 1.2, alpha: 0.7)
        }, transform: CGAffineTransform(translationX: knotX, y: knotY), z: 6))

        // Meeting notes: a little notepad held up in front of his belly, and the pencil writing on it.
        if p.pad > 0.005 {
            let pad = min(1, max(0, p.pad))
            let shown = smooth(0.05, 0.45, pad)
            let cx = 97 + t * 18, cy = 160 + (1 - pad) * 16
            let padTransform = CGAffineTransform(translationX: cx, y: cy).rotated(by: rad(-5 + t * 6))
                .scaledBy(x: 0.7 + 0.3 * pad, y: 0.7 + 0.3 * pad)
            parts.append(WrenPart(id: .notepad, box: CGRect(x: -24, y: -19, width: 48, height: 40),
                                  key: keys(small ? 1 : 0), draw: { ctx in
                drawNotepad(ctx, small: small)
            }, transform: padTransform, opacity: shown, z: 8))
            // The tip moves along the pad's third line; the pencil leans away from his face.
            let pen = min(1.2, max(-1.2, p.pen))
            let tip = CGPoint(x: 2 + pen * 10, y: 7.2 - abs(pen) * 0.8)
            parts.append(WrenPart(id: .pencil, box: CGRect(x: -4, y: -32, width: 30, height: 36), key: keys(small ? 1 : 0),
                                  draw: { ctx in
                drawPencil(ctx, small: small)
            }, transform: CGAffineTransform(translationX: tip.x, y: tip.y).rotated(by: rad(38 + pen * 4)).scaledBy(x: 1.15, y: 1.15)
                .concatenating(padTransform),
               opacity: shown * smooth(0.5, 0.9, pad), z: 9))
        }

        // Face
        var face: [WrenPart] = []
        let gx = p.gazeX * 4.5, gy = p.gazeY * 3.5
        let eyeY = Self.eyeHeight + gy - p.scarfUp * 3
        let eyes: [(Character, Double)] = [("L", th - Self.eyeAngle), ("R", th + Self.eyeAngle)]
        let bodyCenter = CGPoint(x: 84 + t * 12, y: 98)
        if p.blush > 0.01 {
            let spots = eyes.map { side, a in
                (CGPoint(x: fx(a + (side == "L" ? -10 : 10)) + gx, y: eyeY + 12), 6 * cos(rad(a)))
            }
            face.append(WrenPart(id: .blush, box: CGRect(x: 40, y: 90, width: 120, height: 40), key: keys(t, gx, gy), draw: { ctx in
                for (c, rx) in spots { softEllipse(ctx, center: c, rx: rx + 3, ry: 5, color: WrenColors.blush, alpha: 0.7) }
            }, opacity: min(1, p.blush), z: 0))
        }
        for (side, a) in eyes {
            let s = side == "L" ? -1.0 : 1.0
            let x = fx(a) + gx
            let fore = max(0.35, cos(rad(a)))
            // the lid only starts covering the eye past its rest value (0.2), so at rest his eyes are wide open
            let lid = max(0, ((side == "L" ? p.lidL : p.lidR) - 0.2) / 0.8)
            let lower = side == "L" ? p.lowerL : p.lowerR
            let es = (side == "L" ? p.eyeL : p.eyeR) * (small ? 1.3 : 1)
            let center = CGPoint(x: x, y: eyeY)
            let catchlight = CGPoint(x: (p.gazeX * 10).rounded() / 10, y: (p.gazeY * 10).rounded() / 10)
            face.append(WrenPart(id: side == "L" ? .eyeL : .eyeR, box: CGRect(x: -16, y: -17, width: 32, height: 34),
                                 key: keys(lid, lower, es, fore, catchlight.x, catchlight.y, t),
                                 draw: { ctx in
                drawEye(ctx, lid: lid, lower: lower, sx: fore * es, sy: es, look: catchlight,
                        bodyCenter: CGPoint(x: bodyCenter.x - center.x, y: bodyCenter.y - center.y))
            }, transform: CGAffineTransform(translationX: x, y: eyeY), z: side == "L" ? 1 : 2))

            // Brow: a short soft mark in a deeper lavender, high over the eye.
            let raise = (side == "L" ? p.browL : p.browR) * 4.5
            let tilt = (side == "L" ? p.browTiltL : p.browTiltR) * 16 * s
            face.append(WrenPart(id: side == "L" ? .browL : .browR, box: CGRect(x: -24, y: -10, width: 48, height: 20),
                                 key: keys(s, fore), draw: { ctx in
                let arc = CGMutablePath()
                arc.move(to: CGPoint(x: -4.2 * fore, y: 1))
                arc.addQuadCurve(to: CGPoint(x: 4.2 * fore, y: 1), control: CGPoint(x: 0, y: -2.4))
                stroke(ctx, arc, WrenColors.brow, width: small ? 4 : 3, alpha: small ? 0.8 : 0.7)
            }, transform: CGAffineTransform(translationX: x + s * 1.5, y: eyeY - 20 - raise).rotated(by: rad(tilt)), z: side == "L" ? 3 : 4))
        }
        // Beak: small, low between the eyes; the tip swings toward the turn.
        let bx = fx(th) + gx * 1.1, by = Self.eyeHeight + 7 + gy - p.scarfUp * 3
        let tip = t * 9 + p.gazeX * 2
        // in twentieths: finer steps don't show, and each step redraws the beak
        let open = (min(1, max(0, p.beak)) * 20).rounded() / 20
        face.append(WrenPart(id: .beak, box: CGRect(x: -12, y: -8, width: 24, height: 30),
                             key: keys(open, tip, t), draw: { ctx in
            drawBeak(ctx, open: open, tip: tip, turn: t)
        }, transform: CGAffineTransform(translationX: bx, y: by).scaledBy(x: 0.9, y: 0.7), z: 5))

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
        let facePivot = CGPoint(x: fx(th), y: Self.eyeHeight + 4)
        let faceTransform = CGAffineTransform(translationX: facePivot.x + p.headX, y: facePivot.y + p.headY)
            .rotated(by: rad(p.headTilt))
            .translatedBy(x: -facePivot.x, y: -facePivot.y)
        // Crest: a fluffy tuft of three feathers rooted in his crown. It turns with his head, perks up and
        // lies back with his mood, and sways behind every move.
        let perk = (min(1, max(-1, p.crest)) * 10).rounded() / 10
        let laid = max(0, -perk), up = max(0, perk)
        let crownX = 100 + t * 14
        let crestAngle = p.crestSway + back * laid * 40 + t * 12
        parts.append(WrenPart(id: .crest, box: CGRect(x: -30, y: -46, width: 60, height: 52),
                              key: keys(up, small ? 1 : 0), draw: { ctx in
            fillLinear(ctx, crestPath(perk: up), [WrenColors.crestLo, WrenColors.crestHi], top: -40, bottom: -4)
            guard !small else { return }
            let shine = CGMutablePath()
            shine.move(to: CGPoint(x: -1.5, y: -10)); shine.addQuadCurve(to: CGPoint(x: 0.5, y: -27 - up * 6), control: CGPoint(x: -3.4, y: -19))
            stroke(ctx, shine, CGColor(gray: 1, alpha: 1), width: 1, alpha: 0.35)
        }, transform: CGAffineTransform(translationX: crownX, y: Self.bodyTop + 11)
            .rotated(by: rad(crestAngle)).scaledBy(x: 1, y: 1 - laid * 0.3)
            .concatenating(faceTransform),
           z: 2))

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

    /// A small spiral notepad centred on (0, 0), cream paper with lavender lines, the top two already written.
    private static func drawNotepad(_ ctx: CGContext, small: Bool) {
        let paper = CGPath(roundedRect: CGRect(x: -21, y: -14, width: 42, height: 29), cornerWidth: 3.5,
                           cornerHeight: 3.5, transform: nil)
        ctx.saveGState()
        ctx.setShadow(offset: CGSize(width: 0, height: -device(ctx, 1.5)), blur: device(ctx, 3),
                      color: WrenColors.shade.copy(alpha: 0.35))
        fill(ctx, paper, WrenColors.paperHi)
        ctx.restoreGState()
        fillLinear(ctx, paper, [WrenColors.paperHi, WrenColors.paperLo], top: -14, bottom: 16)
        // the cover's edge along the top, in his own lavender, so it stands apart from the scarf above it
        let cover = CGPath(rect: CGRect(x: -21, y: -14, width: 42, height: 6), transform: nil)
        ctx.saveGState()
        ctx.addPath(paper); ctx.clip()
        fillLinear(ctx, cover, [WrenColors.wingHi, WrenColors.wingLo], top: -14, bottom: -8)
        ctx.restoreGState()
        stroke(ctx, paper, WrenColors.paperLine, width: 1, alpha: 0.6)
        guard !small else { return }
        let lines = CGMutablePath()
        for y in [-2.0, 3.5, 9.0] {
            lines.move(to: CGPoint(x: -16, y: y)); lines.addLine(to: CGPoint(x: 16, y: y))
        }
        stroke(ctx, lines, WrenColors.paperLine, width: 0.8, alpha: 0.7)
        // what he wrote so far: loopy lines of handwriting
        let words = CGMutablePath()
        for (y, end) in [(-3.6, 13.0), (1.9, 6.0)] {
            words.move(to: CGPoint(x: -15, y: y))
            var x = -15.0
            while x < end {
                words.addQuadCurve(to: CGPoint(x: x + 2.2, y: y), control: CGPoint(x: x + 1.1, y: y - 2.6))
                x += 2.2
                if Int(x * 10) % 9 == 0 { x += 1.6; words.move(to: CGPoint(x: x, y: y)) }
            }
        }
        stroke(ctx, words, WrenColors.writing, width: 0.9, alpha: 0.75)
        // the spiral's rings
        let rings = CGMutablePath()
        for x in stride(from: -15.0, through: 15.0, by: 6) {
            rings.addEllipse(in: CGRect(x: x - 1.3, y: -16.6, width: 2.6, height: 4.8))
        }
        stroke(ctx, rings, WrenColors.paperHi, width: 1.1)
    }

    /// A pencil with its tip at (0, 0), pointing down, the eraser end up. Rotated into place by the caller.
    private static func drawPencil(_ ctx: CGContext, small: Bool) {
        let w = 2.6
        let shaft = CGPath(rect: CGRect(x: -w, y: -24, width: w * 2, height: 18), transform: nil)
        fillLinear(ctx, shaft, [WrenColors.pencil, WrenColors.pencilLo], top: -24, bottom: -6)
        if !small {
            let facet = CGMutablePath()
            facet.move(to: CGPoint(x: 0.6, y: -23.5)); facet.addLine(to: CGPoint(x: 0.6, y: -6.5))
            stroke(ctx, facet, WrenColors.pencilLo, width: 0.8, alpha: 0.6)
        }
        let wood = CGMutablePath()
        wood.move(to: CGPoint(x: -w, y: -6)); wood.addLine(to: CGPoint(x: w, y: -6)); wood.addLine(to: CGPoint(x: 0, y: 0))
        wood.closeSubpath()
        fill(ctx, wood, WrenColors.wood)
        let lead = CGMutablePath()
        lead.move(to: CGPoint(x: -0.9, y: -2.1)); lead.addLine(to: CGPoint(x: 0.9, y: -2.1)); lead.addLine(to: CGPoint(x: 0, y: 0.2))
        lead.closeSubpath()
        fill(ctx, lead, WrenColors.lead)
        fill(ctx, CGPath(rect: CGRect(x: -w, y: -27, width: w * 2, height: 3), transform: nil), WrenColors.ferrule)
        fill(ctx, CGPath(roundedRect: CGRect(x: -w, y: -31, width: w * 2, height: 4.6), cornerWidth: 1.6, cornerHeight: 1.6,
                         transform: nil), WrenColors.eraser)
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

    /// The top of his head, figure y. He is a little wider than tall, like a sparrow fluffed up in the cold.
    static let bodyTop = 68.0

    /// The tuft: three soft feathers fanning up from one root at (0, 0). `perk` 0...1 spreads and lifts them.
    static func crestPath(perk: Double) -> CGPath {
        let path = CGMutablePath()
        let feathers: [(angle: Double, length: Double, width: Double)] = [(-32, 25, 10), (-6, 33, 12), (22, 22, 9.5)]
        for f in feathers {
            let L = f.length * (1 + perk * 0.2), w = f.width
            let feather = CGMutablePath()
            feather.move(to: .zero)
            feather.addCurve(to: CGPoint(x: w * 0.2, y: -L), control1: CGPoint(x: w * 0.75, y: -L * 0.3),
                             control2: CGPoint(x: w * 0.7, y: -L * 0.85))
            feather.addCurve(to: .zero, control1: CGPoint(x: -w * 0.45, y: -L * 0.8), control2: CGPoint(x: -w * 0.6, y: -L * 0.3))
            feather.closeSubpath()
            path.addPath(feather, transform: CGAffineTransform(rotationAngle: rad(f.angle * (1 + perk * 0.3))))
        }
        return path
    }

    static func bodyPath(turn t: Double, scarfUp: Double) -> CGPath {
        let top = bodyTop + scarfUp * 2
        let xr = 160 + max(t, 0) * 5, xl = 40 + min(t, 0) * 5
        let path = CGMutablePath()
        path.move(to: CGPoint(x: 100 + t * 9, y: top))
        path.addCurve(to: CGPoint(x: xr, y: 130), control1: CGPoint(x: 137 + t * 6, y: top), control2: CGPoint(x: xr, y: top + 30))
        path.addCurve(to: CGPoint(x: 100, y: 180), control1: CGPoint(x: xr, y: 162), control2: CGPoint(x: 136, y: 180))
        path.addCurve(to: CGPoint(x: xl, y: 130), control1: CGPoint(x: 64, y: 180), control2: CGPoint(x: xl, y: 162))
        path.addCurve(to: CGPoint(x: 100 + t * 9, y: top), control1: CGPoint(x: xl, y: top + 30), control2: CGPoint(x: 63 + t * 8, y: top))
        path.closeSubpath()
        return path
    }

    /// The body's gradient, in figure space, so lids can paint with the same colours and vanish into him.
    static func bodyGradient(_ ctx: CGContext, center: CGPoint) {
        ctx.drawRadialGradient(gradient([WrenColors.bodyHi, WrenColors.bodyMid, WrenColors.bodyLo], [0, 0.5, 1]),
                               startCenter: center, startRadius: 0, endCenter: center, endRadius: 108,
                               options: [.drawsAfterEndLocation])
    }

    private static func drawBody(_ ctx: CGContext, turn t: Double, scarfUp: Double, small: Bool) {
        let th = t * 50
        let body = bodyPath(turn: t, scarfUp: scarfUp)
        let top = bodyTop + scarfUp * 2
        ctx.saveGState()
        ctx.addPath(body); ctx.clip()
        bodyGradient(ctx, center: CGPoint(x: 84 + t * 12, y: 98))
        // belly
        let bellyX = 100 + 52 * sin(rad(th * 0.75))
        let brx = 37 - abs(t) * 4
        let belly = CGPath(ellipseIn: CGRect(x: bellyX - brx, y: 124, width: brx * 2, height: 62), transform: nil)
        fillLinear(ctx, belly, [WrenColors.bellyHi, WrenColors.bellyLo], top: 124, bottom: 186)
        // ambient occlusion where he meets the ground, and the key light on his crown
        softEllipse(ctx, center: CGPoint(x: 100, y: 190), rx: 78, ry: 30, color: WrenColors.shade, alpha: 0.26)
        softEllipse(ctx, center: CGPoint(x: 76 + t * 8, y: top + 16), rx: 24, ry: 12, color: CGColor(gray: 1, alpha: 1),
                    alpha: 0.36, rotation: -24)
        if !small {
            // soft feather ticks around his crown, so his head isn't a bare ball
            let fluff = CGMutablePath()
            for (x, y, w) in [(86.0, 81.0, 5.0), (114, 81, 5), (92, 87, 4.4), (108, 87, 4.4), (100, 84, 4)] {
                let cx = x + t * 12
                fluff.move(to: CGPoint(x: cx - w / 2, y: y))
                fluff.addQuadCurve(to: CGPoint(x: cx + w / 2, y: y), control: CGPoint(x: cx, y: y + 2.6))
            }
            stroke(ctx, fluff, WrenColors.fluff, width: 1.1, alpha: 0.32)
        }
        // scarf band, with the soft shadow it casts on him
        let sy = scarfY - scarfUp * 4
        let band = CGMutablePath()
        band.move(to: CGPoint(x: 34, y: sy - 6))
        band.addQuadCurve(to: CGPoint(x: 166, y: sy - 6), control: CGPoint(x: 100, y: sy + 8))
        band.addLine(to: CGPoint(x: 166, y: sy + 3))
        band.addQuadCurve(to: CGPoint(x: 34, y: sy + 3), control: CGPoint(x: 100, y: sy + 18))
        band.closeSubpath()
        ctx.saveGState()
        ctx.setShadow(offset: CGSize(width: 0, height: -device(ctx, 2.5)), blur: device(ctx, 4), color: WrenColors.shade.copy(alpha: 0.3))
        fillLinear(ctx, band, [WrenColors.scarfHi, WrenColors.scarfLo], top: sy - 4, bottom: sy + 12)
        ctx.restoreGState()
        fillLinear(ctx, band, [WrenColors.scarfHi, WrenColors.scarfLo], top: sy - 4, bottom: sy + 12)
        if !small {
            let ribs = CGMutablePath()
            for i in 0...16 {
                let x = 44 + Double(i) * 7
                let y = sy - 6 + (1 - pow((x - 100) / 66, 2)) * 7
                ribs.move(to: CGPoint(x: x, y: y + 2)); ribs.addLine(to: CGPoint(x: x + 0.5, y: y + 8.5))
            }
            stroke(ctx, ribs, WrenColors.scarfRib, width: 1, alpha: 0.4)
        }
        let edge = CGMutablePath()
        edge.move(to: CGPoint(x: 34, y: sy - 6)); edge.addQuadCurve(to: CGPoint(x: 166, y: sy - 6), control: CGPoint(x: 100, y: sy + 8))
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
        // fluffy cheeks: two little feather points poking out at each side of his face, in his own colours
        let tufts = CGMutablePath()
        for side in [-1.0, 1.0] {
            let edge = side < 0 ? 40.6 + min(t, 0) * 5 : 159.4 + max(t, 0) * 5
            for (y, len) in [(109.0, 4.2), (117.0, 3.6)] {
                tufts.move(to: CGPoint(x: edge - side * 2, y: y - 4))
                tufts.addQuadCurve(to: CGPoint(x: edge + side * len, y: y + 1.5), control: CGPoint(x: edge + side * len * 0.7, y: y - 2.5))
                tufts.addQuadCurve(to: CGPoint(x: edge - side * 2, y: y + 4), control: CGPoint(x: edge + side * 0.6, y: y + 2.6))
                tufts.closeSubpath()
            }
        }
        ctx.saveGState()
        ctx.addPath(tufts); ctx.clip()
        bodyGradient(ctx, center: CGPoint(x: 84 + t * 12, y: 98))
        ctx.restoreGState()
    }

    private static func drawScarfEnd(_ ctx: CGContext, length E: Double, small: Bool) {
        let path = CGMutablePath()
        path.move(to: CGPoint(x: -5, y: 0))
        path.addCurve(to: CGPoint(x: -7, y: E), control1: CGPoint(x: -5.8, y: E * 0.4), control2: CGPoint(x: -6.8, y: E * 0.8))
        path.addQuadCurve(to: CGPoint(x: 7, y: E + 1.5), control: CGPoint(x: 0, y: E + 3))
        path.addCurve(to: CGPoint(x: 5, y: 0), control1: CGPoint(x: 6, y: E * 0.7), control2: CGPoint(x: 5.4, y: E * 0.35))
        path.closeSubpath()
        fillLinear(ctx, path, [WrenColors.scarfHi, WrenColors.scarfLo], top: 0, bottom: E + 2)
        let crease = CGMutablePath()
        crease.move(to: CGPoint(x: -6, y: 0)); crease.addLine(to: CGPoint(x: 6, y: 0))
        stroke(ctx, crease, WrenColors.shade, width: 2, alpha: 0.18, cap: .butt)
        guard !small else { return }
        let ribs = CGMutablePath()
        ribs.move(to: CGPoint(x: -1.8, y: 4)); ribs.addLine(to: CGPoint(x: -2.4, y: E - 1))
        ribs.move(to: CGPoint(x: 2, y: 4)); ribs.addLine(to: CGPoint(x: 2.4, y: E))
        stroke(ctx, ribs, WrenColors.scarfRib, width: 1, alpha: 0.5)
        let fringe = CGMutablePath()
        for x in [-5.0, -1.7, 1.7, 5] {
            fringe.move(to: CGPoint(x: x, y: E + 1.5)); fringe.addLine(to: CGPoint(x: x * 1.08, y: E + 5))
        }
        stroke(ctx, fringe, WrenColors.scarfLo, width: 1.5)
    }

    private static func drawEye(_ ctx: CGContext, lid: Double, lower: Double, sx: Double, sy: Double, look: CGPoint,
                                bodyCenter: CGPoint) {
        let rx = 9.2, ry = 10.4
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
                // a soft sheen across the lower half, then the key catchlight and a small second one
                softEllipse(ctx, center: CGPoint(x: -1, y: 5), rx: 6.5, ry: 3.6, color: WrenColors.rgb(DesignTokens.Rig.sheen), alpha: 0.35)
                fill(ctx, CGPath(ellipseIn: CGRect(x: 2.6 + look.x * 0.7 - 3.8, y: -3.4 + look.y * 0.6 - 3.8, width: 7.6, height: 7.6), transform: nil),
                     CGColor(gray: 1, alpha: 1))
                fill(ctx, CGPath(ellipseIn: CGRect(x: -5, y: 2.2, width: 3.4, height: 3.4), transform: nil), CGColor(gray: 1, alpha: 0.85))
                fill(ctx, CGPath(ellipseIn: CGRect(x: -3.6 + look.x * 0.5, y: -5.6 + look.y * 0.4, width: 1.5, height: 1.5), transform: nil),
                     CGColor(gray: 1, alpha: 0.7))
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
                lids.move(to: CGPoint(x: -12, y: 13)); lids.addLine(to: CGPoint(x: -12, y: yb + 3))
                lids.addQuadCurve(to: CGPoint(x: 12, y: yb + 3), control: CGPoint(x: 0, y: yb - 6))
                lids.addLine(to: CGPoint(x: 12, y: 13)); lids.closeSubpath()
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
            arch.move(to: CGPoint(x: -7.6, y: 4.8)); arch.addQuadCurve(to: CGPoint(x: 7.6, y: 4.8), control: CGPoint(x: 0, y: -6))
            stroke(ctx, arch, WrenColors.eye, width: 3, alpha: smile)
        }
        ctx.restoreGState()
    }

    private static func lidPath(yl: Double, sag: Double) -> CGPath {
        let path = CGMutablePath()
        path.move(to: CGPoint(x: -12, y: -13)); path.addLine(to: CGPoint(x: 12, y: -13)); path.addLine(to: CGPoint(x: 12, y: yl))
        path.addQuadCurve(to: CGPoint(x: -12, y: yl), control: CGPoint(x: 0, y: yl + sag))
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
                                 transform: nil), WrenColors.rgb(DesignTokens.Rig.tongue))
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
