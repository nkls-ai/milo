// Milo's rig at one pose (WrenRig.swift): where every part sits and the outlines it draws, in figure space (a
// 200-unit box, ground at y 182, his middle at x 100, y down). WrenRig.qml turns this into GPU shapes; colours live
// there, from Theme.rig. Pure, so tests can check a pose without Qt.
//
// Transforms are CoreGraphics affines [a, b, c, d, tx, ty] (x' = a·x + c·y + tx, y' = b·x + d·y + ty). Outlines are
// SVG path strings. Shape inputs are rounded to hundredths first, like the Mac's part keys, so spring wobble in the
// last digits doesn't rebuild a path every frame.
import { smooth, clamp } from "./pose.mjs"

export const GROUND = 182
export const SCALE = 0.62            // points per figure unit in a 120 pt box
export const VIEW = { x: 100 - 60 / SCALE, y: GROUND - 107 / SCALE, size: 120 / SCALE }  // what a 120 pt box shows
export const BODY_TOP = 68
export const SCARF_Y = 131
const EYE_ANGLE = 30, EYE_HEIGHT = 111
const R = 52

export const rad = d => d * Math.PI / 180
const key = v => Math.round(v * 100) / 100

// MARK: Affines

export const IDENTITY = [1, 0, 0, 1, 0, 0]
export const translate = (x, y) => [1, 0, 0, 1, x, y]
export const scale = (x, y) => [x, 0, 0, y === undefined ? x : y, 0, 0]
export function rotate(r) { const c = Math.cos(r), s = Math.sin(r); return [c, s, -s, c, 0, 0] }

// `m` applied first, then `n` (CoreGraphics' m.concatenating(n)).
export function then(m, n) {
    return [m[0] * n[0] + m[1] * n[2], m[0] * n[1] + m[1] * n[3],
            m[2] * n[0] + m[3] * n[2], m[2] * n[1] + m[3] * n[3],
            m[4] * n[0] + m[5] * n[2] + n[4], m[4] * n[1] + m[5] * n[3] + n[5]]
}

// T(x, y), then turned by r, then scaled: the Mac's CGAffineTransform(translationX:y:).rotated(by:).scaledBy(x:y:).
export function place(x, y, r, sx, sy) {
    let m = translate(x, y)
    if (r) m = then(rotate(r), m)
    if (sx !== undefined) m = then(scale(sx, sy === undefined ? sx : sy), m)
    return m
}

// MARK: Paths

const n = v => { const s = (Math.round(v * 100) / 100).toString(); return s === "-0" ? "0" : s }

export class Path {
    constructor() { this.d = [] }
    M(x, y) { this.d.push("M" + n(x) + " " + n(y)); return this }
    L(x, y) { this.d.push("L" + n(x) + " " + n(y)); return this }
    Q(cx, cy, x, y) { this.d.push("Q" + n(cx) + " " + n(cy) + " " + n(x) + " " + n(y)); return this }
    C(ax, ay, bx, by, x, y) {
        this.d.push("C" + n(ax) + " " + n(ay) + " " + n(bx) + " " + n(by) + " " + n(x) + " " + n(y))
        return this
    }
    Z() { this.d.push("Z"); return this }
    ellipse(cx, cy, rx, ry) {
        return this.M(cx - rx, cy).arc(rx, ry, cx + rx, cy).arc(rx, ry, cx - rx, cy).Z()
    }
    arc(rx, ry, x, y) { this.d.push("A" + n(rx) + " " + n(ry) + " 0 1 0 " + n(x) + " " + n(y)); return this }
    rect(x, y, w, h) { return this.M(x, y).L(x + w, y).L(x + w, y + h).L(x, y + h).Z() }
    roundRect(x, y, w, h, r) {
        return this.M(x + r, y).L(x + w - r, y).Q(x + w, y, x + w, y + r).L(x + w, y + h - r)
            .Q(x + w, y + h, x + w - r, y + h).L(x + r, y + h).Q(x, y + h, x, y + h - r).L(x, y + r)
            .Q(x, y, x + r, y).Z()
    }
    poly(points) {
        if (!points.length) return this
        this.M(points[0][0], points[0][1])
        for (let i = 1; i < points.length; ++i) this.L(points[i][0], points[i][1])
        return this.Z()
    }
    toString() { return this.d.join(" ") }
}

