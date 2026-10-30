import SwiftUI

/// The small birds next to Milo, one per helper at work, each with its title and how far it is.
/// A click opens that helper in the Milo window. Still figures: they redraw only when a helper changes.
struct HelperFlock: View {
    @Environment(\.miloTheme) private var theme
    @ObservedObject var model: MiloModel
    /// More birds than this make a "+2" instead; the corner left of Milo has room for three.
    static let shown = 3

    /// The birds to draw, oldest left: helpers at work before finished ones, so those win the room.
    static func birds(_ helpers: [HelperInfo]) -> [HelperInfo] {
        let ranked = helpers.filter { !$0.status.active } + helpers.filter(\.status.active)
        let kept = Set(ranked.suffix(shown).map(\.id))
        return helpers.filter { kept.contains($0.id) }
    }

    var body: some View {
        let helpers = model.helpers
        let birds = Self.birds(helpers)
        if !helpers.isEmpty {
            HStack(alignment: .bottom, spacing: 0) {
                ForEach(birds) { helper in
                    Button { model.openHelper(helper.id) } label: {
                        HelperBird(helper: helper, character: model.character)
                    }
                    .buttonStyle(.plain)
                    .help(helper.step.isEmpty ? helper.title : "\(helper.title): \(helper.step)")
                    .accessibilityLabel("Helper: \(helper.title), \(HelperBird.statusWords(helper.status))")
                    .accessibilityHint("Shows it in the Milo window")
                    .transition(.scale(scale: 0.4, anchor: .bottom).combined(with: .opacity))
                }
            }
            .overlay(alignment: .topLeading) {
                if helpers.count > birds.count {
                    Text("+\(helpers.count - birds.count)")
                        .font(.system(size: 9.5, weight: .bold, design: .rounded))
                        .foregroundStyle(.secondary)
                        .fixedSize()
                        .padding(.horizontal, 5)
                        .padding(.vertical, 2)
                        .background(Capsule().fill(theme.card))
                        .help("\(helpers.count - birds.count) more in the Milo window")
                }
            }
            .animation(theme.motion.spring, value: helpers.map(\.id))
        }
    }
}

/// One helper: Milo's own figure (whatever `character` draws, so skins carry over), small and still,
/// with a mark for how it is doing, its title, and a thin bar for how far through its plan it is.
struct HelperBird: View {
    @Environment(\.miloTheme) private var theme
    let helper: HelperInfo
    let character: CharacterStyle
    @StateObject private var figure: MiloModel

    static let size: CGFloat = 40
    static let width: CGFloat = 52

    init(helper: HelperInfo, character: CharacterStyle) {
        self.helper = helper
        self.character = character
        _figure = StateObject(wrappedValue: Self.figureModel(for: helper, character: character))
    }

    var body: some View {
        VStack(spacing: 2) {
            HelperFigure(model: figure, size: Self.size)
                .overlay(alignment: .topTrailing) { HelperMark(status: helper.status).offset(x: 2, y: 2) }
                .opacity(helper.status == .stopped || helper.status == .queued ? 0.6 : 1)
            Text(helper.title)
                .font(.system(size: 9, weight: .semibold, design: .rounded))
                .lineLimit(2)
                .multilineTextAlignment(.center)
                .frame(width: Self.width - 4, height: 24)
                .padding(.horizontal, 2)
                .padding(.vertical, 2)
                .background(RoundedRectangle(cornerRadius: 5, style: .continuous).fill(theme.card))
            ProgressLine(progress: helper.progress, status: helper.status)
                .frame(width: Self.width - 14, height: 3)
        }
        .frame(width: Self.width)
        .contentShape(Rectangle())
        .onChange(of: helper) { Self.update(figure, for: helper, character: character) }
        .onChange(of: character) { Self.update(figure, for: helper, character: character) }
    }

    static func figureModel(for helper: HelperInfo, character: CharacterStyle) -> MiloModel {
        let model = MiloModel(scheduler: MainQueueScheduler())
        model.connected = true
        update(model, for: helper, character: character)
        return model
    }

