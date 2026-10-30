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
        }
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

