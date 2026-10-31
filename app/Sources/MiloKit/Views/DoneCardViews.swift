import SwiftUI

/// The cards left of Milo for what he just did (`DoneCards`). They lie as a small deck, newest in front; with the
/// pointer on them they fan out upwards so each can be clicked. A new one springs out of Milo's side; one that
/// ran out tucks back into him. With Reduce Motion they fade.
struct DoneCardStack: View {
    @Environment(\.miloTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @ObservedObject var model: MiloModel
    @ObservedObject var done: DoneCards

    init(model: MiloModel) {
        self.model = model
        done = model.done
    }

    static let width: CGFloat = 172
    static let height: CGFloat = 56
    /// How far each card behind peeks out above the one in front while they lie as a deck.
    static let peek: CGFloat = 7
    static let gap: CGFloat = 6

    var body: some View {
        let cards = done.cards
        let open = done.hovered
        ZStack(alignment: .bottom) {
            ForEach(Array(cards.enumerated()), id: \.element.id) { index, card in
                let depth = cards.count - 1 - index  // 0 is the newest, in front
                DoneCardView(card: card, point: card.action.undo.isEmpty ? nil : point(card.action), done: done,
                             now: Date(), face: open || depth == 0)
                    .scaleEffect(open ? 1 : 1 - 0.05 * CGFloat(depth), anchor: .bottom)
                    .offset(y: -CGFloat(depth) * (open ? Self.height + Self.gap : Self.peek))
                    .zIndex(Double(index))
                    .allowsHitTesting(open || depth == 0)
                    .transition(reduceMotion ? .opacity : Self.flight)
            }
        }
        .frame(width: Self.width, height: Self.height(cards.count, open: open), alignment: .bottom)
        .background(GeometryReader { geometry in
            // Where the cards are in the panel, so its hit test lets a click there through to them.
            Color.clear.onAppear { done.area = geometry.frame(in: .global) }
                .onChange(of: geometry.frame(in: .global)) { _, frame in done.area = cards.isEmpty ? .zero : frame }
        })
        .contentShape(Rectangle())
        .onHover { done.hover($0) }
        .animation(theme.motion.animation(reduced: reduceMotion), value: cards.map(\.id))
        .animation(theme.motion.animation(reduced: reduceMotion), value: open)
    }

    /// The height the deck takes: one card and the peeks behind it, or every card with a gap when fanned out.
    static func height(_ count: Int, open: Bool) -> CGFloat {
        guard count > 0 else { return 0 }
        let behind = CGFloat(count - 1)
        return height + behind * (open ? height + gap : peek)
    }

    /// Out of Milo's side, to the right of the deck: it springs out small and grows into place; away, it shrinks
    /// back into him.
    static let flight = AnyTransition.asymmetric(
        insertion: .offset(x: 110, y: 18).combined(with: .scale(scale: 0.3, anchor: .trailing)).combined(with: .opacity),
        removal: .offset(x: 90, y: 10).combined(with: .scale(scale: 0.35, anchor: .trailing)).combined(with: .opacity))

    /// The task's undo point, or a ready one while the brain hasn't listed it yet.
    private func point(_ action: ActionDone) -> UndoPoint {
        model.undoPoint(action.undo) ?? UndoPoint(id: action.undo, title: action.title)
    }
}

/// One card: a small picture of the thing on the left (a calendar page, a checkbox, a ring), its title and when,
/// a check that draws itself in, and Undo when the task can be taken back.
struct DoneCardView: View {
    @Environment(\.miloTheme) private var theme
    @Environment(\.colorSchemeContrast) private var contrast
    let card: DoneCard
    let point: UndoPoint?
    let done: DoneCards
    let now: Date
    /// In front, or fanned out: everything shows. Behind another card in the deck only its paper peeks out.
    var face = true

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: 14, style: .continuous)
        let action = card.action
        Button { done.open(card.id) } label: {
            HStack(spacing: 8) {
                DoneGlyph(card: card, icon: action.app.isEmpty ? nil : done.icon?(action.app))
                VStack(alignment: .leading, spacing: 1) {
                    Text(action.title.isEmpty ? DoneCardText.line(action, now: now) : action.title)
                        .font(.system(size: 12.5, weight: .semibold, design: .rounded))
                        .foregroundStyle(theme.ink)
                        .lineLimit(1)
                    Text(DoneCardText.line(action, now: now))
                        .font(.system(size: 10.5, weight: .medium, design: .rounded))
                        .foregroundStyle(theme.ink.opacity(contrast == .increased ? 0.85 : 0.6))
                        .lineLimit(1)
                }
                Spacer(minLength: 0)
            }
            .opacity(face ? 1 : 0)
            .padding(.leading, 8)
            // Room for Undo, which sits on top of the card's button so a click on it is its own.
            .padding(.trailing, point == nil ? 10 : 8 + CardUndo.size + 4)
            .frame(width: DoneCardStack.width, height: DoneCardStack.height)
            .floatingSurface(shape)
            .contentShape(shape)
        }
        .buttonStyle(PressScale())
        .overlay(alignment: .topTrailing) { DrawnCheck().offset(x: 5, y: -5).opacity(face ? 1 : 0) }
        .overlay(alignment: .trailing) {
            if let point, face {
                CardUndo(point: point) { _ in done.undo(card.id) }.padding(.trailing, 8)
            }
        }
        .help(DoneCardText.opens(action))
        .accessibilityElement(children: .contain)
        .accessibilityLabel(DoneCardText.spoken(action, now: now))
        .accessibilityHint(DoneCardText.opens(action))
    }
}