// The part of the ellipse (rx, ry) about (0, 0) above the curve y = f(x) (or below it), as a polygon. Clips the eye's
// lids and the shadow they cast without a mask: the curve is a quadratic in x, so the cut is exact up to the
// ellipse's 72 sides, which are smaller than a pixel at any size Milo is drawn.
export function clipEllipse(rx, ry, f, below) {
    const N = 72
    const inside = q => below ? q[1] > f(q[0]) : q[1] < f(q[0])
    const pts = []
    for (let i = 0; i < N; ++i) pts.push([rx * Math.cos(2 * Math.PI * i / N), ry * Math.sin(2 * Math.PI * i / N)])
    const out = []
    let crossings = 0
    for (let i = 0; i < N; ++i) {
        const p = pts[i], q = pts[(i + 1) % N]
        const ip = inside(p), iq = inside(q)
        if (ip) out.push({ p })
        if (ip !== iq) {
            let lo = 0, hi = 1
            for (let k = 0; k < 14; ++k) {
                const mid = (lo + hi) / 2
                const m = [p[0] + (q[0] - p[0]) * mid, p[1] + (q[1] - p[1]) * mid]
                if (inside(m) === ip) lo = mid; else hi = mid
            }
            const t = (lo + hi) / 2
            out.push({ p: [p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t], exit: ip })
            crossings++
        }
    }
    if (!out.length) return []
    if (!crossings) return pts
    const polygon = []
    for (let i = 0; i < out.length; ++i) {
        const a = out[i], b = out[(i + 1) % out.length]
        polygon.push(a.p)
        if (a.exit === true && b.exit === false) {
            // along the curve from where the ellipse left the region to where it comes back
            for (let k = 1; k < 10; ++k) {
                const x = a.p[0] + (b.p[0] - a.p[0]) * k / 10
                polygon.push([x, f(x)])
            }
        }
    }
    return polygon
}

const scaled = (points, sx, sy) => points.map(p => [p[0] * sx, p[1] * sy])

function ellipsePoints(cx, cy, rx, ry) {
    const pts = []
    for (let i = 0; i < 48; ++i) pts.push([cx + rx * Math.cos(Math.PI * i / 24), cy + ry * Math.sin(Math.PI * i / 24)])
    return pts
}

function quadPoints(a, c, b) {
    const pts = []
    for (let i = 0; i <= 12; ++i) {
        const u = i / 12, v = 1 - u
        pts.push([v * v * a[0] + 2 * v * u * c[0] + u * u * b[0], v * v * a[1] + 2 * v * u * c[1] + u * u * b[1]])
    }
    return pts
}

// His outline as a polygon, fine enough that its corners stay under a pixel.
export function bodyPolygon(t, scarfUp) {
    const top = BODY_TOP + scarfUp * 2
    const xr = 160 + Math.max(t, 0) * 5, xl = 40 + Math.min(t, 0) * 5
    const segments = [
        [[100 + t * 9, top], [137 + t * 6, top], [xr, top + 30], [xr, 130]],
        [[xr, 130], [xr, 162], [136, 180], [100, 180]],
        [[100, 180], [64, 180], [xl, 162], [xl, 130]],
        [[xl, 130], [xl, top + 30], [63 + t * 8, top], [100 + t * 9, top]],
    ]
    const pts = []
    for (const [a, b, c, d] of segments) {
        for (let i = 0; i < 18; ++i) {
            const u = i / 18, v = 1 - u
            pts.push([v * v * v * a[0] + 3 * v * v * u * b[0] + 3 * v * u * u * c[0] + u * u * u * d[0],
                      v * v * v * a[1] + 3 * v * v * u * b[1] + 3 * v * u * u * c[1] + u * u * u * d[1]])
        }
    }
    return pts
}

function insideConvex(q, polygon) {
    let sign = 0
    for (let i = 0; i < polygon.length; ++i) {
        const a = polygon[i], b = polygon[(i + 1) % polygon.length]
        const cross = (b[0] - a[0]) * (q[1] - a[1]) - (b[1] - a[1]) * (q[0] - a[0])
        if (cross === 0) continue
        if (sign === 0) sign = Math.sign(cross)
        else if (Math.sign(cross) !== sign) return false
    }
    return true
}

