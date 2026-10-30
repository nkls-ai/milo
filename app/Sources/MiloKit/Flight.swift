import CoreGraphics
import Foundation

/// Where Milo is between his corner and a spot he points at. Directions are unit vectors in view
/// coordinates: x right, y down.
public enum Flight: Equatable, Sendable {
    case perched
    case flying(heading: CGVector)
    case pointing(toward: CGVector)

    var airborne: Bool {
        if case .perched = self { false } else { true }
    }
}

/// Where Milo sits to point at something, and his path there. AppKit screen coordinates, y up.
enum FlightPlan {
    /// How far his centre sits from the target: about the length of his body plus an outstretched wing.
    static let reach: CGFloat = 84
    /// Room he needs around his centre to stay on screen.
    static let margin: CGFloat = 64

    /// His centre while he points at `target`, and the direction he points in (view coordinates).
    /// He sits to the right of the target and a little below, so his bubble, which hangs above and to the
    /// left of him, doesn't cover it. Near the right edge he sits on the left instead.
    static func perch(pointingAt target: CGPoint, within screen: CGRect) -> (center: CGPoint, toward: CGVector) {
        var center = CGPoint(x: target.x + reach, y: target.y - 14)
        if center.x + margin > screen.maxX { center.x = target.x - reach }
        center.x = min(max(center.x, screen.minX + margin), screen.maxX - margin)
        center.y = min(max(center.y, screen.minY + margin), screen.maxY - margin)
        return (center, direction(from: center, to: target))
    }

    /// A unit vector in view coordinates from one AppKit point to another.
    static func direction(from a: CGPoint, to b: CGPoint) -> CGVector {
        let dx = b.x - a.x, dy = b.y - a.y
        let length = hypot(dx, dy)
        guard length > 0.001 else { return CGVector(dx: -1, dy: 0) }
        return CGVector(dx: dx / length, dy: -dy / length)
    }

    /// Seconds for a flight over `distance` points: short hops feel quick, crossing a screen stays calm.
    static func duration(_ distance: CGFloat) -> TimeInterval {
        min(1.5, max(0.55, 0.45 + Double(distance) / 1600))
    }

    /// The point a fraction `t` (0...1) along the way, on a gentle upward arc, eased in and out.
    static func point(from start: CGPoint, to end: CGPoint, at t: Double) -> CGPoint {
        let s = ease(min(1, max(0, t)))
        let lift = min(80, hypot(end.x - start.x, end.y - start.y) * 0.16)
        let control = CGPoint(x: (start.x + end.x) / 2, y: max(start.y, end.y) + lift)
        let u = 1 - s
        return CGPoint(x: u * u * start.x + 2 * u * s * control.x + s * s * end.x,
                       y: u * u * start.y + 2 * u * s * control.y + s * s * end.y)
    }

    static func ease(_ t: Double) -> Double {
        t < 0.5 ? 4 * t * t * t : 1 - pow(-2 * t + 2, 3) / 2
    }

    /// Converts a point from global top-left coordinates (CGEvent, screenshots) to AppKit's, whose origin
    /// is the bottom-left of the primary display.
    static func appKit(_ point: CGPoint, primaryHeight: CGFloat) -> CGPoint {
        CGPoint(x: point.x, y: primaryHeight - point.y)
    }
}
