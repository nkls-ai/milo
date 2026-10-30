import AppKit
import QuartzCore
import SwiftUI

/// A motion that repeats forever: breathing, a floating "z", a puff of smoke. Keys are poses at fractions of
/// the period, the first at 0 and the last at 1 (make them equal for a seamless loop).
struct Loop: Equatable {
    struct Key: Equatable {
        /// 0...1 through the period.
        var at: Double
        var dx = 0.0, dy = 0.0
        var sx = 1.0, sy = 1.0
        /// Degrees, clockwise.
        var angle = 0.0
        var opacity = 1.0
    }

    var period: Double
    var keys: [Key]
    /// What scaling and turning keep in place, in the looping view's own frame.
    var pivot = UnitPoint.center
    /// Eased between keys (smooth) or not (linear).
    var smooth = true
    /// Seconds into the loop at time zero, so copies of one loop can run out of step.
    var phase = 0.0

    /// Slow vertical breathing around `pivot`: taller by `amount` at the top of the breath.
    static func breath(period: Double, amount: Double, pivot: UnitPoint = .bottom, phase: Double = 0) -> Loop {
        Loop(period: period, keys: [Key(at: 0, sx: 1 + amount * 0.3, sy: 1 - amount),
                                    Key(at: 0.5, sx: 1 - amount * 0.3, sy: 1 + amount),
                                    Key(at: 1, sx: 1 + amount * 0.3, sy: 1 - amount)],
             pivot: pivot, phase: phase)
    }

    /// Bobs up and down by `height` points.
    static func float(period: Double, height: Double, phase: Double = 0) -> Loop {
        Loop(period: period, keys: [Key(at: 0, dy: height / 2), Key(at: 0.5, dy: -height / 2), Key(at: 1, dy: height / 2)],
             phase: phase)
    }

    /// The pose at `time` seconds, for renders and for tests.
    func key(at time: Double) -> Key {
        guard let first = keys.first, let last = keys.last, period > 0 else { return Key(at: 0) }
        let t = ((time + phase) / period).truncatingRemainder(dividingBy: 1)
        let f = t < 0 ? t + 1 : t
        guard let upper = keys.firstIndex(where: { $0.at >= f }) else { return last }
        guard upper > 0 else { return first }
        let a = keys[upper - 1], b = keys[upper]
        var u = b.at > a.at ? (f - a.at) / (b.at - a.at) : 1
        if smooth { u = u * u * (3 - 2 * u) }
        func mix(_ x: Double, _ y: Double) -> Double { x + (y - x) * u }
        return Key(at: f, dx: mix(a.dx, b.dx), dy: mix(a.dy, b.dy), sx: mix(a.sx, b.sx), sy: mix(a.sy, b.sy),
                   angle: mix(a.angle, b.angle), opacity: mix(a.opacity, b.opacity))
    }
}

/// Runs `loop` on `content`. On screen Core Animation plays it, so it costs Milo no CPU between pose changes:
/// SwiftUI redraws a figure only when something about it changes. With `frozen` (renders, which can't show
/// Core Animation) the pose at `time` is drawn instead. A nil loop shows the content as it is.
struct Looping<Content: View>: View {
    var loop: Loop?
    var frozen: Bool
    var time: Double
    var content: Content

    init(_ loop: Loop?, frozen: Bool, time: Double, @ViewBuilder content: () -> Content) {
        self.loop = loop
        self.frozen = frozen
        self.time = time
        self.content = content()
    }

    var body: some View {
        if let loop {
            if frozen {
                let k = loop.key(at: time)
                content
                    .scaleEffect(x: k.sx, y: k.sy, anchor: loop.pivot)
                    .rotationEffect(.degrees(k.angle), anchor: loop.pivot)
                    .offset(x: k.dx, y: k.dy)
                    .opacity(k.opacity)
            } else {
                LoopHost(loop: loop, content: content)
            }
        } else {
            content
        }
    }
}

/// The content in its own hosting view, whose layer carries the loop as Core Animation keyframes.
private struct LoopHost<Content: View>: NSViewRepresentable {
    var loop: Loop
    var content: Content