// A soft ellipse (RigSoft draws a radius-50 circle scaled to rx, ry and turned) cut to `polygon`: the outline in
// that circle's own space.
export function softClip(cx, cy, rx, ry, degrees, polygon) {
    const r = rad(-degrees), c = Math.cos(r), s = Math.sin(r)
    const local = polygon.map(q => {
        const x = q[0] - cx, y = q[1] - cy
        return [(c * x - s * y) * 50 / rx, (s * x + c * y) * 50 / ry]
    })
    return new Path().poly(clipConvex(ellipsePoints(0, 0, 50, 50), local)).toString()
}

// `subject` cut to the convex polygon `clip` (Sutherland-Hodgman).
export function clipConvex(subject, clip) {
    let area = 0
    for (let i = 0; i < clip.length; ++i) {
        const a = clip[i], b = clip[(i + 1) % clip.length]
        area += a[0] * b[1] - b[0] * a[1]
    }
    const sign = area > 0 ? 1 : -1
    let out = subject
    for (let i = 0; i < clip.length && out.length; ++i) {
        const a = clip[i], b = clip[(i + 1) % clip.length]
        const side = q => sign * ((b[0] - a[0]) * (q[1] - a[1]) - (b[1] - a[1]) * (q[0] - a[0])) >= 0
        const cross = (p, q) => {
            const d1 = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
            const d2 = (b[0] - a[0]) * (q[1] - a[1]) - (b[1] - a[1]) * (q[0] - a[0])
            const t = d1 / (d1 - d2)
            return [p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t]
        }
        const input = out
        out = []
        for (let j = 0; j < input.length; ++j) {
            const p = input[j], q = input[(j + 1) % input.length]
            if (side(p)) out.push(p)
            if (side(p) !== side(q)) out.push(cross(p, q))
        }
    }
    return out
}

// MARK: The frame

