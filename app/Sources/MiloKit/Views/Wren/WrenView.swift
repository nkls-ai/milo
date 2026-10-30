import AppKit
import Combine
import QuartzCore
import SwiftUI

/// Milo, live. Each part of the rig is its own Core Animation layer: moving, turning and squashing him
/// only changes layer transforms, and a part is redrawn only when its shape changes (a blink redraws the
/// eyes, speech the beak). Frames run only while something moves; at rest the display link stops and
/// Core Animation breathes him on its own, outside the process.
final class WrenView: NSView {
    private var director = WrenDirector(seed: .random(in: 0...UInt64.max))
    private var motion = WrenMotion()
    private var input: FigureInput?
    var small = false
    /// The live mic or voice level, read here rather than through SwiftUI: it changes 20 times a second.
    private var levels: AnyCancellable?
    private var level: Double?

    private let stage = CALayer()
    private let breath = CALayer()
    private let body = CALayer()
    private let face = CALayer()
    private var parts: [WrenPart.ID: CALayer] = [:]
    private var drawn: [WrenPart.ID: [Int]] = [:]
    private var link: CADisplayLink?
    private var lastTick: CFTimeInterval?
    private var wakeTimer: Timer?
    private var breathing: Breathing?
    /// Points per figure unit, times the screen's scale: the resolution parts are drawn at.
    private var pixelsPerUnit: CGFloat = 0

    private enum Breathing: Equatable { case awake, asleep, none }

    /// Frames drawn since the view was made; for tests and the probe.
    private(set) var frames = 0
    /// Part images drawn since the view was made.
    private(set) var redraws = 0

    override init(frame: NSRect) {
        super.init(frame: frame)
        wantsLayer = true
        layerContentsRedrawPolicy = .never
        for layer in [stage, breath, body, face] {
            layer.anchorPoint = .zero
            layer.bounds = CGRect(x: 0, y: 0, width: 200, height: 200)
            layer.position = .zero
            layer.actions = Self.noActions
        }
        // Breathing scales him about his feet.
        breath.anchorPoint = CGPoint(x: 0.5, y: WrenRig.ground / 200)
        breath.position = CGPoint(x: 100, y: WrenRig.ground)
        layer?.addSublayer(stage)
        stage.addSublayer(breath)
        breath.addSublayer(body)
        body.addSublayer(face)
        face.zPosition = CGFloat(WrenRig.faceZ)
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) { fatalError("init(coder:) is not used") }

    override var isFlipped: Bool { true }
    override func hitTest(_ point: NSPoint) -> NSView? { nil }

    private static let noActions: [String: CAAction] = [
        "position": NSNull(), "bounds": NSNull(), "transform": NSNull(), "opacity": NSNull(), "contents": NSNull(),
        "sublayerTransform": NSNull(), "hidden": NSNull(), "zPosition": NSNull(), "anchorPoint": NSNull(),
    ]

    private var reduceMotion: Bool { NSWorkspace.shared.accessibilityDisplayShouldReduceMotion }

    /// Follows `live` for the level instead of the input's.
    func follow(_ live: LiveLevel?) {
        guard let live else { levels = nil; level = nil; return }
        guard levels == nil else { return }
        levels = live.$level.removeDuplicates().sink { [weak self] value in
            guard let self, let input = self.input else { return }
            self.level = value
            self.update(input)
        }
    }

    func update(_ input: FigureInput) {
        let first = self.input == nil
        self.input = input
        var input = input
        if let level { input.level = level }
        director.direct(input, small: small, motion: &motion, at: CACurrentMediaTime(), reduceMotion: reduceMotion)
        // Nobody sees the moves while the window isn't shown (and its display link never fires): just take the pose.
        let unseen = window?.isVisible != true
        if first || unseen || reduceMotion && !motion.playing.isEmpty {
            motion.snap()
        }
        if first || unseen || reduceMotion { apply() }
        updateBreathing()
        run()
    }

    // MARK: Layout

    override func layout() {
        super.layout()
        frameStage()
    }