/// Undo on a card: a small round button with the undo arrow, then a turning arrow while it undoes and a dimmed one
/// once it is undone.
private struct CardUndo: View {
    @Environment(\.miloTheme) private var theme
    @Environment(\.colorSchemeContrast) private var contrast
    let point: UndoPoint
    let undo: (String) -> Void
    @State private var hovered = false

    static let size: CGFloat = 24

    var body: some View {
        switch point.state {
        case .ready:
            Button { undo(point.id) } label: {
                Image(systemName: "arrow.uturn.backward")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(theme.primary)
                    .frame(width: Self.size, height: Self.size)
                    .background(Circle().fill(theme.primary.opacity(hovered ? 0.2 : 0.1)))
                    .overlay(Circle().strokeBorder(theme.primary.opacity(contrast == .increased ? 0.8 : 0.28),
                                                   lineWidth: 1))
                    .contentShape(Circle())
            }
            .buttonStyle(PressScale())
            .onHover { hovered = $0 }
            .help("Undo “\(point.title)”")
            .accessibilityLabel("Undo")
            .accessibilityHint("Takes back what Milo just did")
        case .undoing:
            ProgressView().controlSize(.small).frame(width: Self.size, height: Self.size)
                .accessibilityLabel("Undoing")
        case .undone:
            Image(systemName: "arrow.uturn.backward.circle")
                .font(.system(size: 15, weight: .medium))
                .foregroundStyle(theme.ink.opacity(0.4))
                .frame(width: Self.size, height: Self.size)
                .help("Undone")
                .accessibilityLabel("Undone")
        }
    }
}

/// A button that gives a little under the finger, in Milo's spring.
private struct PressScale: ButtonStyle {
    @Environment(\.miloTheme) private var theme

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(configuration.isPressed ? 0.96 : 1)
            .animation(theme.motion.spring, value: configuration.isPressed)
    }
}

/// The marigold check on the card's corner. It draws itself in a moment after the card lands; with Reduce Motion
/// it is simply there.
struct DrawnCheck: View {
    @Environment(\.miloTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var drawn: CGFloat = 0
    /// Draws it whole at once, for still renders.
    var still = false

    static let size: CGFloat = 20

    var body: some View {
        Circle()
            .fill(theme.accent)
            .overlay(Circle().strokeBorder(theme.tint, lineWidth: 2))
            .overlay(
                CheckShape()
                    .trim(from: 0, to: still ? 1 : drawn)
                    .stroke(theme.onPrimary, style: StrokeStyle(lineWidth: 2.2, lineCap: .round, lineJoin: .round))
                    .padding(5.5)
            )
            .frame(width: Self.size, height: Self.size)
            .shadow(color: theme.accent.opacity(0.35), radius: 3, y: 1)
            .accessibilityHidden(true)
            .onAppear {
                guard !still else { return }
                if reduceMotion { return drawn = 1 }
                withAnimation(.easeOut(duration: 0.32).delay(0.28)) { drawn = 1 }
            }
    }
}

/// A tick, short stroke then long, in its rectangle.
struct CheckShape: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: rect.minX, y: rect.midY + rect.height * 0.05))
        path.addLine(to: CGPoint(x: rect.minX + rect.width * 0.36, y: rect.maxY - rect.height * 0.1))
        path.addLine(to: CGPoint(x: rect.maxX, y: rect.minY + rect.height * 0.12))
        return path
    }
}

/// The small picture of what Milo did: a calendar page with its day for an event, a checkbox row for a to-do,
/// a ring that runs down for a timer, a note sheet, an envelope, the app's icon for something he opened.
struct DoneGlyph: View {
    @Environment(\.miloTheme) private var theme
    let card: DoneCard
    /// The app's icon, for something Milo opened.
    var icon: CGImage?

    static let size: CGFloat = 36

    var body: some View {
        Group {
            switch card.action.kind {
            case .event: CalendarTile(date: card.action.when)
            case .todo: TodoTile()
            case .timer: TimerRing(from: card.since, to: card.action.when)
            case .note: NoteTile()
            case .reminder: SymbolTile(symbol: "bell.fill")
            case .draft: SymbolTile(symbol: "envelope.fill")
            case .shortcut: SymbolTile(symbol: "square.2.layers.3d.fill")
            case .music: SymbolTile(symbol: "music.note")
            case .opened: OpenedTile(app: card.action.app, detail: card.action.detail, icon: icon)
            case .other: SymbolTile(symbol: "sparkles")
            }
        }
        .frame(width: Self.size, height: Self.size)
        .accessibilityHidden(true)
    }
}