// Everything WrenRig.qml draws for pose `p`: groups, parts and their outlines.
export function frame(p, small) {
    const t = key(p.turn)
    const th = t * 50
    const fx = a => 100 + R * Math.sin(rad(a))
    const flight = smooth(0.3, 0.7, p.fly)
    const f = {}

    // Ground shadow: shrinks and fades as he rises; gone while he flies between windows.
    const lift = p.lift + p.fly * 16
    const ss = Math.max(0.35, 1 - lift / 70)
    f.shadow = { m: place(100, GROUND + 1, 0, ss), opacity: (1 - flight) * (0.4 + 0.6 * ss) }

    // Feet
    const feet = new Path()
    for (const x of [87 + t * 8, 113 + t * 8]) {
        feet.M(x, 174).L(x, 181).M(x - 5, 182).L(x, 180.5).L(x + 5.5, 182).M(x, 180.5).L(x + 1.4, 182.6)
    }
    f.feet = { path: feet.toString(), width: small ? 3.2 : 2.4, opacity: p.feet * (1 - flight) }

    // Tail: one barred feather fan cocked up behind his back, on the side he faces away from.
    const back = t > 0.02 ? -1 : 1
    const L = key(64 * (1 - p.fly * 0.3))
    const w = Math.round((7.5 + Math.max(p.tailFan, p.fly) * 3.5) * 4) / 4
    const tail = new Path().M(-w * 0.5, 0).C(-w * 0.75, -L * 0.45, -w - 1.2, -L * 0.78, -w, -L + 2)
    for (const cx of [-w * 0.33, w * 0.33, w]) tail.Q(cx - w * 0.36, -L - 3.2, cx, -L - 0.6)
    tail.C(w + 1.2, -L * 0.78, w * 0.75, -L * 0.45, w * 0.5, 0).Z()
    const bars = new Path()
    // kept a little inside the fan's edge: the Mac clips them to it
    for (const y of [0.56, 0.7, 0.84]) bars.M(-w * 0.76, -L * y + 1.8).Q(0, -L * y - 1.6, w * 0.76, -L * y + 1.8)
    f.tail = {
        m: place(100 + back * (30 + Math.abs(t) * 34), 152, rad(back * (27 + p.tail * 0.8 + Math.abs(t) * 10 + p.fly * 42))),
        path: tail.toString(), top: -L - 3, bottom: 0, bars: bars.toString(),
        shine: new Path().M(-w + 2, -L + 6).Q(0, -L - 1, w - 3, -L + 5).toString(),
    }

    // Wings: each a folded wing and an open one, cross-faded as it opens so the shape never swaps. Turned far
    // enough, the far wing slips behind him; open, it shows behind the body instead.
    const far = t > 0.05 ? "R" : t < -0.05 ? "L" : ""
    const farHidden = smooth(0.2, 0.3, Math.abs(t))
    for (const side of ["L", "R"]) {
        const s = side === "L" ? -1 : 1
        const angle = side === "L" ? p.wingL : p.wingR
        const open = Math.max(p.fly, side === "L" ? p.openL : p.openR)
        // the open wing is solid before the folded one fades, so the swap never shows through him
        const shown = smooth(0.2, 0.5, open)
        const folded = 1 - smooth(0.45, 0.75, open)
        const x = (side === "L" ? 48 : 152) + t * 20
        const isFar = far === side
        f["fold" + side] = {
            m: place(x, 127, rad(-s * (angle + open * 80)), 0.82, 0.8),
            opacity: folded * (isFar ? 1 - farHidden : 1), z: 4,
        }
        f["open" + side] = { m: place(x, 123, rad(-s * (angle - (1 - open) * 80))), opacity: shown, z: isFar ? 2 : 4 }
    }

    // Body, belly, shading and the scarf band: drawn by WrenBody.qml from these.
    const scarfUp = key(p.scarfUp)
    const top = BODY_TOP + scarfUp * 2
    const sy = SCARF_Y - scarfUp * 4
    // Everything inside him is cut to his outline here (he is convex), so no layer or mask is needed to draw him.
    const outline = bodyPolygon(t, scarfUp)
    const inside = q => insideConvex(q, outline)
    const cut = pts => new Path().poly(clipConvex(pts, outline)).toString()
    const bandPts = quadPoints([34, sy - 6], [100, sy + 8], [166, sy - 6])
        .concat(quadPoints([166, sy + 3], [100, sy + 18], [34, sy + 3]))
    const keyLight = [76 + t * 8, top + 16]
    f.body = {
        path: bodyPath(t, scarfUp),
        // lifted a little to the light: the gradient's middle, figure space
        light: [84 + t * 12, 98],
        belly: cut(ellipsePoints(100 + 52 * Math.sin(rad(th * 0.75)), 155, 37 - Math.abs(t) * 4, 31)),
        // ambient occlusion where he meets the ground, and the key light on his crown, as soft ellipses cut to him
        occlusion: softClip(100, 190, 78, 30, 0, outline),
        keyLight: keyLight,
        keyLightPath: softClip(keyLight[0], keyLight[1], 24, 12, -24, outline),
        fluff: small ? "" : (() => {
            const fluff = new Path()
            for (const [x, y, fw] of [[86, 81, 5], [114, 81, 5], [92, 87, 4.4], [108, 87, 4.4], [100, 84, 4]]) {
                const cx = x + t * 12
                fluff.M(cx - fw / 2, y).Q(cx, y + 2.6, cx + fw / 2, y)
            }
            return fluff.toString()
        })(),
        scarfY: sy,
        band: cut(bandPts),
        // the shadow the band casts on him, 2.5 below it
        bandShadow: cut(bandPts.map(q => [q[0], q[1] + 2.5])),
        ribs: small ? "" : (() => {
            const ribs = new Path()
            for (let i = 0; i <= 16; ++i) {
                const x = 44 + i * 7
                const y = sy - 6 + (1 - Math.pow((x - 100) / 66, 2)) * 7
                if (inside([x, y + 2]) && inside([x + 0.5, y + 8.5])) ribs.M(x, y + 2).L(x + 0.5, y + 8.5)
            }
            return ribs.toString()
        })(),
        edge: (() => {
            const pts = quadPoints([34, sy - 6], [100, sy + 8], [166, sy - 6]).filter(inside)
            return pts.length > 1 ? new Path().poly(pts).toString().replace(/ Z$/, "") : ""
        })(),
        // fluffy cheeks: two feather points poking out at each side of his face, in his own colours
        tufts: (() => {
            const tufts = new Path()
            for (const side of [-1, 1]) {
                const edge = side < 0 ? 40.6 + Math.min(t, 0) * 5 : 159.4 + Math.max(t, 0) * 5
                for (const [y, len] of [[109, 4.2], [117, 3.6]]) {
                    tufts.M(edge - side * 2, y - 4).Q(edge + side * len * 0.7, y - 2.5, edge + side * len, y + 1.5)
                        .Q(edge + side * 0.6, y + 2.6, edge - side * 2, y + 4).Z()
                }
            }
            return tufts.toString()
        })(),
    }

    // The scarf's loose end, swinging from the knot, and the knot over it
    const knotX = fx(th + 32)
    const knotY = sy + 6 + (1 - Math.pow((knotX - 100) / 60, 2)) * 2
    const E = key(25 * (1 + p.scarfToss * 0.25))
    const end = new Path().M(-5, 0).C(-5.8, E * 0.4, -6.8, E * 0.8, -7, E).Q(0, E + 3, 7, E + 1.5)
        .C(6, E * 0.7, 5.4, E * 0.35, 5, 0).Z()
    const fringe = new Path()
    for (const x of [-5, -1.7, 1.7, 5]) fringe.M(x, E + 1.5).L(x * 1.08, E + 5)
    f.scarfEnd = {
        m: place(knotX, knotY, rad(-12 + p.scarf + p.scarfToss * -118 + p.fly * -70)),
        path: end.toString(), bottom: E + 2,
        ribs: new Path().M(-1.8, 4).L(-2.4, E - 1).M(2, 4).L(2.4, E).toString(), fringe: fringe.toString(),
    }
    f.knot = { m: translate(knotX, knotY) }

    // Meeting notes: a little notepad held up in front of his belly, and the pencil writing on it.
    const pad = clamp(p.pad, 0, 1)
    f.pad = { shown: p.pad > 0.005, opacity: smooth(0.05, 0.45, pad) }
    if (f.pad.shown) {
        const padM = place(97 + t * 18, 160 + (1 - pad) * 16, rad(-5 + t * 6), 0.7 + 0.3 * pad)
        // the tip moves along the pad's third line; the pencil leans away from his face
        const pen = clamp(p.pen, -1.2, 1.2)
        f.pad.m = padM
        f.pencil = { m: then(place(2 + pen * 10, 7.2 - Math.abs(pen) * 0.8, rad(38 + pen * 4), 1.15), padM),
                     opacity: f.pad.opacity * smooth(0.5, 0.9, pad) }
    }

    // Face
    const gx = p.gazeX * 4.5, gy = p.gazeY * 3.5
    const eyeY = EYE_HEIGHT + gy - p.scarfUp * 3
    const eyes = [["L", th - EYE_ANGLE], ["R", th + EYE_ANGLE]]
    const bodyCenter = [84 + t * 12, 98]
    f.blush = {
        opacity: Math.min(1, p.blush),
        spots: eyes.map(([side, a]) => ({ x: fx(a + (side === "L" ? -10 : 10)) + gx, y: eyeY + 12,
                                          rx: 6 * Math.cos(rad(a)) + 3, ry: 5 })),
    }
    for (const [side, a] of eyes) {
        const s = side === "L" ? -1 : 1
        const x = fx(a) + gx
        const fore = key(Math.max(0.35, Math.cos(rad(a))))
        // the lid only starts covering the eye past its rest value (0.2), so at rest his eyes are wide open
        const lid = key(Math.max(0, ((side === "L" ? p.lidL : p.lidR) - 0.2) / 0.8))
        const lower = key(side === "L" ? p.lowerL : p.lowerR)
        const es = key((side === "L" ? p.eyeL : p.eyeR) * (small ? 1.3 : 1))
        const look = [Math.round(p.gazeX * 10) / 10, Math.round(p.gazeY * 10) / 10]
        f["eye" + side] = Object.assign({ m: translate(x, eyeY), z: side === "L" ? 1 : 2 },
                                        eye(lid, lower, fore * es, es, look, [bodyCenter[0] - x, bodyCenter[1] - eyeY]))
        // Brow: a short soft mark in a deeper lavender, high over the eye.
        const raise = (side === "L" ? p.browL : p.browR) * 4.5
        const tilt = (side === "L" ? p.browTiltL : p.browTiltR) * 16 * s
        f["brow" + side] = {
            m: place(x + s * 1.5, eyeY - 20 - raise, rad(tilt)), z: side === "L" ? 3 : 4,
            path: new Path().M(-4.2 * fore, 1).Q(0, -2.4, 4.2 * fore, 1).toString(),
            width: small ? 4 : 3, alpha: small ? 0.8 : 0.7,
        }
    }
    // Beak: small, low between the eyes; the tip swings toward the turn.
    const tip = key(t * 9 + p.gazeX * 2)
    // in twentieths: finer steps don't show
    const open = Math.round(clamp(p.beak, 0, 1) * 20) / 20
    f.beak = Object.assign({ m: place(fx(th) + gx * 1.1, EYE_HEIGHT + 7 + gy - p.scarfUp * 3, 0, 0.9, 0.7) },
                           beak(open, tip, t))

    // The groups: the body leans, lifts, squashes and breathes about his feet; the face tilts about its middle.
    const pivot = [100, GROUND]
    const breathe = p.breath * 0.012
    const about = (m, x, y) => then(then(translate(-x, -y), m), translate(x, y))
    const squash = about(scale(1 - p.squash * 0.6 - breathe * 0.3, 1 + p.squash + breathe), pivot[0], pivot[1])
    const tilt = about(rotate(rad(p.lean)), pivot[0], pivot[1])
    f.bodyM = then(then(squash, tilt), translate(0, -lift))
    const fp = [fx(th), EYE_HEIGHT + 4]
    f.faceM = then(then(translate(-fp[0], -fp[1]), rotate(rad(p.headTilt))), translate(fp[0] + p.headX, fp[1] + p.headY))

    // Crest: a fluffy tuft of three feathers rooted in his crown. It turns with his head, perks up and lies back
    // with his mood, and sways behind every move.
    const perk = Math.round(clamp(p.crest, -1, 1) * 10) / 10
    const laid = Math.max(0, -perk), up = Math.max(0, perk)
    f.crest = {
        m: then(place(100 + t * 14, BODY_TOP + 11, rad(p.crestSway + back * laid * 40 + t * 12), 1, 1 - laid * 0.3), f.faceM),
        path: crestPath(up),
        shine: small ? "" : new Path().M(-1.5, -10).Q(-3.4, -19, 0.5, -27 - up * 6).toString(),
    }
    return f
}

