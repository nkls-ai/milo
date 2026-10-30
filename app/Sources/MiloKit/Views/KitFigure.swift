import SwiftUI

enum KitPalette {
    static let fur = Color(red: 0.93, green: 0.59, blue: 0.34)
    static let furShade = Color(red: 0.85, green: 0.48, blue: 0.24)
    static let furLight = Color(red: 0.95, green: 0.64, blue: 0.41)
    static let faceShade = Color(red: 0.89, green: 0.53, blue: 0.29)
    static let tail = Color(red: 0.87, green: 0.50, blue: 0.25)
    static let cream = Color(red: 0.97, green: 0.92, blue: 0.85)
    static let creamShade = Color(red: 0.94, green: 0.88, blue: 0.80)
    static let ink = Color(red: 0.18, green: 0.15, blue: 0.14)
    static let earInside = Color(red: 0.23, green: 0.18, blue: 0.17)
    static let cheek = Color(red: 0.94, green: 0.56, blue: 0.53)
    static let plane = Color(red: 0.97, green: 0.92, blue: 0.85)
    static let planeShade = Color(red: 0.89, green: 0.80, blue: 0.69)
}

/// Kit, a fox folded from warm paper: flat facets and crisp creases. He folds himself into a paper plane to
/// fly and unfolds a paw to point. Drawn from the concept page; feet on y = 107.
struct KitFigure: Skin {
    var look: SkinLook

    static func idleLoop(_ look: SkinLook) -> Loop? {
        guard !look.airborne else {
            // The plane rides the air a little.
            if case .flying = look.flight { return .float(period: 0.9, height: 3) }
            return nil
        }
        let feet = UnitPoint(x: 0.5, y: 106 / 120)
        if look.thinking {
            return Loop(period: 2.6, keys: [.init(at: 0, angle: -2.5), .init(at: 0.5, angle: 2.5), .init(at: 1, angle: -2.5)],
                        pivot: feet)
        }
        return look.sleeping ? .breath(period: 5.5, amount: 0.018, pivot: feet) : .breath(period: 3.8, amount: 0.009, pivot: feet)
    }

    var body: some View {
        ZStack {
            ListeningRing(look: look, center: CGPoint(x: 60, y: 60), diameter: 110)
            if case .flying = look.flight {
                PaperPlane(look: look)
            } else {
                GroundShadow(look: look, width: 56, y: 108)
                KitBody(look: look)
            }
            Marks(look: look, at: CGPoint(x: 100, y: 30), sleepColor: KitPalette.furShade, color: KitPalette.furShade)
        }
        .frame(width: 120, height: 120)
    }
}

/// A shape from points in the 120 pt box.
private struct Facet: Shape {
    var points: [CGPoint]

    init(_ coordinates: [Double]) {
        points = stride(from: 0, to: coordinates.count - 1, by: 2).map { CGPoint(x: coordinates[$0], y: coordinates[$0 + 1]) }
    }

    func path(in r: CGRect) -> Path {
        var p = Path()
        p.addLines(points.map { CGPoint(x: r.minX + $0.x * r.width / 120, y: r.minY + $0.y * r.height / 120) })
        p.closeSubpath()
        return p
    }
}

/// Fold lines: pairs of points in the 120 pt box.
private struct Creases: Shape {
    var lines: [[Double]]

    func path(in r: CGRect) -> Path {
        var p = Path()
        for line in lines {
            let points = stride(from: 0, to: line.count - 1, by: 2).map {
                CGPoint(x: r.minX + line[$0] * r.width / 120, y: r.minY + line[$0 + 1] * r.height / 120)
            }
            p.addLines(points)
        }
        return p
    }
}

private struct KitBody: View {
    var look: SkinLook

    private var curled: Bool { look.sleeping }

    private var pointing: CGVector? {
        if case let .pointing(toward) = look.flight { toward } else { nil }
    }

