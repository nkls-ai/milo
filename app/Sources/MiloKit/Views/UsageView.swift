import Charts
import SwiftUI

/// The Usage page: how much Milo did for you, day by day, and the accounts he does it with. The numbers come from
/// the brain's usage ledger and dictation history (`get_usage`); opening the page costs no model call.
struct UsageView: View {
    @Environment(\.miloTheme) private var theme
    @ObservedObject var usage: UsageModel
    @ObservedObject var model: MiloModel
    @State private var metric = Metric.tokens

    enum Metric: String, CaseIterable, Identifiable {
        case tokens = "Tokens"
        case words = "Words dictated"
        var id: String { rawValue }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                header.padding(.bottom, 4)
                if let report = usage.report {
                    tiles(report)
                    activity(report)
                    if !report.sources.isEmpty || !report.apps.isEmpty {
                        ViewThatFits(in: .horizontal) {
                            HStack(alignment: .top, spacing: 12) { breakdowns(report) }
                            VStack(spacing: 12) { breakdowns(report) }
                        }
                    }
                    accounts(report)
                } else {
                    waiting
                }
            }
            .padding(.horizontal, 24)
            .padding(.top, 22)
            .padding(.bottom, 24)
            .frame(maxWidth: 720, alignment: .leading)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .onAppear { usage.refresh() }
        .onChange(of: model.connected) { if model.connected { usage.refresh() } }
    }

    // ---- the parts

    private var header: some View {
        HStack(alignment: .bottom, spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                Text(sinceLine)
                    .font(.system(size: 12, weight: .semibold, design: .rounded))
                    .foregroundStyle(theme.primary)
                Text("Your usage")
                    .font(.system(size: 24, weight: .bold, design: .rounded))
                    .foregroundStyle(theme.ink)
            }
            Spacer(minLength: 8)
            Picker("Range", selection: Binding(get: { usage.span }, set: { usage.show(span: $0) })) {
                ForEach(UsageModel.spans, id: \.self) { Text("\($0) days").tag($0) }
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .fixedSize()
        }
    }

    private var sinceLine: String {
        guard let since = usage.report.flatMap({ UsageDay.parse($0.since) }) else { return "Milo on this Mac" }
        return "With Milo since \(since.formatted(.dateTime.day().month(.wide).year()))"
    }

    private var waiting: some View {
        VStack(spacing: 10) {
            if model.connected {
                ProgressView().controlSize(.small)
                Text("Counting…")
            } else {
                Image(systemName: "bolt.horizontal.circle")
                    .font(.system(size: 22, weight: .medium))
                    .foregroundStyle(theme.primary.opacity(0.7))
                Text("Milo's brain isn't running, so there's nothing to count yet.")
            }
        }
        .font(.system(size: 12.5))
        .foregroundStyle(theme.ink.opacity(0.58))
        .frame(maxWidth: .infinity)
        .padding(.vertical, 40)
    }

    // ---- the headline numbers

    private func tiles(_ r: UsageReport) -> some View {
        let cached = r.tokens > 0 ? Int((Double(r.cachedTokens) / Double(r.tokens) * 100).rounded()) : 0
        return ViewThatFits(in: .horizontal) {
            HStack(spacing: 10) { tileRow(r, cached: cached) }
            VStack(spacing: 10) {
                HStack(spacing: 10) { tileRow(r, cached: cached).prefix2 }
                HStack(spacing: 10) { tileRow(r, cached: cached).suffix2 }
            }
        }
    }

    private func tileRow(_ r: UsageReport, cached: Int) -> TileRow {
        TileRow(tiles: [
            StatTile(value: Self.compact(r.tokens), label: "Tokens",
                     note: r.tokens > 0 ? "\(cached)% from cache" : "No model calls yet", icon: "sparkles",
                     tint: theme.primary),
            StatTile(value: Self.compact(r.calls), label: r.calls == 1 ? "Model call" : "Model calls",
                     note: "Talking, tasks, upkeep", icon: "bubble.left.and.bubble.right.fill", tint: theme.primary),
            StatTile(value: Self.compact(r.dictations), label: r.dictations == 1 ? "Dictation" : "Dictations",
                     note: "\(Self.compact(r.words)) words", icon: "waveform", tint: theme.accent),
            StatTile(value: "\(r.activeDays)", label: r.activeDays == 1 ? "Active day" : "Active days",
                     note: r.streak > 1 ? "\(r.streak) days in a row" : "of the last \(r.span)", icon: "flame.fill",
                     tint: theme.accent),
        ])
    }

    // ---- day by day

    private func activity(_ r: UsageReport) -> some View {
        TodayCard(title: "Day by day", icon: "chart.bar.fill", tint: theme.primary) {
            Picker("Show", selection: $metric) {
                ForEach(Metric.allCases) { Text($0.rawValue).tag($0) }
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .fixedSize()
            DailyChart(days: r.daily, metric: metric, tint: metric == .tokens ? theme.primary : theme.accent)
                .frame(height: 170)
        }
    }

    // ---- where it went

    @ViewBuilder private func breakdowns(_ r: UsageReport) -> some View {
        if !r.sources.isEmpty {
            TodayCard(title: "Where the tokens went", icon: "sparkles", tint: theme.primary) {
                ShareBars(rows: r.sources.map { ($0.label, $0.tokens, Self.compact($0.tokens)) }, tint: theme.primary)
            }
        }
        if !r.apps.isEmpty {
            TodayCard(title: "Where your words went", icon: "text.cursor", tint: theme.accent) {
                ShareBars(rows: r.apps.map { ($0.label, $0.words, "\(Self.compact($0.words)) words") },
                          tint: theme.accent)
            }
        }
    }

    // ---- accounts

    private func accounts(_ r: UsageReport) -> some View {
        TodayCard(title: "Accounts Milo uses", icon: "person.crop.circle.fill", tint: theme.primary) {
            if r.accounts.isEmpty {
                HStack(spacing: 8) {
                    ProgressView().controlSize(.mini)
                    Text("Checking who Milo is signed in as…")
                        .font(.system(size: 12))
                        .foregroundStyle(theme.ink.opacity(0.55))
                }
            }
            ForEach(Array(r.accounts.enumerated()), id: \.element.id) { i, account in
                if i > 0 { Rectangle().fill(theme.rule).frame(height: 1) }
                AccountRow(account: account)
            }
        }
    }

    /// 1,234 → "1.2K", 3,400,000 → "3.4M"; small numbers stay whole.
    static func compact(_ n: Int) -> String {
        n < 10_000 ? n.formatted() : n.formatted(.number.notation(.compactName).precision(.fractionLength(0...1)))
    }
}