// MARK: Shapes

export function bodyPath(t, scarfUp) {
    const top = BODY_TOP + scarfUp * 2
    const xr = 160 + Math.max(t, 0) * 5, xl = 40 + Math.min(t, 0) * 5
    return new Path().M(100 + t * 9, top).C(137 + t * 6, top, xr, top + 30, xr, 130).C(xr, 162, 136, 180, 100, 180)
        .C(64, 180, xl, 162, xl, 130).C(xl, top + 30, 63 + t * 8, top, 100 + t * 9, top).Z().toString()
}

// The tuft: three soft feathers fanning up from one root at (0, 0). `perk` 0...1 spreads and lifts them.
export function crestPath(perk) {
    const path = new Path()
    for (const [angle, length, fw] of [[-32, 25, 10], [-6, 33, 12], [22, 22, 9.5]]) {
        const L = length * (1 + perk * 0.2)
        const m = rotate(rad(angle * (1 + perk * 0.3)))
        const at = (x, y) => [m[0] * x + m[2] * y, m[1] * x + m[3] * y]
        const c1 = at(fw * 0.75, -L * 0.3), c2 = at(fw * 0.7, -L * 0.85), e = at(fw * 0.2, -L)
        const d1 = at(-fw * 0.45, -L * 0.8), d2 = at(-fw * 0.6, -L * 0.3)
        path.M(0, 0).C(c1[0], c1[1], c2[0], c2[1], e[0], e[1]).C(d1[0], d1[1], d2[0], d2[1], 0, 0).Z()
    }
    return path.toString()
}