    var body: some View {
        ZStack {
            if !curled { tail }
            // Body: two facets with the chest between them.
            Facet([36, 106, 84, 106, 81, 80, 60, 70, 39, 80]).fill(KitPalette.fur)
            Facet([60, 70, 81, 80, 84, 106, 60, 106]).fill(KitPalette.furShade)
            Facet([47, 106, 73, 106, 60, 80]).fill(KitPalette.cream)
            Creases(lines: [[60, 70, 60, 106]]).stroke(Color.black.opacity(0.09), lineWidth: 0.8)
            if pointing.map({ $0.dx <= 0 }) != true {
                Facet([43, 106, 52, 106, 50, 95]).fill(KitPalette.cream)
            }
            if pointing.map({ $0.dx > 0 }) != true {
                Facet([68, 106, 77, 106, 70, 95]).fill(KitPalette.creamShade)
            }
            if let toward = pointing { paw(toward) }
            if curled { curledTail }
            KitHead(look: look)
                .offset(x: curled ? 4 : look.gaze.dx * 1.5, y: curled ? 10 : look.gaze.dy * 1)
                .rotationEffect(.degrees(headTilt), anchor: UnitPoint(x: 0.5, y: 80 / 120))
        }
        .frame(width: 120, height: 120)
        .scaleEffect(x: 1 - look.stretch * 0.5, y: 1 + look.stretch, anchor: UnitPoint(x: 0.5, y: 106 / 120))
        .rotationEffect(.degrees(look.airborne ? look.tilt * 0.5 : look.pose.lean * 3), anchor: UnitPoint(x: 0.5, y: 106 / 120))
        .offset(x: look.airborne ? 0 : look.pose.lean * 3, y: look.lift)
        .animation(.spring(response: 0.22, dampingFraction: 0.5), value: look.pose.squash)
        .animation(.spring(response: 0.45, dampingFraction: 0.7), value: look.pose.lean)
        .animation(.spring(response: 0.3, dampingFraction: 0.6), value: look.pose.tilt)
        .animation(.spring(response: 0.25, dampingFraction: 0.8), value: look.pose.gaze)
        .animation(.spring(response: 0.45, dampingFraction: 0.7), value: look.emotion)
        .animation(.spring(response: 0.45, dampingFraction: 0.7), value: look.state)
        .animation(.easeOut(duration: 0.08), value: look.level)
    }

    /// The head turns more than the body: toward the user while listening, aside while sleeping.
    private var headTilt: Double {
        if curled { return 10 }
        if look.airborne { return look.tilt * 0.6 }
        var degrees = look.pose.lean * 6 + look.pose.tilt
        if look.listening { degrees += 3 * look.side }
        if look.emotion == .confused { degrees -= 10 }
        if look.emotion == .sad { degrees += 4 }
        return degrees + look.nod * 6
    }

    /// The tail: a long folded wedge with a cream tip, swishing slowly, wagging when he's pleased, and wrapped
    /// round his paws while he sleeps.
    private var tail: some View {
        let root = UnitPoint(x: 81 / 120, y: 100 / 120)
        let loop: Loop? = if look.airborne {
            nil
        } else if look.happy {
            Loop(period: 0.32, keys: [.init(at: 0, angle: 0), .init(at: 0.5, angle: -14), .init(at: 1, angle: 0)], pivot: root)
        } else {
            Loop(period: 3.6, keys: [.init(at: 0, angle: -3), .init(at: 0.5, angle: 4), .init(at: 1, angle: -3)], pivot: root)
        }
        return Looping(loop, frozen: look.frozen, time: look.time) {
            ZStack {
                Facet([78, 100, 112, 64, 104, 104]).fill(KitPalette.tail)
                Facet([78, 100, 104, 104, 98, 92]).fill(KitPalette.furShade)
                Facet([112, 64, 104, 80, 99, 73]).fill(KitPalette.cream)
            }
            .frame(width: 120, height: 120)
        }
        .frame(width: 120, height: 120)
    }

    /// Asleep, the tail lies round in front of his paws with its tip by his cheek.
    private var curledTail: some View {
        ZStack {
            Facet([90, 92, 52, 99, 30, 96, 58, 108, 86, 107]).fill(KitPalette.tail)
            Facet([90, 92, 86, 107, 58, 108]).fill(KitPalette.furShade)
            Facet([30, 96, 42, 97.5, 40, 104]).fill(KitPalette.cream)
            Facet([30, 96, 40, 104, 46, 106]).fill(KitPalette.creamShade)
            Creases(lines: [[90, 92, 58, 108]]).stroke(Color.black.opacity(0.08), lineWidth: 0.8)
        }
        .frame(width: 120, height: 120)
    }