    override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()
        frameStage()
        breathing = nil
        updateBreathing()
        run()
    }

    override func viewDidChangeBackingProperties() {
        super.viewDidChangeBackingProperties()
        frameStage()
    }

    /// Maps figure space onto the view: the 120 pt framing, scaled to the view's size, y down.
    private func frameStage() {
        guard let layer, bounds.width > 0 else { return }
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        stage.frame = layer.bounds
        let box = WrenRig.viewBox
        let k = min(bounds.width / box.width, bounds.height / box.height)
        // The view's layer counts y up unless AppKit flipped it for us.
        let yDown = layer.isGeometryFlipped
        var t = CATransform3DIdentity
        if !yDown {
            t = CATransform3DTranslate(t, 0, bounds.height, 0)
            t = CATransform3DScale(t, 1, -1, 1)
        }
        t = CATransform3DTranslate(t, (bounds.width - box.width * k) / 2, (bounds.height - box.height * k) / 2, 0)
        t = CATransform3DScale(t, k, k, 1)
        t = CATransform3DTranslate(t, -box.minX, -box.minY, 0)
        stage.sublayerTransform = t
        CATransaction.commit()
        let scale = (window?.backingScaleFactor ?? NSScreen.main?.backingScaleFactor ?? 2) * k
        if abs(scale - pixelsPerUnit) > 0.001 {
            pixelsPerUnit = scale
            drawn.removeAll()
            if input != nil { apply() }
        }
    }

    // MARK: Running

    /// Asks for frames while anything moves, and wakes for the director's next beat after that.
    private func run() {
        wakeTimer?.invalidate()
        wakeTimer = nil
        guard window != nil else { return stopLink() }
        if !motion.settled {
            startLink()
        } else {
            stopLink()
            let wake = director.wake - CACurrentMediaTime()
            if wake.isFinite {
                let timer = Timer(timeInterval: max(0.01, wake), repeats: false) { [weak self] _ in self?.beat() }
                RunLoop.main.add(timer, forMode: .common)
                wakeTimer = timer
            }
        }
    }

    private func beat() {
        guard var input else { return }
        if let level { input.level = level }
        director.direct(input, small: small, motion: &motion, at: CACurrentMediaTime(), reduceMotion: reduceMotion)
        run()
    }

    private func startLink() {
        guard link == nil else { return }
        let link = displayLink(target: self, selector: #selector(tick(_:)))
        // 60 at most: a ProMotion screen would double the work for motion this size.
        link.preferredFrameRateRange = CAFrameRateRange(minimum: 30, maximum: 60, preferred: 60)
        link.add(to: .main, forMode: .common)
        self.link = link
        lastTick = nil
    }

    private func stopLink() {
        link?.invalidate()
        link = nil
        lastTick = nil
    }

    @objc private func tick(_ link: CADisplayLink) {
        let now = link.targetTimestamp
        let dt = lastTick.map { now - $0 } ?? 1.0 / 60
        lastTick = now
        if var input, director.wake <= CACurrentMediaTime() {
            if let level { input.level = level }
            director.direct(input, small: small, motion: &motion, at: CACurrentMediaTime(), reduceMotion: reduceMotion)
        }
        motion.advance(by: dt)
        apply()
        if motion.settled { run() }
    }

    /// One frame by hand, for measuring: what a display link tick does.
    func step(_ dt: Double) {
        motion.advance(by: dt)
        apply()
    }

    override func removeFromSuperview() {
        stopLink()
        wakeTimer?.invalidate()
        super.removeFromSuperview()
    }

    // MARK: Drawing

    /// Sets every layer from the motion's current pose. Transforms only, unless a part's shape changed.
    private func apply() {
        guard pixelsPerUnit > 0 else { return }
        frames += 1
        let frame = WrenRig.frame(motion.pose, small: small)
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        body.setAffineTransform(frame.body)
        face.setAffineTransform(frame.face)
        place(frame.shadow, in: stage, below: breath)
        for part in frame.bodyParts { place(part, in: body) }
        for part in frame.faceParts { place(part, in: face) }
        for (id, layer) in parts where !frame.bodyParts.contains(where: { $0.id == id })
            && !frame.faceParts.contains(where: { $0.id == id }) && id != .shadow {
            layer.isHidden = true
        }
        CATransaction.commit()
    }

    private func place(_ part: WrenPart, in group: CALayer, below sibling: CALayer? = nil) {
        let layer = parts[part.id] ?? {
            let layer = CALayer()
            layer.anchorPoint = .zero
            layer.actions = Self.noActions
            layer.contentsGravity = .resize
            layer.zPosition = CGFloat(part.z)
            if let sibling { group.insertSublayer(layer, below: sibling) } else { Self.insert(layer, into: group) }
            parts[part.id] = layer
            return layer
        }()
        if layer.zPosition != CGFloat(part.z) {
            layer.zPosition = CGFloat(part.z)
            layer.removeFromSuperlayer()
            Self.insert(layer, into: group)
        }
        let visible = part.opacity > 0.004
        layer.isHidden = !visible
        guard visible else { return }
        if drawn[part.id] != part.key || layer.bounds != part.box {
            layer.contents = render(part)
            drawn[part.id] = part.key
            redraws += 1
        }
        let t = part.transform
        let linear = CGAffineTransform(a: t.a, b: t.b, c: t.c, d: t.d, tx: 0, ty: 0)
        layer.bounds = part.box
        layer.position = part.box.origin.applying(linear)
        layer.setAffineTransform(t)
        layer.opacity = Float(part.opacity)
    }

    /// Keeps sublayers in z order by position as well, for renderers that ignore `zPosition`.
    private static func insert(_ layer: CALayer, into group: CALayer) {
        let above = group.sublayers?.first { $0.zPosition > layer.zPosition }
        if let above { group.insertSublayer(layer, below: above) } else { group.addSublayer(layer) }
    }

    private func render(_ part: WrenPart) -> CGImage? {
        let w = Int((part.box.width * pixelsPerUnit).rounded(.up)), h = Int((part.box.height * pixelsPerUnit).rounded(.up))
        guard w > 0, h > 0, let ctx = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: 0,
                                                 space: CGColorSpace(name: CGColorSpace.sRGB)!,
                                                 bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return nil }
        // Figure space counts y down; the bitmap counts up.
        ctx.translateBy(x: 0, y: CGFloat(h))
        ctx.scaleBy(x: pixelsPerUnit, y: -pixelsPerUnit)
        ctx.translateBy(x: -part.box.minX, y: -part.box.minY)
        part.draw(ctx)
        return ctx.makeImage()
    }

    // MARK: Breathing

    /// A slow breath on Core Animation's clock: deeper and slower asleep, none in the air or with Reduce Motion.
    private func updateBreathing() {
        guard let input else { return }
        let want: Breathing
        if reduceMotion || window == nil || input.flight.airborne {
            want = .none
        } else {
            want = input.shown == .sleepy && !input.pose.yawn ? .asleep : .awake
        }
        guard want != breathing else { return }
        breathing = want
        breath.removeAnimation(forKey: "breath")
        guard want != .none else { return }
        let amount = want == .asleep ? 0.022 : 0.012
        let animation = CAKeyframeAnimation(keyPath: "transform")
        let out = CATransform3DMakeScale(1 + amount * 0.3, 1 - amount * 0.4, 1)
        let held = CATransform3DMakeScale(1 - amount * 0.3, 1 + amount, 1)
        animation.values = [out, held, out].map { NSValue(caTransform3D: $0) }
        animation.keyTimes = [0, 0.42, 1]
        animation.timingFunctions = [CAMediaTimingFunction(name: .easeInEaseOut), CAMediaTimingFunction(name: .easeInEaseOut)]
        animation.duration = want == .asleep ? 5.2 : 3.6
        animation.repeatCount = .infinity
        animation.isRemovedOnCompletion = false
        animation.beginTime = CACurrentMediaTime()
        breath.add(animation, forKey: "breath")
    }
}