export function foldedWing(s, L) {
    const path = new Path().M(2 * s, -5).C(-9 * s, -5, -15 * s, 8, -15 * s, L * 0.42)
        .C(-15 * s, L * 0.72, -9 * s, L * 0.9, -4 * s, L).C(4 * s, L * 0.82, 11 * s, L * 0.6, 11 * s, L * 0.36)
        .C(11 * s, 8, 10 * s, -5, 2 * s, -5).Z()
    const bars = new Path()
    ;[0.56, 0.7, 0.84].forEach((k, i) => bars.M(-12 * s + i * 2.5 * s, L * k).Q(-4 * s, L * k + 2.6, 5 * s - i * 2.5 * s, L * k - 1.5))
    return { path: path.toString(), bars: bars.toString(), top: -5, bottom: L }
}

export function openWing(s, k) {
    const q = (x, y) => [s * x * k, y * k]
    const P = new Path()
    const go = (op, ...xy) => { const pts = []; for (let i = 0; i < xy.length; i += 2) pts.push(...q(xy[i], xy[i + 1])); P[op](...pts) }
    go("M", 0, -6); go("C", 16, -16, 40, -24, 62, -20); go("Q", 68, -17, 62, -12); go("Q", 66, -8, 58, -5)
    go("Q", 61, 0, 52, 1); go("Q", 54, 6, 44, 6); go("Q", 44, 11, 34, 10); go("C", 22, 10, 8, 9, 0, 6); P.Z()
    const bars = new Path()
    for (const [a, b, c, e] of [[30, -14, 32, 7], [42, -17, 44, 3], [52, -18, 53, 0]]) {
        bars.M(...q(a, b)).L(...q(c, e))
    }
    const edge = new Path().M(...q(4, -6)).C(...q(18, -14), ...q(40, -21), ...q(60, -19))
    return { path: P.toString(), bars: bars.toString(), edge: edge.toString(), top: -24 * k, bottom: 11 * k }
}