    /// A paw unfolded toward what he points at, with a dark tip.
    private func paw(_ toward: CGVector) -> some View {
        let left = toward.dx <= 0
        // The drawn paw points along (-29, -18) from the shoulder; turn it to `toward`.
        let base = atan2(-18.0, left ? -29 : 29)
        let angle = (atan2(Double(toward.dy), Double(toward.dx)) - base) * 180 / .pi
        let shoulder = UnitPoint(x: (left ? 41 : 79) / 120, y: 81 / 120)
        return ZStack {
            // A folded foreleg: fur on top, shade underneath, a dark sock at the paw.
            Group {
                Facet([42, 76, 20, 61, 18, 65, 40, 85]).fill(KitPalette.furLight)
                Facet([40, 85, 18, 65, 21, 68, 42, 86]).fill(KitPalette.furShade)
                Facet([20, 61, 12, 58, 10, 64, 18, 65]).fill(KitPalette.earInside)
                Facet([18, 65, 10, 64, 14, 68, 21, 68]).fill(KitPalette.ink)
            }
            .scaleEffect(x: left ? 1 : -1)
        }
        .frame(width: 120, height: 120)
        .rotationEffect(.degrees(angle), anchor: shoulder)
    }
}

/// The folded head: two big ears, two cheek facets, round eyes and a small triangle nose.
private struct KitHead: View {
    var look: SkinLook

    var body: some View {
        let emotion = look.emotion
        ZStack {
            ear(left: true)
            ear(left: false)
            Facet([27, 47, 60, 40, 60, 86]).fill(KitPalette.furLight)
            Facet([93, 47, 60, 40, 60, 86]).fill(KitPalette.faceShade)
            Facet([35, 59, 60, 63, 60, 86]).fill(Color(red: 0.98, green: 0.94, blue: 0.89))
            Facet([85, 59, 60, 63, 60, 86]).fill(KitPalette.creamShade)
            Creases(lines: [[60, 40, 60, 86], [27, 47, 60, 63, 93, 47]])
                .stroke(Color.black.opacity(look.small ? 0.05 : 0.09), lineWidth: 0.8)
            ForEach([true, false], id: \.self) { left in
                Ellipse()
                    .fill(KitPalette.cheek.opacity(look.happy ? 0.62 : 0.45))
                    .frame(width: 8, height: 4.8)
                    .position(x: left ? 42 : 78, y: 66)
                KitEye(look: look, left: left)
                    .offset(x: look.gaze.dx * 2, y: look.gaze.dy * 1.6)
                    .position(x: left ? 48 : 72, y: 57)
            }
            Facet([56.2, 80, 63.8, 80, 60, 85.5]).fill(KitPalette.ink)
            KitMouth(look: look)
                .position(x: 60, y: 92)
            if emotion == .concerned || emotion == .sad || emotion == .thinking || emotion == .confused {
                ForEach([true, false], id: \.self) { left in
                    Capsule()
                        .fill(KitPalette.ink.opacity(0.75))
                        .frame(width: 8, height: 1.8)
                        .rotationEffect(.degrees(browTilt(left: left)))
                        .position(x: left ? 47 : 73, y: 50)
                }
            }
        }
        .frame(width: 120, height: 120)
    }

    private func browTilt(left: Bool) -> Double {
        switch look.emotion {
        case .concerned, .sad: left ? -16 : 16
        case .confused: left ? -4 : 14
        default: left ? 8 : -8
        }
    }

    /// An ear and its dark inside, folded and turned by mood.
    private func ear(left: Bool) -> some View {
        let (angle, height) = earPose(left: left)
        let base = UnitPoint(x: (left ? 40 : 80) / 120, y: 45 / 120)
        return ZStack {
            if left {
                Facet([29, 47, 35, 13, 52, 42]).fill(Color(red: 0.93, green: 0.56, blue: 0.31))
                Facet([34, 41, 36, 22, 46, 40]).fill(KitPalette.earInside)
            } else {
                Facet([91, 47, 85, 13, 68, 42]).fill(KitPalette.furShade)
                Facet([86, 41, 84, 22, 74, 40]).fill(KitPalette.earInside)
            }
        }
        .frame(width: 120, height: 120)
        .scaleEffect(y: height, anchor: base)
        .rotationEffect(.degrees(angle), anchor: base)
    }

