import SwiftUI

struct BubbleView: View {
    @ObservedObject var model: MiloModel

    var body: some View {
        if let content = content {
            VStack(alignment: .leading, spacing: 6) {
                if let heard = model.heard, model.state == .thinking || model.bubble != nil {
                    Text("“\(heard)”")
                        .font(.system(size: 11))
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
                content
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .frame(maxWidth: 270, alignment: .leading)
            .background(BubbleShape().fill(Color(nsColor: .windowBackgroundColor).opacity(0.96)))
            .overlay(BubbleShape().stroke(Color.primary.opacity(0.08), lineWidth: 1))
            .shadow(color: .black.opacity(0.18), radius: 10, y: 4)
            .padding(.trailing, 40)
            .transition(.scale(scale: 0.6, anchor: .bottomTrailing).combined(with: .opacity))
        }
    }

    private var content: AnyView? {
        switch model.state {
        case .listening, .dictating:
            let color = model.state == .dictating ? Palette.dictate : Palette.talk
            return AnyView(HStack(spacing: 8) {
                LevelBars(level: model.level, color: color)
                Text(model.state == .dictating ? "Dictating…" : "Listening…")
                    .font(.system(size: 13, weight: .medium))
            })
        case .transcribing where model.bubble == nil:
            return AnyView(ThinkingDots(color: Palette.dictate))
        case .thinking where model.bubble == nil:
            return AnyView(ThinkingDots(color: Palette.think))
        default:
            guard let text = model.bubble else { return nil }
            return AnyView(ScrollView {
                Text(text)
                    .font(.system(size: 13.5))
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .textSelection(.enabled)
            }
            .scrollIndicators(.never)
            .frame(maxHeight: 170)
            .fixedSize(horizontal: false, vertical: text.count < 260))
        }
    }
}

struct BubbleShape: Shape {
    func path(in rect: CGRect) -> Path {
        let tail: CGFloat = 9
        let body = CGRect(x: rect.minX, y: rect.minY, width: rect.width, height: rect.height - tail)
        var p = Path(roundedRect: body, cornerRadius: 16, style: .continuous)
        let x = body.maxX - 34
        p.move(to: CGPoint(x: x - 10, y: body.maxY))
        p.addQuadCurve(to: CGPoint(x: x + 8, y: rect.maxY), control: CGPoint(x: x + 2, y: body.maxY + 2))
        p.addQuadCurve(to: CGPoint(x: x + 6, y: body.maxY), control: CGPoint(x: x + 6, y: body.maxY + 4))
        p.closeSubpath()
        return p
    }
}

struct LevelBars: View {
    var level: Double
    var color: Color
    private let weights: [Double] = [0.5, 0.8, 1.0, 0.75, 0.45]

    var body: some View {
        HStack(spacing: 3) {
            ForEach(weights.indices, id: \.self) { i in
                Capsule()
                    .fill(color)
                    .frame(width: 3.5, height: 5 + 15 * min(1, level * 1.6) * weights[i])
            }
        }
        .frame(height: 20)
        .animation(.easeOut(duration: 0.08), value: level)
    }
}

struct ThinkingDots: View {
    var color: Color
    @State private var phase = false

    var body: some View {
        HStack(spacing: 5) {
            ForEach(0..<3) { i in
                Circle()
                    .fill(color)
                    .frame(width: 7, height: 7)
                    .offset(y: phase ? -3 : 3)
                    .animation(.easeInOut(duration: 0.45).repeatForever().delay(Double(i) * 0.15), value: phase)
            }
        }
        .frame(height: 20)
        .onAppear { phase = true }
    }
}
