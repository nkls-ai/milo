import SwiftUI

/// The setup window: what Milo needs permission for and why, a button to each place in System Settings, a
/// check mark as soon as it's on, and a last step to try him out.
public struct SetupView: View {
    @ObservedObject var setup: SetupModel
    let done: () -> Void

    public init(setup: SetupModel, done: @escaping () -> Void) {
        self.setup = setup
        self.done = done
    }

    public var body: some View {
        VStack(spacing: 0) {
            Form {
                Section {
                    ForEach(setup.rows.filter { !$0.optional }) { PermissionRow(row: $0, fix: setup.fix) }
                } header: {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Let's get Milo ready")
                            .font(.title2.weight(.semibold))
                            .foregroundStyle(.primary)
                        Text("Milo needs your OK for a few things. Each button opens the right place in System Settings: switch Milo on there, then come back here.")
                            .font(.body)
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .padding(.bottom, 8)
                }
                Section("Only if you want Milo to help with these") {
                    ForEach(setup.rows.filter(\.optional)) { PermissionRow(row: $0, fix: setup.fix) }
                }
                Section {
                    HStack(alignment: .top, spacing: 12) {
                        Mark(done: setup.tried)
                        VStack(alignment: .leading, spacing: 3) {
                            Text("Try it: hold \(setup.dictateKey) and say something")
                                .font(.body.weight(.medium))
                            Text(setup.tried ? "Milo heard you. You're all set."
                                             : "Milo listens while you hold the key, and types your words where your cursor is when you let go.")
                                .foregroundStyle(.secondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                    .padding(.vertical, 2)
                }
            }
            .formStyle(.grouped)

            Divider()
            HStack {
                Spacer()
                Button("Done", action: done)
                    .keyboardShortcut(.defaultAction)
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 12)
        }
        .background(Color(nsColor: .windowBackgroundColor))
        .frame(minWidth: 480, idealWidth: 520, minHeight: 560, idealHeight: 780)
    }
}

struct PermissionRow: View {
    let row: SetupModel.Row
    let fix: (Permission) -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Mark(done: row.state == .granted)
            VStack(alignment: .leading, spacing: 3) {
                Text(row.title).font(.body.weight(.medium))
                Text(row.reason)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 8)
            if row.state != .granted {
                Button(row.state == .notAsked ? "Allow…" : "Open Settings") { fix(row.permission) }
            }
        }
        .padding(.vertical, 2)
        .accessibilityElement(children: .combine)
        .accessibilityValue(row.state == .granted ? "allowed" : "not allowed yet")
    }
}

/// A green check once something is done, an empty circle until then.
private struct Mark: View {
    let done: Bool

    var body: some View {
        Image(systemName: done ? "checkmark.circle.fill" : "circle")
            .font(.system(size: 18))
            .foregroundStyle(done ? Color.green : Color.secondary.opacity(0.6))
            .frame(width: 22)
            .animation(.easeOut(duration: 0.2), value: done)
    }
}
