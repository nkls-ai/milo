import SwiftUI

/// The Settings window: how Milo looks, how much he tells you, how dictation behaves, his keys and his voice.
/// Every choice comes from the brain's `settings` report and goes back to it; nothing is stored in the app.
public struct SettingsView: View {
    @ObservedObject var settings: SettingsModel
    @ObservedObject var model: MiloModel
    let restart: () -> Void

    public init(settings: SettingsModel, model: MiloModel, restart: @escaping () -> Void) {
        self.settings = settings
        self.model = model
        self.restart = restart
    }

    public var body: some View {
        Group {
            if let report = settings.report {
                form(report)
            } else {
                VStack(spacing: 10) {
                    ProgressView().controlSize(.small)
                    Text(model.connected ? "Getting Milo's settings…" : "Milo is starting up…")
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .frame(minWidth: 460, idealWidth: 500, minHeight: 420, idealHeight: 640)
    }

    private func form(_ report: SettingsReport) -> some View {
        Form {
            if let look = report["ui", "character"] {
                Section("Look") {
                    LookPicker(setting: look) { settings.change("ui", "character", to: $0) }
                }
            }
            if let updates = report["chat", "updates"] {
                Section {
                    choice(updates, "How often Milo tells you what he's doing")
                }
            }
            if let stream = report["dictation", "stream"] {
                Section("Dictation") {
                    choice(stream, "When your words appear")
                }
            }
            Section("Keys") {
                if let key = report["ui", "dictate_key"] { menu(key, "Hold to dictate") }
                if let key = report["ui", "talk_key"] { menu(key, "Hold to talk to Milo") }
                if let key = report["ui", "whats_this_key"] { menu(key, "Ask “What's this?”") }
            }
            if let voice = report["ui", "voice"] {
                Section {
                    Toggle("Milo says his answers out loud", isOn: Binding(
                        get: { voice.value.bool ?? true },
                        set: { settings.change(voice.section, voice.key, to: .bool($0)) }))
                }
            }
            if !report.error.isEmpty || report.restart {
                Section {
                    if !report.error.isEmpty {
                        Label(report.error, systemImage: "exclamationmark.triangle")
                            .foregroundStyle(.orange)
                    }
                    if report.restart {
                        HStack {
                            Text("Some changes start working after Milo restarts.")
                            Spacer()
                            Button("Restart Milo", action: restart)
                        }
                    }
                }
            }
        }
        .formStyle(.grouped)
    }

    /// A few choices, all visible at once.
    private func choice(_ setting: Setting, _ title: String) -> some View {
        Picker(title, selection: binding(setting)) {
            ForEach(setting.choices, id: \.label) { Text($0.label).tag($0.value) }
        }
        .pickerStyle(.radioGroup)
    }

    /// Many choices or a short label: a pop-up menu.
    private func menu(_ setting: Setting, _ title: String) -> some View {
        Picker(title, selection: binding(setting)) {
            ForEach(setting.choices, id: \.label) { Text($0.label).tag($0.value) }
        }
    }

    private func binding(_ setting: Setting) -> Binding<JSONValue> {
        Binding(get: { setting.value }, set: { settings.change(setting.section, setting.key, to: $0) })
    }
}

/// One tile per look, each a small live Milo. The chosen one is happy and ringed.
struct LookPicker: View {
    let setting: Setting
    let choose: (JSONValue) -> Void

    var body: some View {
        HStack(spacing: 6) {
            ForEach(Array(setting.choices.enumerated()), id: \.offset) { _, choice in
                if let name = choice.value.string, let style = CharacterStyle(rawValue: name) {
                    tile(style, label: choice.label, chosen: choice.value == setting.value)
                }
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 4)
    }

    private func tile(_ style: CharacterStyle, label: String, chosen: Bool) -> some View {
        Button {
            choose(.string(style.rawValue))
        } label: {
            VStack(spacing: 4) {
                CharacterFigure(for: style, emotion: chosen ? .happy : .neutral, size: 72)
                    .frame(width: 72, height: 72)
                Text(label)
                    .font(.callout.weight(chosen ? .semibold : .regular))
                    .foregroundStyle(chosen ? .primary : .secondary)
            }
            .padding(.vertical, 8)
            .frame(maxWidth: .infinity)
            .background(RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(chosen ? Color.accentColor.opacity(0.14) : Color.clear))
            .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous)
                .strokeBorder(chosen ? Color.accentColor : Color.clear, lineWidth: 2))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(label)
        .accessibilityAddTraits(chosen ? .isSelected : [])
    }
}
