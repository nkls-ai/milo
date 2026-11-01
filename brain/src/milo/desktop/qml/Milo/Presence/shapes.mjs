// Outlines of the surfaces next to Milo, as SVG paths in a w × h box (WorkingEdge, CursorArrow).

const n = v => (Math.round(v * 100) / 100).toString()

// A rounded rectangle, inset by `i` (a hairline sits half a point in, like SwiftUI's strokeBorder).
export function roundRect(w, h, r, i = 0) {
    r = Math.max(0, Math.min(r - i, (w - 2 * i) / 2, (h - 2 * i) / 2))
    const x0 = i, y0 = i, x1 = w - i, y1 = h - i
    const a = " A" + n(r) + " " + n(r) + " 0 0 1 "
    return "M" + n(x0 + r) + " " + n(y0) + " L" + n(x1 - r) + " " + n(y0) + a + n(x1) + " " + n(y0 + r)
        + " L" + n(x1) + " " + n(y1 - r) + a + n(x1 - r) + " " + n(y1) + " L" + n(x0 + r) + " " + n(y1)
        + a + n(x0) + " " + n(y1 - r) + " L" + n(x0) + " " + n(y0 + r) + a + n(x0 + r) + " " + n(y0) + " Z"
}

// A classic arrow pointer in a w × h box, tip at the top left (CursorArrow).
export function arrow(w, h) {
    const p = [[0, 0], [0, 0.74], [0.27, 0.56], [0.44, 0.95], [0.62, 0.88], [0.45, 0.5], [0.72, 0.47]]
    return p.map((q, k) => (k ? "L" : "M") + n(q[0] * w) + " " + n(q[1] * h)).join(" ") + " Z"
}
