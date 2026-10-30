import SwiftUI

/// The setup window: for each permission a little scene of what Milo does with it, one plain sentence, a clear
/// button, and a tick that draws itself the moment macOS says yes. Ends with trying him out.
public struct SetupView: View {
    @ObservedObject var setup: SetupModel
    @Environment(\.miloTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let done: () -> Void

    public init(setup: SetupModel, done: @escaping () -> Void) {
        self.setup = setup
        self.done = done
    }

    public var body: some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    header
                    ForEach(setup.rows.filter { !$0.optional }) { card($0) }
                    Text("If you'd like Milo to help with these too")
                        .font(.system(size: 13, weight: .semibold, design: .rounded))
                        .foregroundStyle(theme.ink.opacity(0.7))
                        .padding(.top, 10)
                        .padding(.leading, 4)
                    ForEach(setup.rows.filter(\.optional)) { card($0) }
                    tryIt.padding(.top, 10)
                }
                .padding(22)
            }
            HStack {
                Text(progress)
                    .font(.system(size: 12, design: .rounded))
                    .foregroundStyle(theme.ink.opacity(0.6))
                Spacer()
                Button("Done", action: done)
                    .buttonStyle(PillButtonStyle())
                    .keyboardShortcut(.defaultAction)
            }
            .padding(.horizontal, 22)
            .padding(.vertical, 12)
            .background(theme.card.opacity(0.6))
            .overlay(alignment: .top) { Rectangle().fill(theme.rule).frame(height: 1) }
        }
        .background(theme.tint)
        .animation(theme.motion.animation(reduced: reduceMotion), value: setup.rows)
        .animation(theme.motion.animation(reduced: reduceMotion), value: setup.stuck)
        .animation(theme.motion.animation(reduced: reduceMotion), value: setup.restartForScreen)
        .animation(theme.motion.gentle, value: theme)
        .frame(minWidth: 520, idealWidth: 560, minHeight: 600, idealHeight: 820)
    }

    private var required: [SetupModel.Row] { setup.rows.filter { !$0.optional } }

    private var progress: String {
        let ready = required.filter { $0.state == .granted }.count
        return ready == required.count ? "Milo has everything he needs." : "\(ready) of \(required.count) done"
    }

    private var header: some View {
        HStack(spacing: 14) {
            CharacterFigure(for: theme.style, emotion: setup.needsAttention ? .happy : .excited, size: 74)
                .frame(width: 74, height: 74)
                .background(Circle().fill(RadialGradient(colors: [theme.glow.opacity(0.45), theme.glow.opacity(0)], center: .center, startRadius: 4, endRadius: 50)).frame(width: 110, height: 110))
            VStack(alignment: .leading, spacing: 5) {
                Text(setup.needsAttention ? "Hi! Let's get me ready." : "All set. Thank you!")
                    .font(.system(size: 22, weight: .bold, design: .rounded))
                    .foregroundStyle(theme.ink)
                Text("Each button takes you to the right switch in System Settings. Turn me on there and come back: I'll tick it off.")
                    .font(.system(size: 13))
                    .foregroundStyle(theme.ink.opacity(0.65))
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.bottom, 6)
    }

    private func card(_ row: SetupModel.Row) -> some View {
        let granted = row.state == .granted
        return ThemedCard(padding: 12) {
            VStack(alignment: .leading, spacing: 10) {
                HStack(alignment: .center, spacing: 14) {
                    PermissionScene(permission: row.permission, playing: setup.watching && !granted,
                                    still: granted ? 2 : (setup.watching ? 0 : 2))
                    VStack(alignment: .leading, spacing: 6) {
                        HStack(spacing: 8) {
                            Text(row.title)
                                .font(.system(size: 15, weight: .semibold, design: .rounded))
                                .foregroundStyle(theme.ink)
                            Spacer(minLength: 0)
                            CheckBadge(done: granted)
                        }
                        Text(row.reason)
                            .font(.system(size: 12.5))
                            .foregroundStyle(theme.ink.opacity(0.7))
                            .fixedSize(horizontal: false, vertical: true)
                        if granted {
                            Text("Done")
                                .font(.system(size: 12, weight: .semibold, design: .rounded))
                                .foregroundStyle(theme.primary)
                        } else {
                            Button(buttonTitle(row)) { setup.fix(row.permission) }
                                .buttonStyle(PillButtonStyle())
                                .padding(.top, 2)
                        }
                    }
                }
                notes(row)
            }
        }
    }

    private func buttonTitle(_ row: SetupModel.Row) -> String {
        if row.state == .notAsked && SetupModel.asksInADialog.contains(row.permission) { return "Allow" }
        return "Open System Settings"
    }

    @ViewBuilder private func notes(_ row: SetupModel.Row) -> some View {
        if row.state != .granted {
            if setup.stuck.contains(row.permission) {
                Callout(icon: "wrench.and.screwdriver",
                        text: "Switched on but no tick? After an update macOS can keep an old Milo in the list. Fix it clears him out, so you can switch the new one on.",
                        button: "Fix it") { setup.repair(row.permission) }
            } else if setup.helper == row.permission {
                Callout(icon: "hand.point.up.left",
                        text: "Don't see Milo in the list? Drag him in from the little window next to it, then switch him on.")
            }
            if row.permission == .screenRecording, setup.restartForScreen {
                Callout(icon: "arrow.clockwise",
                        text: "Switched on? macOS only counts it after Milo restarts.",
                        button: "Restart Milo") { setup.restart?() }
            }
        }
    }

    private var tryIt: some View {
        ThemedCard(padding: 12) {
            HStack(alignment: .center, spacing: 14) {
                PermissionScene(permission: nil, playing: setup.watching && !setup.tried, key: setup.dictateKey)
                VStack(alignment: .leading, spacing: 6) {
                    HStack {
                        Text("Try it: hold \(setup.dictateKey) and say something")
                            .font(.system(size: 15, weight: .semibold, design: .rounded))
                            .foregroundStyle(theme.ink)
                        Spacer(minLength: 0)
                        CheckBadge(done: setup.tried)
                    }
                    Text(setup.tried ? "I heard you. We're all set."
                                     : "I listen while you hold the key, and type your words where your cursor is when you let go.")
                        .font(.system(size: 12.5))
                        .foregroundStyle(theme.ink.opacity(0.7))
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }
}

/// The little floating window next to System Settings: Milo as a tile to drag into the permission's list.
public struct DragHelperView: View {
    @Environment(\.miloTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let appURL: URL
    let icon: NSImage
    let close: () -> Void
    @State private var lifted = false

    public init(appURL: URL, icon: NSImage, close: @escaping () -> Void) {
        self.appURL = appURL
        self.icon = icon
        self.close = close
    }

    public var body: some View {
        VStack(spacing: 10) {
            VStack(spacing: 4) {
                Image(nsImage: icon)
                    .resizable()
                    .frame(width: 56, height: 56)
                Text("Milo")
                    .font(.system(size: 12, weight: .semibold, design: .rounded))
                    .foregroundStyle(theme.ink)
            }
            .padding(12)
            .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(theme.card))
            .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous)
                .strokeBorder(theme.primary.opacity(0.6), style: StrokeStyle(lineWidth: 1.5, dash: [5, 4])))
            .shadow(color: theme.primary.opacity(lifted ? 0.3 : 0.12), radius: lifted ? 12 : 5, y: lifted ? 6 : 2)
            .scaleEffect(lifted ? 1.05 : 1)
            .onHover { hovering in
                withAnimation(theme.motion.animation(reduced: reduceMotion)) { lifted = hovering }
            }
            .onDrag { NSItemProvider(object: appURL as NSURL) }
            .help("Drag me into the list in System Settings")
            Text("Drag Milo into the list, then switch him on.")
                .font(.system(size: 12.5, weight: .medium))
                .foregroundStyle(theme.ink)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
            Button("Close", action: close)
                .buttonStyle(PillButtonStyle(prominent: false))
        }
        .padding(16)
        .frame(width: 210)
        .background(theme.tint)
    }
}