// The eye about (0, 0): lids from 0 open to 1 shut, the lower lid pushing up into a smile, squeezed by (sx, sy).
// Outlines are in the eye's unsqueezed space, so the lids can paint with the body's own gradient (`bodyCenter`)
// and vanish into him at rest.
export function eye(lid, lower, sx, sy, look, bodyCenter) {
    const rx = 9.2, ry = 10.4
    const yl = -ry + lid * ry * 2.1
    const sag = -1.6 + 5 * lid * lid
    const yb = ry - lower * ry * 1.25
    const smile = smooth(0.7, 0.9, lower)
    const S = (x, y) => [x * sx, y * sy]
    // y of the upper lid's edge across x (a quadratic from (-12, y0) through (0, y0 + sag) to (12, y0))
    const curve = (y0, dip) => x => y0 + dip * (1 - (x / 12) * (x / 12)) / 2
    const poly = pts => new Path().poly(scaled(pts, sx, sy)).toString()
    const ellipse = (cx, cy, erx, ery) => new Path().ellipse(cx * sx, cy * sy, erx * sx, ery * sy).toString()
    const e = { smile, lid, lower, open: lid < 0.97, bodyCenter, sx, sy }
    e.ball = ellipse(0, 0, rx, ry)
    e.ballCenter = S(0, ry * 0.7)
    e.ballRadius = ry * 1.5 * sy
    // a soft sheen across the lower half, then the key catchlight and a small second one
    e.sheen = { x: -1 * sx, y: 5 * sy, rx: 6.5 * sx, ry: 3.6 * sy }
    e.catchlight = ellipse(2.6 + look[0] * 0.7, -3.4 + look[1] * 0.6, 3.8, 3.8)
    e.second = ellipse(-3.3, 3.9, 1.7, 1.7)
    e.glint = ellipse(-3.6 + look[0] * 0.5 + 0.75, -5.6 + look[1] * 0.4 + 0.75, 0.75, 0.75)
    // the shadow the upper lid casts on the eye
    e.lidShadow = poly(clipEllipse(rx, ry, curve(yl + 1.6, sag), false))
    // lids, clipped to an ellipse a little bigger than the eye
    const bigger = [rx + 1.2, ry + 1.2]
    e.upper = poly(clipEllipse(bigger[0], bigger[1], curve(yl, sag), false))
    e.lowerLid = lower > 0.001 ? poly(clipEllipse(bigger[0], bigger[1], curve(yb + 3, -9), true)) : ""
    if (lid > 0.04) {
        const closed = Math.min(yl, ry - 0.5)
        e.lidLine = new Path().M(...S(-rx - 0.4, closed)).Q(...S(0, closed + sag), ...S(rx + 0.4, closed)).toString()
        e.lidWidth = lid > 0.95 ? 2.1 : 1.1
        e.lidAlpha = lid > 0.95 ? 1 : 0.6 + 0.4 * smooth(0.5, 0.95, lid)
    } else {
        e.lidLine = ""
    }
    if (lower > 0.3) {
        e.lowerLine = new Path().M(...S(-rx + 0.5, yb + 2.6)).Q(...S(0, yb - 5.6), ...S(rx - 0.5, yb + 2.6)).toString()
        e.lowerWidth = 1 + 0.8 * smooth(0.4, 0.8, lower)
        e.lowerAlpha = 0.5 + 0.4 * smooth(0.4, 0.8, lower)
    } else {
        e.lowerLine = ""
    }
    // smiling: a clean arch
    e.arch = new Path().M(...S(-7.6, 4.8)).Q(...S(0, -6), ...S(7.6, 4.8)).toString()
    return e
}