/// Milo in SwiftUI: the live layer rig, or a still drawing when `time` fixes the clock (renders).
struct WrenFigure: View {
    var input: FigureInput
    /// The overlay's live level, followed by the rig itself; nil uses `input.level`.
    var live: LiveLevel?
    var small: Bool
    /// Renders: draw the pose this input settles into, without the live rig.
    var still: Bool

    var body: some View {
        if still {
            let pose = Self.stillPose(input, small: small)
            Canvas { context, size in
                context.withCGContext { cg in
                    WrenRender.draw(pose, small: small, in: cg, rect: CGRect(origin: .zero, size: size), flipped: true)
                }
            }
        } else {
            WrenLive(input: input, live: live, small: small)
        }
    }

    /// The pose a still figure shows: where the springs would come to rest, with the eyes shut mid-blink.
    static func stillPose(_ input: FigureInput, small: Bool) -> WrenPose {
        var pose = WrenDirector.pose(for: input, small: small)
        if input.pose.blink { pose.lidL = 1; pose.lidR = 1 }
        return pose
    }
}

private struct WrenLive: NSViewRepresentable {
    var input: FigureInput
    var live: LiveLevel?
    var small: Bool

    func makeNSView(context: Context) -> WrenView {
        let view = WrenView(frame: .zero)
        view.small = small
        return view
    }

    func updateNSView(_ view: WrenView, context: Context) {
        view.small = small
        view.follow(live)
        view.update(input)
    }
}