    func makeNSView(context: Context) -> LoopView<Content> { LoopView(content: content) }

    func updateNSView(_ view: LoopView<Content>, context: Context) {
        view.host.rootView = content
        view.loop = loop
    }
}

final class LoopView<Content: View>: NSView {
    let host: NSHostingView<Content>
    var loop: Loop? {
        didSet { if loop != oldValue { animate() } }
    }
    private var animatedSize = CGSize.zero

    init(content: Content) {
        host = NSHostingView(rootView: content)
        host.sizingOptions = []
        super.init(frame: .zero)
        wantsLayer = true
        host.wantsLayer = true
        addSubview(host)
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) { fatalError("init(coder:) is not used") }

    override var isFlipped: Bool { true }
    /// Clicks and drags go to whatever is behind, as if the loop weren't there.
    override func hitTest(_ point: NSPoint) -> NSView? { nil }

    override func layout() {
        super.layout()
        host.frame = bounds
        if bounds.size != animatedSize { animate() }
    }

    override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()
        animate()
    }

    private func animate() {
        guard let layer = host.layer else { return }
        // SwiftUI may hand over a new loop before the first layout; the keyframes need the real size.
        if host.frame != bounds { host.frame = bounds }
        layer.removeAnimation(forKey: "loop.transform")
        layer.removeAnimation(forKey: "loop.opacity")
        animatedSize = bounds.size
        guard let loop, loop.keys.count > 1, loop.period > 0, bounds.width > 0, window != nil,
              !NSWorkspace.shared.accessibilityDisplayShouldReduceMotion else { return }
        let transforms = loop.keys.map { NSValue(caTransform3D: transform($0, pivot: loop.pivot)) }
        let times = loop.keys.map { NSNumber(value: $0.at) }
        let timing = CAMediaTimingFunction(name: loop.smooth ? .easeInEaseOut : .linear)
        let segments = Array(repeating: timing, count: loop.keys.count - 1)

        let moves = CAKeyframeAnimation(keyPath: "transform")
        moves.values = transforms
        let opacity = CAKeyframeAnimation(keyPath: "opacity")
        opacity.values = loop.keys.map { NSNumber(value: $0.opacity) }
        for (animation, key) in [(moves, "loop.transform"), (opacity, "loop.opacity")] {
            animation.keyTimes = times
            animation.timingFunctions = segments
            animation.duration = loop.period
            animation.repeatCount = .infinity
            animation.timeOffset = loop.phase.truncatingRemainder(dividingBy: loop.period)
            animation.isRemovedOnCompletion = false
            layer.add(animation, forKey: key)
        }
    }

    /// The host layer's transform for one key. Turning and scaling happen around the layer's anchor, so they
    /// are shifted to keep `pivot` in place. Offsets and angles are in this view's flipped space, as in SwiftUI:
    /// +y is down and a positive angle turns clockwise.
    func transform(_ k: Loop.Key, pivot unit: UnitPoint) -> CATransform3D {
        guard let layer = host.layer else { return CATransform3DIdentity }
        let size = host.frame.size
        // Where the anchor and the pivot sit, in this view's coordinates (y down).
        let anchor = layerYDown ? layer.position : CGPoint(x: layer.position.x, y: bounds.height - layer.position.y)
        let pivot = CGPoint(x: host.frame.minX + unit.x * size.width, y: host.frame.minY + unit.y * size.height)
        // Layer space may have y up; flip the y parts if so.
        let y: CGFloat = layerYDown ? 1 : -1
        let d = CGPoint(x: pivot.x - anchor.x, y: (pivot.y - anchor.y) * y)
        var t = CATransform3DMakeTranslation(d.x + k.dx, d.y + k.dy * y, 0)
        t = CATransform3DRotate(t, y * k.angle * .pi / 180, 0, 0, 1)
        t = CATransform3DScale(t, k.sx, k.sy, 1)
        return CATransform3DTranslate(t, -d.x, -d.y, 0)
    }

    /// Whether this view's layer, the host layer's parent, counts y downward.
    private var layerYDown: Bool { layer?.isGeometryFlipped ?? false }
}