// The beak: a short upper bill pointing down at the viewer, the lower bill swinging down below it to open the
// mouth. Open, the upper bill lifts a touch and shortens, as the head tips back to speak.
export function beak(open, tip, t) {
    const d = open * 11
    const b = { open, d }
    if (open > 0.03) {
        b.lower = new Path().M(-6, 3 + d * 0.4).Q(-2.8, 8.5 + d, tip * 0.8 - 0.4, 10.5 + d).Q(2.6, 8.5 + d, 6, 3 + d * 0.4).Z().toString()
        b.mouth = new Path().M(-5, 2.5).Q(-2.6, 6 + d * 0.8, tip * 0.8 - 0.3, 8.2 + d * 0.86).Q(2.4, 6 + d * 0.8, 5, 2.5).Z().toString()
        // a hint of tongue once it is properly open, inside the mouth
        if (open > 0.3) {
            const k = smooth(0.3, 0.8, open)
            const end = [tip * 0.8 - 0.3, 8.2 + d * 0.86]
            const mouth = quadPoints([-5, 2.5], [-2.6, 6 + d * 0.8], end)
                .concat(quadPoints(end, [2.4, 6 + d * 0.8], [5, 2.5]).slice(1))
            const th = 5 * k + 1
            b.tongue = new Path().poly(clipConvex(ellipsePoints(tip * 0.6, 5 + d * 0.62 + th / 2, 3.4, th / 2), mouth)).toString()
        }
    }
    b.upper = new Path().M(-6.5, 0).Q(0, -4.5, 6.5, 0).Q(3 + t * 3, 6, tip, 13 - open * 3).Q(-3 + t * 3, 6, -6.5, 0).Z().toString()
    b.shine = new Path().M(-3, -1.2).Q(0, -2.6, 2.5, -1.4).toString()
    return b
}

export function notepad() {
    const lines = new Path()
    for (const y of [-2, 3.5, 9]) lines.M(-16, y).L(16, y)
    // what he wrote so far: loopy lines of handwriting
    const words = new Path()
    for (const [y, end] of [[-3.6, 13], [1.9, 6]]) {
        words.M(-15, y)
        let x = -15
        while (x < end) {
            words.Q(x + 1.1, y - 2.6, x + 2.2, y)
            x += 2.2
            if (Math.trunc(x * 10) % 9 === 0) { x += 1.6; words.M(x, y) }
        }
    }
    const rings = new Path()
    for (let x = -15; x <= 15; x += 6) rings.ellipse(x, -14.2, 1.3, 2.4)
    // the cover's edge along the top, in his own lavender: the paper's top band with its rounded corners
    const cover = new Path().M(-21, -8).L(-21, -10.5).Q(-21, -14, -17.5, -14).L(17.5, -14).Q(21, -14, 21, -10.5).L(21, -8).Z()
    return { paper: new Path().roundRect(-21, -14, 42, 29, 3.5).toString(), cover: cover.toString(),
             lines: lines.toString(), words: words.toString(), rings: rings.toString() }
}

export function pencil() {
    const w = 2.6
    return {
        shaft: new Path().rect(-w, -24, w * 2, 18).toString(),
        facet: new Path().M(0.6, -23.5).L(0.6, -6.5).toString(),
        wood: new Path().M(-w, -6).L(w, -6).L(0, 0).Z().toString(),
        lead: new Path().M(-0.9, -2.1).L(0.9, -2.1).L(0, 0.2).Z().toString(),
        ferrule: new Path().rect(-w, -27, w * 2, 3).toString(),
        eraser: new Path().roundRect(-w, -31, w * 2, 4.6, 1.6).toString(),
    }
}