    /// How a helper looks for each status: dozing in the queue, thinking at work, worried when it needs you.
    static func update(_ model: MiloModel, for helper: HelperInfo, character: CharacterStyle) {
        let (state, emotion): (MiloState, Emotion) = switch helper.status {
        case .queued: (.idle, .neutral)
        case .working: (.thinking, .thinking)
        case .needsYou: (.idle, .concerned)
        case .done: (.idle, .happy)
        case .failed: (.idle, .confused)
        case .stopped: (.idle, .neutral)
        }
        if model.character != character { model.character = character }
        if model.state != state { model.state = state }
        if model.emotion != emotion { model.emotion = emotion }
        let dozing = helper.status == .queued
        if model.drowsy != dozing { model.drowsy = dozing }
    }

    static func statusWords(_ status: HelperInfo.Status) -> String {
        switch status {
        case .queued: "waiting its turn"
        case .working: "working"
        case .needsYou: "needs your answer"
        case .done: "done"
        case .failed: "couldn't finish"
        case .stopped: "stopped"
        }
    }
}

/// Milo's figure view, scaled down and still. It is the same view the big Milo uses, so the character
/// setting (and every skin it can pick) shows on the helpers too.
struct HelperFigure: View {
    @ObservedObject var model: MiloModel
    var size: CGFloat

    var body: some View {
        CharacterView(model: model, still: true)
            .frame(width: 132, height: 132)
            .scaleEffect(size / 132)
            .frame(width: size, height: size)
            .allowsHitTesting(false)
    }
}

/// A small mark on a helper's corner: a question when it needs you, a check when done, a cross when it
/// couldn't finish, "z" while it waits its turn. Nothing while it works: the thinking figure says that.
struct HelperMark: View {
    @Environment(\.miloTheme) private var theme
    let status: HelperInfo.Status

    var body: some View {
        switch status {
        case .working:
            EmptyView()
        case .queued:
            mark("z", theme.tint, text: theme.primary)
        case .needsYou:
            mark("?", Palette.think, text: Palette.face)
        case .done:
            symbol("checkmark", WindowColors.done)
        case .failed:
            symbol("xmark", WindowColors.failed)
        case .stopped:
            symbol("stop.fill", Color.gray)
        }
    }

    private func mark(_ text: String, _ fill: Color, text color: Color) -> some View {
        Text(text)
            .font(.system(size: 10, weight: .heavy, design: .rounded))
            .foregroundStyle(color)
            .frame(width: 15, height: 15)
            .background(Circle().fill(fill))
            .overlay(Circle().stroke(Color.white.opacity(0.8), lineWidth: 1))
    }

    private func symbol(_ name: String, _ fill: Color) -> some View {
        Image(systemName: name)
            .font(.system(size: 7, weight: .heavy))
            .foregroundStyle(.white)
            .frame(width: 15, height: 15)
            .background(Circle().fill(fill))
            .overlay(Circle().stroke(Color.white.opacity(0.8), lineWidth: 1))
    }
}

/// How far through its plan a helper is: an empty track while it has no plan, full once it is done.
struct ProgressLine: View {
    @Environment(\.miloTheme) private var theme
    let progress: Double?
    let status: HelperInfo.Status

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                Capsule().fill(theme.ink.opacity(0.12))
                if let fraction {
                    Capsule().fill(color).frame(width: max(3, geo.size.width * fraction))
                }
            }
        }
        .opacity(status.active || progress != nil ? 1 : 0)
    }

    private var fraction: Double? {
        if status == .done { return 1 }
        return progress
    }

    private var color: Color {
        switch status {
        case .done: WindowColors.done
        case .failed, .stopped: WindowColors.failed
        case .needsYou: Palette.think
        default: WindowColors.running
        }
    }
}