/// Four tiles that wrap two by two in a narrow window.
private struct TileRow: View {
    let tiles: [StatTile]

    var body: some View { ForEach(Array(tiles.enumerated()), id: \.offset) { $0.element } }
    var prefix2: TileRow { TileRow(tiles: Array(tiles.prefix(2))) }
    var suffix2: TileRow { TileRow(tiles: Array(tiles.suffix(2))) }
}

/// One headline number: big value, what it counts, and one quiet line of context.
private struct StatTile: View {
    @Environment(\.miloTheme) private var theme
    let value: String
    let label: String
    let note: String
    let icon: String
    let tint: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 6) {
                Image(systemName: icon)
                    .font(.system(size: 10, weight: .bold))
                    .foregroundStyle(tint)
                    .frame(width: 20, height: 20)
                    .background(Circle().fill(tint.opacity(0.15)))
                Text(label)
                    .font(.system(size: 11.5, weight: .semibold, design: .rounded))
                    .foregroundStyle(theme.ink.opacity(0.62))
                    .lineLimit(1)
            }
            Text(value)
                .font(.system(size: 26, weight: .bold, design: .rounded).monospacedDigit())
                .foregroundStyle(theme.ink)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
            Text(note)
                .font(.system(size: 11))
                .foregroundStyle(theme.ink.opacity(0.5))
                .lineLimit(1)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .frame(minWidth: 140, maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(theme.card))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).strokeBorder(theme.rule, lineWidth: 1))
        .shadow(color: theme.primary.opacity(0.06), radius: 10, y: 3)
        .accessibilityElement(children: .combine)
    }
}