    /// Degrees (clockwise, mirrored for the right ear) and height: up and tall while listening, one ear folded
    /// while thinking, drooping when sad or asleep, flattened when worried.
    private func earPose(left: Bool) -> (Double, Double) {
        let out = left ? -1.0 : 1.0
        if look.sleeping { return (out * 8 * -1, 0.72) }
        if look.listening { return (0, 1.06 + look.level * 0.16) }
        switch look.emotion {
        case .thinking where !left, .confused where !left: return (22, 0.78)
        case .sad: return (out * 24, 0.8)
        case .concerned: return (out * 16, 0.88)
        case .happy, .excited: return (out * -3, 1.05)
        default: return (0, 1)
        }
    }
}

private struct KitEye: View {
    var look: SkinLook
    var left: Bool

    var body: some View {
        let emotion = look.emotion
        ZStack {
            if look.pose.yawn || emotion == .sleepy {
                ArcShape(up: false)
                    .stroke(KitPalette.ink, style: StrokeStyle(lineWidth: 2.2, lineCap: .round))
                    .frame(width: 8, height: 2.4)
            } else if emotion == .happy {
                ArcShape(up: true)
                    .stroke(KitPalette.ink, style: StrokeStyle(lineWidth: 2.4, lineCap: .round))
                    .frame(width: 8, height: 3.6)
                    .offset(y: 1)
            } else {
                let d = diameter
                Ellipse()
                    .fill(KitPalette.ink)
                    .frame(width: d, height: look.pose.blink ? 1.4 : d * 1.04)
                    .overlay(alignment: .topTrailing) {
                        Circle().fill(.white).frame(width: d * 0.34)
                            .offset(x: -d * 0.16, y: d * 0.14)
                            .opacity(look.pose.blink ? 0 : 1)
                    }
            }
        }
        .frame(width: 14, height: 14)
        .animation(.easeInOut(duration: 0.07), value: look.pose.blink)
    }

    private var diameter: Double {
        switch look.emotion {
        case .excited: 8.4
        case .confused: left ? 7.8 : 5.4
        case .sad, .concerned: 6.2
        default: look.listening ? 7.6 : 6.8
        }
    }
}

/// Only shown while he speaks, yawns or smiles wide: a small paper mouth under the nose.
private struct KitMouth: View {
    var look: SkinLook

    var body: some View {
        let open = look.mouthOpen
        ZStack {
            if open > 0.05 {
                Facet([0, 0, 120, 0, 60, 120]).fill(Color(red: 0.45, green: 0.20, blue: 0.20))
                    .frame(width: 5 + open * 3, height: 2 + open * 6)
                    .offset(y: 1)
            } else if look.emotion == .happy || look.emotion == .excited {
                ArcShape(up: false)
                    .stroke(KitPalette.ink, style: StrokeStyle(lineWidth: 1.4, lineCap: .round))
                    .frame(width: 7, height: 2.2)
            } else if look.emotion == .sad || look.emotion == .concerned {
                ArcShape(up: true)
                    .stroke(KitPalette.ink, style: StrokeStyle(lineWidth: 1.4, lineCap: .round))
                    .frame(width: 6, height: 1.8)
                    .offset(y: 1)
            }
        }
        .frame(width: 14, height: 12, alignment: .top)
        .animation(.easeOut(duration: 0.07), value: open)
    }
}

/// Kit folded into a paper plane, nose toward where he's going.
private struct PaperPlane: View {
    var look: SkinLook

    var body: some View {
        let heading: CGVector = if case let .flying(h) = look.flight { h } else { CGVector(dx: -1, dy: 0) }
        // The plane is drawn flying right and a little up; turn it to the heading, and flip it when heading left
        // so it never flies upside down.
        let left = heading.dx < 0
        let angle = atan2(Double(heading.dy), abs(Double(heading.dx))) * 180 / .pi
        ZStack {
            Facet([16, 72, 106, 50, 58, 86]).fill(KitPalette.plane)
            Facet([58, 86, 106, 50, 64, 74]).fill(KitPalette.fur)
            Facet([58, 86, 64, 74, 52, 78]).fill(KitPalette.furShade)
            Creases(lines: [[16, 72, 106, 50], [58, 86, 106, 50]]).stroke(Color.black.opacity(0.08), lineWidth: 0.8)
        }
        .frame(width: 120, height: 120)
        .rotationEffect(.degrees(angle + 13))
        .scaleEffect(x: left ? -1 : 1)
        .shadow(color: Color.black.opacity(0.12), radius: 3, y: 4)
    }
}
