import CoreGraphics
import Foundation

/// How Milo's cursor moves: a short eased glide, quicker for short hops, along a slight curve so it reads as
/// a hand moving and not a jump.
enum CursorGlide {
    /// Seconds for a glide over `distance` points.
    static func duration(_ distance: CGFloat) -> TimeInterval {
        min(0.6, max(0.18, 0.16 + Double(distance) / 2600))
    }

    /// The point a fraction `t` (0...1) of the way, eased out, bowed a little to the side.
    static func point(from start: CGPoint, to end: CGPoint, at t: Double) -> CGPoint {
        let s = 1 - pow(1 - min(1, max(0, t)), 3)
        let dx = end.x - start.x, dy = end.y - start.y
        let bow = min(40, hypot(dx, dy) * 0.08) * CGFloat(sin(.pi * s))
        let length = max(hypot(dx, dy), 0.001)
        return CGPoint(x: start.x + dx * s - dy / length * bow, y: start.y + dy * s + dx / length * bow)
    }

    /// Where a hidden cursor appears before gliding to `target`: a little up and to the left of it.
    static func entry(for target: CGPoint) -> CGPoint {
        CGPoint(x: target.x - 70, y: target.y + 50)
    }
}