/// A tiny tear-off page: the weekday on a marigold band, the day of the month big below it.
private struct CalendarTile: View {
    @Environment(\.miloTheme) private var theme
    let date: Date?

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: 8, style: .continuous)
        VStack(spacing: 0) {
            Text(date.map { $0.formatted(.dateTime.weekday(.abbreviated)) } ?? "")
                .font(.system(size: 8.5, weight: .bold, design: .rounded))
                .foregroundStyle(theme.onPrimary)
                .frame(maxWidth: .infinity)
                .frame(height: 12)
                .background(theme.accent)
            Text(date.map { $0.formatted(.dateTime.day()) } ?? "")
                .font(.system(size: 17, weight: .bold, design: .rounded))
                .monospacedDigit()
                .foregroundStyle(theme.ink)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .background(theme.card)
        .clipShape(shape)
        .overlay(shape.strokeBorder(theme.rule, lineWidth: 1))
    }
}

/// A checkbox with two lines beside it, like a row of a list.
private struct TodoTile: View {
    @Environment(\.miloTheme) private var theme

    var body: some View {
        Tile {
            HStack(spacing: 4) {
                Circle().strokeBorder(theme.primary, lineWidth: 1.8).frame(width: 11, height: 11)
                VStack(alignment: .leading, spacing: 3) {
                    Capsule().fill(theme.primary.opacity(0.55)).frame(width: 13, height: 2.5)
                    Capsule().fill(theme.primary.opacity(0.3)).frame(width: 9, height: 2.5)
                }
            }
        }
    }
}

/// A sheet with a marigold top and three ruled lines.
private struct NoteTile: View {
    @Environment(\.miloTheme) private var theme

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: 7, style: .continuous)
        VStack(alignment: .leading, spacing: 3.5) {
            Rectangle().fill(theme.accent).frame(height: 6)
            ForEach([20.0, 22, 14], id: \.self) { width in
                Capsule().fill(theme.ink.opacity(0.28)).frame(width: width, height: 2).padding(.leading, 6)
            }
            Spacer(minLength: 0)
        }
        .frame(width: 32, height: 36)
        .background(theme.card)
        .clipShape(shape)
        .overlay(shape.strokeBorder(theme.rule, lineWidth: 1))
        .rotationEffect(.degrees(-4))
    }
}

/// A ring that runs down from when the timer was set to when it rings, with the minutes left inside.
private struct TimerRing: View {
    @Environment(\.miloTheme) private var theme
    let from: Date
    let to: Date?

    var body: some View {
        TimelineView(.periodic(from: .now, by: 1)) { context in
            let total = max(1, (to ?? from).timeIntervalSince(from))
            let left = max(0, (to ?? from).timeIntervalSince(context.date))
            ZStack {
                Circle().stroke(theme.primary.opacity(0.18), lineWidth: 4)
                Circle()
                    .trim(from: 0, to: to == nil ? 1 : left / total)
                    .stroke(theme.primary, style: StrokeStyle(lineWidth: 4, lineCap: .round))
                    .rotationEffect(.degrees(-90))
                Text(Self.left(left))
                    .font(.system(size: 10, weight: .bold, design: .rounded))
                    .monospacedDigit()
                    .foregroundStyle(theme.ink)
            }
            .padding(3)
        }
    }

    /// "12m", "45s", "1h".
    static func left(_ seconds: TimeInterval) -> String {
        if seconds >= 3600 { return "\(Int((seconds / 3600).rounded()))h" }
        if seconds >= 60 { return "\(Int((seconds / 60).rounded(.up)))m" }
        return "\(Int(seconds.rounded(.up)))s"
    }
}

/// The app's own icon when Milo has it, else a globe for a page or a window for an app.
private struct OpenedTile: View {
    let app: String
    let detail: String
    let icon: CGImage?

    var body: some View {
        if let icon {
            Image(decorative: icon, scale: 2).resizable().interpolation(.high).aspectRatio(contentMode: .fit)
        } else {
            SymbolTile(symbol: detail.contains(".") ? "globe" : "macwindow")
        }
    }
}

/// A rounded lavender wash with a symbol on it.
private struct SymbolTile: View {
    @Environment(\.miloTheme) private var theme
    let symbol: String

    var body: some View {
        Tile {
            Image(systemName: symbol)
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(theme.primary)
        }
    }
}

private struct Tile<Content: View>: View {
    @Environment(\.miloTheme) private var theme
    @ViewBuilder let content: Content

    var body: some View {
        RoundedRectangle(cornerRadius: 9, style: .continuous)
            .fill(theme.primary.opacity(0.12))
            .overlay(content)
    }
}
