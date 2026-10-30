import SwiftUI

struct Face: View {
    var emotion: Emotion
    var speaking: Bool
    var level: Double
    var blinking: Bool
    /// Where the eyes look, -1...1 per axis, y down.
    var gaze: CGVector = .zero
    var yawning = false

    var body: some View {
        VStack(spacing: 9) {
            HStack(spacing: 22) {
                Eye(emotion: emotion, left: true, blinking: blinking)
                Eye(emotion: emotion, left: false, blinking: blinking)
            }
            .offset(x: gaze.dx * 3, y: gaze.dy * 2.5)
            .overlay(Brows(emotion: emotion).offset(x: gaze.dx * 1.5, y: -15 + gaze.dy))
            ZStack {
                if [.happy, .excited].contains(emotion) || speaking {
                    HStack(spacing: 44) {
                        Ellipse().fill(Palette.blush.opacity(0.55)).frame(width: 15, height: 8)
                        Ellipse().fill(Palette.blush.opacity(0.55)).frame(width: 15, height: 8)
                    }
                    .offset(y: -6)
                }
                Mouth(emotion: emotion, speaking: speaking, level: level, yawning: yawning)
            }
            .frame(height: 18)
        }
        .animation(.spring(response: 0.3, dampingFraction: 0.7), value: emotion)
    }
}

struct Eye: View {
    var emotion: Emotion
    var left: Bool
    var blinking: Bool

    var body: some View {
        ZStack {
            switch emotion {
            case .happy:
                ArcShape(up: true).stroke(Palette.face, style: StrokeStyle(lineWidth: 3.5, lineCap: .round))
                    .frame(width: 15, height: 8)
            case .sleepy:
                Capsule().fill(Palette.face).frame(width: 15, height: 3.5)
            default:
                let size = eyeSize
                Ellipse()
                    .fill(Palette.face)
                    .frame(width: size.width, height: blinking ? 2 : size.height)
                    .overlay(
                        Circle().fill(.white).frame(width: size.width * 0.38)
                            .offset(x: size.width * 0.18, y: -size.height * 0.2)
                            .opacity(blinking ? 0 : 1)
                    )
                    .offset(x: emotion == .thinking ? 3 : 0, y: emotion == .thinking ? -3 : (emotion == .sad ? 2 : 0))
            }
        }
        .frame(width: 18, height: 22)
    }

    private var eyeSize: CGSize {
        switch emotion {
        case .excited: CGSize(width: 16, height: 21)
        case .confused: left ? CGSize(width: 14, height: 18) : CGSize(width: 10, height: 12)
        case .sad, .concerned: CGSize(width: 12, height: 15)
        default: CGSize(width: 13, height: 17)
        }
    }
}

struct Brows: View {
    var emotion: Emotion

    var body: some View {
        HStack(spacing: 18) {
            brow(left: true)
            brow(left: false)
        }
        .opacity([.concerned, .sad, .confused].contains(emotion) ? 1 : 0)
    }

    private func brow(left: Bool) -> some View {
        let tilt: Double = switch emotion {
        case .concerned, .sad: left ? -18 : 18
        case .confused: left ? 0 : -16
        default: 0
        }
        return Capsule().fill(Palette.face).frame(width: 13, height: 3).rotationEffect(.degrees(tilt))
    }
}

struct Mouth: View {
    var emotion: Emotion
    var speaking: Bool
    var level: Double
    var yawning = false

    var body: some View {
        Group {
            if yawning {
                Ellipse().fill(Palette.face).frame(width: 12, height: 15).offset(y: 2)
            } else if speaking {
                Ellipse()
                    .fill(Palette.face)
                    .frame(width: 14 + level * 4, height: 3 + level * 13)
                    .overlay(Ellipse().fill(Palette.blush).frame(width: 8, height: max(0, level * 5)).offset(y: level * 3))
                    .clipShape(Ellipse())
            } else {
                switch emotion {
                case .happy, .excited:
                    SmileShape().fill(Palette.face).frame(width: emotion == .excited ? 22 : 18, height: emotion == .excited ? 11 : 8)
                case .sad, .concerned:
                    ArcShape(up: true).stroke(Palette.face, style: StrokeStyle(lineWidth: 3, lineCap: .round)).frame(width: 14, height: 5)
                case .thinking:
                    Capsule().fill(Palette.face).frame(width: 8, height: 3).offset(x: 5)
                case .sleepy:
                    Circle().fill(Palette.face).frame(width: 6, height: 6)
                case .confused:
                    WavyShape().stroke(Palette.face, style: StrokeStyle(lineWidth: 2.5, lineCap: .round)).frame(width: 16, height: 5)
                case .neutral:
                    ArcShape(up: false).stroke(Palette.face, style: StrokeStyle(lineWidth: 3, lineCap: .round)).frame(width: 13, height: 5)
                }
            }
        }
        .animation(.easeOut(duration: 0.07), value: level)
    }
}