/// Bars for each day of the range, one series. Hovering a day shows its numbers.
private struct DailyChart: View {
    @Environment(\.miloTheme) private var theme
    let days: [UsageDay]
    let metric: UsageView.Metric
    let tint: Color
    @State private var hovered: Date?

    private var points: [(date: Date, day: UsageDay)] { days.compactMap { d in d.date.map { ($0, d) } } }

    private func value(_ d: UsageDay) -> Int { metric == .tokens ? d.tokens : d.words }

    private var selected: (date: Date, day: UsageDay)? {
        guard let hovered else { return nil }
        return points.first { Calendar.current.isDate($0.date, inSameDayAs: hovered) }
    }

    var body: some View {
        let empty = points.allSatisfy { value($0.day) == 0 }
        Chart {
            ForEach(points, id: \.day.id) { point in
                BarMark(x: .value("Day", point.date, unit: .day), y: .value(metric.rawValue, value(point.day)))
                    .foregroundStyle(tint.opacity(selected == nil || selected?.day.id == point.day.id ? 1 : 0.45))
                    .clipShape(UnevenRoundedRectangle(topLeadingRadius: 4, topTrailingRadius: 4))
            }
            if let selected {
                RuleMark(x: .value("Day", selected.date, unit: .day))
                    .foregroundStyle(theme.ink.opacity(0.12))
                    .lineStyle(StrokeStyle(lineWidth: 1))
                    .zIndex(-1)
                    .annotation(position: .top, spacing: 4,
                                overflowResolution: .init(x: .fit(to: .chart), y: .disabled)) {
                        tooltip(selected.day, selected.date)
                    }
            }
        }
        .chartXSelection(value: $hovered)
        .chartYAxis {
            AxisMarks(position: .leading, values: .automatic(desiredCount: 3)) { value in
                AxisGridLine().foregroundStyle(theme.rule)
                AxisValueLabel {
                    if let n = value.as(Int.self) { Text(UsageView.compact(n)) }
                }
                .foregroundStyle(theme.ink.opacity(0.45))
            }
        }
        .chartXAxis {
            AxisMarks(values: .automatic(desiredCount: 6)) { _ in
                AxisValueLabel(format: .dateTime.day().month(.abbreviated))
                    .foregroundStyle(theme.ink.opacity(0.45))
            }
        }
        .overlay {
            if empty {
                Text(metric == .tokens ? "No model calls in this range." : "Nothing dictated in this range.")
                    .font(.system(size: 12))
                    .foregroundStyle(theme.ink.opacity(0.5))
            }
        }
        .accessibilityLabel("\(metric.rawValue) per day")
    }

    private func tooltip(_ day: UsageDay, _ date: Date) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(date.formatted(.dateTime.weekday(.abbreviated).day().month(.abbreviated)))
                .font(.system(size: 10.5, weight: .semibold, design: .rounded))
                .foregroundStyle(theme.ink.opacity(0.6))
            if metric == .tokens {
                Text("\(day.tokens.formatted()) tokens").font(.system(size: 12, weight: .bold, design: .rounded))
                Text("\(day.calls) \(day.calls == 1 ? "call" : "calls")").font(.system(size: 10.5))
                    .foregroundStyle(theme.ink.opacity(0.6))
            } else {
                Text("\(day.words.formatted()) words").font(.system(size: 12, weight: .bold, design: .rounded))
                Text("\(day.dictations) \(day.dictations == 1 ? "dictation" : "dictations")").font(.system(size: 10.5))
                    .foregroundStyle(theme.ink.opacity(0.6))
            }
        }
        .foregroundStyle(theme.ink)
        .padding(.horizontal, 9)
        .padding(.vertical, 6)
        .background(RoundedRectangle(cornerRadius: 9, style: .continuous).fill(theme.card)
            .shadow(color: .black.opacity(0.12), radius: 6, y: 2))
        .overlay(RoundedRectangle(cornerRadius: 9, style: .continuous).strokeBorder(theme.rule, lineWidth: 1))
    }
}

