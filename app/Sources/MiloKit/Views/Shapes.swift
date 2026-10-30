import SwiftUI

/// A curve: `up` bows upward (∩, used for happy eyes and frowns), otherwise downward (∪, a small smile).
struct ArcShape: Shape {
    var up: Bool
    func path(in r: CGRect) -> Path {
        var p = Path()
        p.move(to: CGPoint(x: r.minX, y: up ? r.maxY : r.minY))
        p.addQuadCurve(to: CGPoint(x: r.maxX, y: up ? r.maxY : r.minY),
                       control: CGPoint(x: r.midX, y: up ? r.minY - r.height : r.maxY + r.height))
        return p
    }
}

struct SmileShape: Shape {
    func path(in r: CGRect) -> Path {
        var p = Path()
        p.move(to: CGPoint(x: r.minX, y: r.minY))
        p.addLine(to: CGPoint(x: r.maxX, y: r.minY))
        p.addQuadCurve(to: CGPoint(x: r.minX, y: r.minY), control: CGPoint(x: r.midX, y: r.maxY + r.height * 0.9))
        return p
    }
}

struct WavyShape: Shape {
    func path(in r: CGRect) -> Path {
        var p = Path()
        p.move(to: CGPoint(x: r.minX, y: r.midY))
        p.addCurve(to: CGPoint(x: r.maxX, y: r.midY),
                   control1: CGPoint(x: r.minX + r.width / 3, y: r.minY),
                   control2: CGPoint(x: r.minX + 2 * r.width / 3, y: r.maxY))
        return p
    }
}
