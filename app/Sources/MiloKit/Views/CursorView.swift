import SwiftUI

/// Milo's own pointer, in his lavender. Drawn in an overlay, never the system cursor, so the user's own
/// pointer is untouched. A ring ripples out on a click; a caret and a little "Milo" tag show while he types.
struct MiloCursorView: View {
    enum Gesture: Equatable {
        case none, click, typing
    }

    var gesture: Gesture
    /// 0 at rest (faded out), 1 while working.
    var presence: Double
    /// Rises each time a click lands, to retrigger the ripple.
    var clickTick: Int

    var body: some View {
        ZStack(alignment: .topLeading) {
            if gesture == .click { Ripple(tick: clickTick) }
            Pointer()
            if gesture == .typing { Caret() }
        }
        .frame(width: 72, height: 96, alignment: .topLeading)
        .opacity(presence)
        .animation(.easeOut(duration: 0.25), value: presence)
        .animation(.easeInOut(duration: 0.2), value: gesture)
    }

    /// An arrow pointer, lavender with a soft white edge and a little shadow so it reads on any background.
    private struct Pointer: View {
        var body: some View {
            CursorArrow()
                .fill(LinearGradient(colors: [Palette.bodyTop, Palette.bodyBottom],
                                     startPoint: .top, endPoint: .bottom))
                .overlay(CursorArrow().stroke(.white.opacity(0.95), lineWidth: 1.5))
                .frame(width: 22, height: 30)
                .shadow(color: Palette.bodyBottom.opacity(0.5), radius: 4, y: 1)
        }
    }

    private struct Ripple: View {
        let tick: Int
        @State private var out = false
        var body: some View {
            Circle()
                .stroke(Palette.speak, lineWidth: 2.5)
                .frame(width: 34, height: 34)
                .scaleEffect(out ? 1.6 : 0.4)
                .opacity(out ? 0 : 0.9)
                .offset(x: -6, y: -6)
                .onChange(of: tick) { _ in out = false; withAnimation(.easeOut(duration: 0.5)) { out = true } }
                .onAppear { withAnimation(.easeOut(duration: 0.5)) { out = true } }
        }
    }

    private struct Caret: View {
        @State private var on = true
        var body: some View {
            HStack(spacing: 4) {
                RoundedRectangle(cornerRadius: 1).fill(Palette.bodyTop).frame(width: 2.5, height: 20).opacity(on ? 1 : 0.2)
                Text("Milo")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 6).padding(.vertical, 2)
                    .background(Capsule().fill(Palette.bodyBottom.opacity(0.92)))
            }
            .offset(x: 20, y: 30)
            .onAppear { withAnimation(.easeInOut(duration: 0.5).repeatForever()) { on.toggle() } }
        }
    }
}

/// A classic arrow pointer in a 22×30 box, tip at the top-left.
struct CursorArrow: Shape {
    func path(in rect: CGRect) -> Path {
        let w = rect.width, h = rect.height
        var p = Path()
        p.move(to: CGPoint(x: 0, y: 0))
        p.addLine(to: CGPoint(x: 0, y: h * 0.74))
        p.addLine(to: CGPoint(x: w * 0.27, y: h * 0.56))
        p.addLine(to: CGPoint(x: w * 0.44, y: h * 0.95))
        p.addLine(to: CGPoint(x: w * 0.62, y: h * 0.88))
        p.addLine(to: CGPoint(x: w * 0.45, y: h * 0.5))
        p.addLine(to: CGPoint(x: w * 0.72, y: h * 0.47))
        p.closeSubpath()
        return p
    }
}