/// The helpers at the top of the Milo window: each one's figure, title, what it does now, its last steps,
/// and a Stop button. A click on a helper shows its task further down.
struct HelpersPanel: View {
    @Environment(\.miloTheme) private var theme
    let helpers: [HelperInfo]
    let entries: [TranscriptEntry]
    let character: CharacterStyle
    let open: (String) -> Void
    let stop: (String) -> Void
    /// Rows shown before "and 2 more": the conversation keeps most of the window.
    static let rows = 4

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(helpers.count == 1 ? "1 helper" : "\(helpers.count) helpers")
                    .font(.system(size: 11, weight: .semibold, design: .rounded))
                    .foregroundStyle(.secondary)
                Spacer()
                if helpers.filter(\.status.active).count > 1 {
                    Button("Stop all") { helpers.filter(\.status.active).forEach { stop($0.id) } }
                        .buttonStyle(.plain)
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(WindowColors.failed)
                }
            }
            ForEach(helpers.prefix(Self.rows)) { helper in
                HelperRow(helper: helper, steps: steps(of: helper), character: character,
                          open: { open(helper.id) }, stop: { stop(helper.id) })
            }
            if helpers.count > Self.rows {
                Text("and \(helpers.count - Self.rows) more in the conversation below")
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(theme.ink.opacity(0.05))
        .overlay(alignment: .bottom) { Rectangle().fill(theme.rule).frame(height: 1) }
    }

    private func steps(of helper: HelperInfo) -> [ActivityStep] {
        Array((entries.last(where: { $0.id == helper.id })?.steps ?? []).suffix(2))
    }
}

struct HelperRow: View {
    let helper: HelperInfo
    let steps: [ActivityStep]
    let character: CharacterStyle
    let open: () -> Void
    let stop: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Button(action: open) {
                HStack(alignment: .top, spacing: 10) {
                    HelperBird.Mini(helper: helper, character: character)
                    VStack(alignment: .leading, spacing: 3) {
                        HStack(spacing: 6) {
                            Text(helper.title)
                                .font(.system(size: 12.5, weight: .semibold, design: .rounded))
                                .lineLimit(1)
                            Text(HelperBird.statusWords(helper.status))
                                .font(.system(size: 10.5, weight: .medium))
                                .foregroundStyle(helper.status == .needsYou ? WindowColors.running : Color.secondary)
                        }
                        if !helper.step.isEmpty {
                            Text(helper.step)
                                .font(.system(size: 11.5))
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                        }
                        ForEach(steps.dropLast(helper.step == steps.last?.title ? 1 : 0)) { step in
                            HStack(spacing: 5) {
                                Image(systemName: StepRow.icon(step.kind))
                                    .font(.system(size: 9))
                                    .frame(width: 11)
                                Text(step.title).lineLimit(1)
                            }
                            .font(.system(size: 10.5))
                            .foregroundStyle(.tertiary)
                        }
                        if let progress = helper.progress, helper.status.active {
                            ProgressLine(progress: progress, status: helper.status)
                                .frame(width: 120, height: 3)
                                .padding(.top, 2)
                        }
                    }
                    Spacer(minLength: 0)
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .help("Show this in the conversation")
            if helper.status.active {
                Button(action: stop) {
                    Text("Stop")
                        .font(.system(size: 11.5, weight: .medium))
                        .padding(.horizontal, 10)
                        .padding(.vertical, 4)
                        // A capsule border this small draws a short bar at each end; a rounded rectangle doesn't.
                        .background(RoundedRectangle(cornerRadius: 7, style: .continuous)
                            .strokeBorder(WindowColors.failed.opacity(0.6), lineWidth: 1))
                        .foregroundStyle(WindowColors.failed)
                }
                .buttonStyle(.plain)
                .help("Stop this helper")
                .accessibilityLabel("Stop \(helper.title)")
            }
        }
    }
}

extension HelperBird {
    /// The figure alone, for rows in the Milo window.
    struct Mini: View {
        let helper: HelperInfo
        let character: CharacterStyle
        @StateObject private var figure: MiloModel

        init(helper: HelperInfo, character: CharacterStyle) {
            self.helper = helper
            self.character = character
            _figure = StateObject(wrappedValue: HelperBird.figureModel(for: helper, character: character))
        }

        var body: some View {
            HelperFigure(model: figure, size: 30)
                .overlay(alignment: .topTrailing) { HelperMark(status: helper.status).scaleEffect(0.8).offset(x: 3, y: -1) }
                .onChange(of: helper) { HelperBird.update(figure, for: helper, character: character) }
                .onChange(of: character) { HelperBird.update(figure, for: helper, character: character) }
        }
    }
}