/// Each row's share of the largest, as a thin bar under its label and value.
private struct ShareBars: View {
    @Environment(\.miloTheme) private var theme
    let rows: [(label: String, value: Int, shown: String)]
    let tint: Color

    var body: some View {
        let top = max(1, rows.map(\.value).max() ?? 1)
        VStack(alignment: .leading, spacing: 9) {
            ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text(row.label)
                            .font(.system(size: 12.5, weight: .medium, design: .rounded))
                            .foregroundStyle(theme.ink)
                            .lineLimit(1)
                        Spacer(minLength: 6)
                        Text(row.shown)
                            .font(.system(size: 11.5).monospacedDigit())
                            .foregroundStyle(theme.ink.opacity(0.55))
                    }
                    GeometryReader { g in
                        Capsule().fill(theme.ink.opacity(0.06))
                            .overlay(alignment: .leading) {
                                Capsule().fill(tint)
                                    .frame(width: max(4, g.size.width * CGFloat(row.value) / CGFloat(top)))
                            }
                    }
                    .frame(height: 5)
                }
                .accessibilityElement(children: .combine)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// A service: its name and plan, who Milo is signed in as, what he uses it for, and whether it works.
private struct AccountRow: View {
    @Environment(\.miloTheme) private var theme
    let account: UsageAccount

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: icon)
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(theme.primary)
                .frame(width: 30, height: 30)
                .background(Circle().fill(theme.primary.opacity(0.12)))
            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 6) {
                    Text(account.service)
                        .font(.system(size: 13.5, weight: .semibold, design: .rounded))
                        .foregroundStyle(theme.ink)
                    if !account.plan.isEmpty {
                        Text(account.plan)
                            .font(.system(size: 10.5, weight: .bold, design: .rounded))
                            .foregroundStyle(theme.onPrimary)
                            .padding(.horizontal, 7)
                            .padding(.vertical, 1.5)
                            .background(Capsule().fill(theme.primary))
                    }
                }
                Text(account.uses.joined(separator: " · "))
                    .font(.system(size: 11.5))
                    .foregroundStyle(theme.ink.opacity(0.6))
                if !account.who.isEmpty || !account.detail.isEmpty {
                    Text([account.who, account.detail].filter { !$0.isEmpty }.joined(separator: " · "))
                        .font(.system(size: 11))
                        .foregroundStyle(theme.ink.opacity(0.45))
                        .fixedSize(horizontal: false, vertical: true)
                        .textSelection(.enabled)
                }
            }
            Spacer(minLength: 8)
            StateBadge(state: account.state)
        }
        .accessibilityElement(children: .combine)
    }

    private var icon: String {
        switch account.service {
        case "This Mac": "laptopcomputer"
        case "ElevenLabs": "waveform"
        default: "person.fill"
        }
    }
}

/// Signed in, signed out, can't tell, or on this Mac: an icon and a word, never colour alone.
private struct StateBadge: View {
    @Environment(\.miloTheme) private var theme
    let state: UsageAccount.State

    var body: some View {
        let (icon, label, tint): (String, String, Color) = switch state {
        case .ok: ("checkmark.circle.fill", "Signed in", WindowColors.done)
        case .signedOut: ("xmark.circle.fill", "Signed out", WindowColors.failed)
        case .unknown: ("questionmark.circle.fill", "Can't tell", WindowColors.running)
        case .local: ("lock.fill", "Private", theme.primary)
        }
        HStack(spacing: 4) {
            Image(systemName: icon).foregroundStyle(tint)
            Text(label).foregroundStyle(theme.ink.opacity(0.7))
        }
        .font(.system(size: 11, weight: .semibold, design: .rounded))
        .fixedSize()
    }
}
