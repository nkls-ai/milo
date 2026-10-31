import SwiftUI

/// The Settings window: how Milo looks, how much he tells you, how dictation behaves, his keys and his voice.
/// Every choice comes from the brain's `settings` report and goes back to it; nothing is stored in the app.
public struct SettingsView: View {
    @ObservedObject var settings: SettingsModel
    @ObservedObject var model: MiloModel
    @Environment(\.miloTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let restart: () -> Void
    /// Opens dictionary.md, the words Milo learned from your fixes. nil: no button.
    let showWords: (() -> Void)?

    public init(settings: SettingsModel, model: MiloModel, restart: @escaping () -> Void,
                showWords: (() -> Void)? = nil) {
        self.settings = settings
        self.model = model
        self.restart = restart
        self.showWords = showWords
    }

    public var body: some View {
        Group {
            if let report = settings.report {
                ScrollView { content(report).padding(22) }
            } else {
                waiting
            }
        }
        .frame(minWidth: 480, idealWidth: 520, maxWidth: .infinity, minHeight: 420, idealHeight: 760, maxHeight: .infinity)
        .background(theme.tint)
        .animation(theme.motion.gentle, value: theme)
        .animation(theme.motion.animation(reduced: reduceMotion), value: settings.report)
    }

    private var waiting: some View {
        VStack(spacing: 12) {
            CharacterFigure(for: theme.style, state: .thinking, emotion: .thinking, size: 72)
                .frame(width: 72, height: 72)
            Text(model.connected ? "Getting my settings…" : "I'm just waking up…")
                .font(.system(size: 14, weight: .medium, design: .rounded))
                .foregroundStyle(theme.ink.opacity(0.7))
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func content(_ report: SettingsReport) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            if !report.error.isEmpty {
                Callout(icon: "exclamationmark.bubble", text: report.error)
            }
            if report.restart {
                Callout(icon: "arrow.clockwise", text: "Some changes start working after Milo restarts.",
                        button: "Restart Milo", action: restart)
            }
            if let updates = report["chat", "updates"] {
                ThemedCard {
                    VStack(alignment: .leading, spacing: 10) {
                        CardHeading(icon: "text.bubble", title: "How often Milo tells you what he's doing",
                                    detail: "While he works on something for you.")
                        choices(updates)
                    }
                }
            }
            if let ask = report["approvals", "ask"] {
                ThemedCard { asking(ask, allowed: report["approvals", "allowed_apps"]) }
            }
            if let stream = report["dictation", "stream"] {
                ThemedCard {
                    VStack(alignment: .leading, spacing: 10) {
                        CardHeading(icon: "mic", title: "Dictation", detail: "When your words appear.")
                        choices(stream)
                        if let learn = report["dictation", "learn"] { learnRow(learn) }
                    }
                }
            }
            ThemedCard {
                VStack(alignment: .leading, spacing: 10) {
                    CardHeading(icon: "keyboard", title: "Keys")
                    if let key = report["ui", "dictate_key"] { keyRow(key, "Hold to dictate") }
                    if let key = report["ui", "talk_key"] { keyRow(key, "Hold to talk to Milo") }
                    if let key = report["ui", "whats_this_key"] { keyRow(key, "Ask “What's this?”") }
                    if let key = report["ui", "meeting_key"] { keyRow(key, "Start or stop meeting notes") }
                }
            }
            if let voice = report["ui", "voice"] {
                ThemedCard {
                    HStack {
                        CardHeading(icon: voice.value.bool == false ? "speaker.slash" : "speaker.wave.2",
                                    title: "Milo says his answers out loud",
                                    detail: "Off: answers show in his bubble only.")
                        Spacer(minLength: 12)
                        Toggle("Milo says his answers out loud", isOn: Binding(
                            get: { voice.value.bool ?? true },
                            set: { settings.change(voice.section, voice.key, to: .bool($0)) }))
                            .toggleStyle(.switch)
                            .labelsHidden()
                    }
                }
            }
            if let show = report["hands", "show_window"] {
                ThemedCard {
                    HStack {
                        CardHeading(icon: show.value.bool == false ? "macwindow.on.rectangle" : "macwindow",
                                    title: "Show me the window Milo works in",
                                    detail: "Brings it to the front when he starts. Off: he works behind your windows.")
                        Spacer(minLength: 12)
                        Toggle("Show me the window Milo works in", isOn: Binding(
                            get: { show.value.bool ?? true },
                            set: { settings.change(show.section, show.key, to: .bool($0)) }))
                            .toggleStyle(.switch)
                            .labelsHidden()
                    }
                }
            }
        }
    }

    /// `[approvals] ask` and the apps the user chose Allow always for, each with Remove (ADR 22).
    private func asking(_ ask: Setting, allowed: Setting?) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            CardHeading(icon: ask.value.string == "auto" ? "bolt.fill" : "hand.raised",
                        title: "How often Milo asks before he acts", detail: "While he works in an app for you.")
            choices(ask)
            Text(ask.value.string == "auto"
                 ? "Milo does what you ask without checking first. He always stops for things that can't be undone, "
                   + "sending, buying and money. Passwords and security settings he never touches."
                 : "He always stops for things that can't be undone, sending, buying and money. Passwords and "
                   + "security settings he never touches.")
                .font(.system(size: 11.5, weight: ask.value.string == "auto" ? .medium : .regular))
                .foregroundStyle(ask.value.string == "auto" ? theme.accent : theme.ink.opacity(0.65))
                .fixedSize(horizontal: false, vertical: true)
                .padding(.leading, 26)
            if let allowed { allowedApps(allowed) }
        }
    }

    private func allowedApps(_ setting: Setting) -> some View {
        let apps = setting.value.array ?? []
        return VStack(alignment: .leading, spacing: 6) {
            Text("Always allowed")
                .font(.system(size: 13))
                .foregroundStyle(theme.ink)
            if apps.isEmpty {
                Text("No apps yet. Choose Allow always when Milo asks, and the app shows here.")
                    .font(.system(size: 11))
                    .foregroundStyle(theme.ink.opacity(0.65))
                    .fixedSize(horizontal: false, vertical: true)
            }
            ForEach(Array(apps.enumerated()), id: \.offset) { index, app in
                HStack {
                    Image(systemName: "checkmark.seal")
                        .foregroundStyle(theme.primary)
                    Text(app["name"]?.string.flatMap { $0.isEmpty ? nil : $0 } ?? app["bundle"]?.string ?? "?")
                        .font(.system(size: 13))
                        .foregroundStyle(theme.ink)
                    Spacer()
                    Button("Remove") {
                        var rest = apps
                        rest.remove(at: index)
                        settings.change(setting.section, setting.key, to: .array(rest))
                    }
                    .buttonStyle(AnswerButtonStyle(prominent: false))
                    .controlSize(.small)
                    .accessibilityHint("Milo asks again before he works in this app")
                }
            }
        }
        .padding(.leading, 26)
    }

    /// `[dictation] learn`, and the button that shows what was learned.
    private func learnRow(_ learn: Setting) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Learn from your fixes")
                        .font(.system(size: 13))
                        .foregroundStyle(theme.ink)
                    Text("Fix a word he pasted, and he spells it your way next time.")
                        .font(.system(size: 11))
                        .foregroundStyle(theme.ink.opacity(0.65))
                }
                Spacer(minLength: 12)
                Toggle("Learn from your fixes", isOn: Binding(
                    get: { learn.value.bool ?? true },
                    set: { settings.change(learn.section, learn.key, to: .bool($0)) }))
                    .toggleStyle(.switch)
                    .labelsHidden()
            }
            if let showWords {
                Button("Show the words", action: showWords)
                    .buttonStyle(.link)
                    .font(.system(size: 12))
            }
        }
        .padding(.top, 4)
    }

    private func choices(_ setting: Setting) -> some View {
        ChoiceList(choices: setting.choices, selected: setting.value) {
            settings.change(setting.section, setting.key, to: $0)
        }
    }

    private func keyRow(_ setting: Setting, _ title: String) -> some View {
        HStack {
            Text(title)
                .font(.system(size: 13))
                .foregroundStyle(theme.ink)
            Spacer()
            Picker(title, selection: Binding(get: { setting.value },
                                             set: { settings.change(setting.section, setting.key, to: $0) })) {
                ForEach(setting.choices, id: \.label) { Text($0.label).tag($0.value) }
            }
            .labelsHidden()
            .fixedSize()
        }
        .padding(.leading, 26)
    }
}

