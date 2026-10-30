import Foundation

/// Wires the brain, the keyboard, the context and the text inserter to the model.
/// Knows no concrete adapter; main.swift hands them in.
public final class MiloController {
    public struct Settings: Sendable {
        /// How often context is sent besides on app switch.
        public var contextInterval: TimeInterval
        /// Milo looks sleepy when there was no input for longer than this.
        public var drowsyAfter: TimeInterval
        /// Keys until the brain sends `ui_config`.
        public var bindings: HotkeyBindings
        /// Presses shorter than this are taps: one alone does nothing, two lock hands-free.
        public var minHold: TimeInterval
        /// A press shows the listening state after this long (a tap shorter than that shows nothing).
        public var showAfter: TimeInterval
        /// The second tap must start within this long of the first.
        public var doubleTap: TimeInterval
        /// A hands-free recording stops by itself after this long, until `ui_config` says otherwise.
        public var handsFreeMax: TimeInterval
        /// Show macOS's Accessibility dialog at start when it's missing. Off when the setup window asks instead.
        public var promptForAccessibility: Bool

        public init(contextInterval: TimeInterval = 15, drowsyAfter: TimeInterval = 600,
                    bindings: HotkeyBindings = .default, minHold: TimeInterval = 0.25, showAfter: TimeInterval = 0.08,
                    doubleTap: TimeInterval = 0.35, handsFreeMax: TimeInterval = 300,
                    promptForAccessibility: Bool = true) {
            self.contextInterval = contextInterval
            self.drowsyAfter = drowsyAfter
            self.bindings = bindings
            self.minHold = minHold
            self.showAfter = showAfter
            self.doubleTap = doubleTap
            self.handsFreeMax = handsFreeMax
            self.promptForAccessibility = promptForAccessibility
        }
    }

    public let model: MiloModel
    /// The conversation the Milo window shows.
    public let transcript = TranscriptModel()
    /// What the "What Milo knows" window shows.
    public let knowledge = KnowledgeModel()
    /// What the Settings window shows and changes. The menu's "Dictation style" reads and changes it too.
    public let settingsModel = SettingsModel()
    /// What the Usage page in the Milo window shows.
    public let usage = UsageModel()
    /// Looking at the screen and the worker's actions on it; nil without those ports.
    public let screen: ScreenController?
    /// Calls and meeting recordings; nil without a recorder.
    public let meetings: MeetingController?
    /// Learns from the user's fixes to pasted dictation; nil without a field reader.
    public let pasteWatcher: PasteWatcher?
    public private(set) var muted = false
    /// The dictation style the brain uses, from its `settings`; nil while no brain is connected.
    public var dictationStyle: DictationStyle? {
        guard model.connected, let value = settingsModel.value("dictation", "stream")?.string else { return nil }
        return DictationStyle(rawValue: value)
    }
    /// `[dictation] learn` as the brain last reported it. Off while no brain is connected: nothing is read then.
    public var learnsFromFixes: Bool {
        model.connected && settingsModel.value("dictation", "learn")?.bool == true
    }
    public var bindings: HotkeyBindings { pushToTalk.bindings }
    /// Called when `ui_config` changes the bindings.
    public var onBindingsChange: ((HotkeyBindings) -> Void)?

    private let brain: BrainClient
    private let launcher: BrainLauncher
    private let inserter: TextInserter
    private let keys: KeyEventSource
    private let context: ContextProvider
    private let accessibility: AccessibilityPermission
    private let connections: AppConnections?
    private let scheduler: Scheduler
    private let settings: Settings
    private var pushToTalk: PushToTalk
    private var pushToTalkTimer: ScheduledTask?
    private var contextTimer: ScheduledTask?

    public init(model: MiloModel, brain: BrainClient, launcher: BrainLauncher, inserter: TextInserter,
                keys: KeyEventSource, context: ContextProvider, accessibility: AccessibilityPermission,
                scheduler: Scheduler, connections: AppConnections? = nil, settings: Settings = Settings(),
                screen: ScreenController? = nil, meetings: MeetingController? = nil,
                pasteWatcher: PasteWatcher? = nil) {
        self.model = model
        self.screen = screen
        self.meetings = meetings
        self.pasteWatcher = pasteWatcher
        self.brain = brain
        self.launcher = launcher
        self.inserter = inserter
        self.keys = keys
        self.context = context
        self.accessibility = accessibility
        self.connections = connections
        self.scheduler = scheduler
        self.settings = settings
        self.pushToTalk = PushToTalk(bindings: settings.bindings, minHold: settings.minHold,
                                     showAfter: settings.showAfter, doubleTap: settings.doubleTap,
                                     maxLocked: settings.handsFreeMax)
    }

    public func start() {
        model.onAnswer = { [weak self] question, yes in self?.brain.send(.confirmAnswer(id: question.id, yes: yes)) }
        model.onStopHelper = { [weak self] id in self?.brain.send(.stopHelper(id: id)) }
        model.onRoutine = { [weak self] id, action in self?.brain.send(.routine(id: id, action: action)) }
        model.onDraftAnswer = { [weak self] id, save in self?.brain.send(.routineDraftAnswer(id: id, save: save)) }
        settingsModel.send = { [weak self] in self?.brain.send($0) }
        usage.send = { [weak self] in self?.brain.send($0) }
        pasteWatcher?.onFixes = { [weak self] in self?.brain.send(.dictationFixed($0)) }
        brain.onEvent = { [weak self] in self?.received($0) }
        brain.onConnectionChange = { [weak self] in self?.connectionChanged($0) }
        // Development brains are started by hand; only launch one if nothing answers.
        if !brain.probe() { launcher.start() }
        brain.start()

        keys.onEvent = { [weak self] in self?.handleKey($0) }
        keys.start()
        screen?.start()
        meetings?.start()

        if !accessibility.isTrusted(prompt: settings.promptForAccessibility) {
            model.show(Self.needAccessibility(bindings.dictate.displayName), action: .permissions)
        }

        context.onAppSwitch = { [weak self] in self?.sendContext() }
        contextTimer = scheduler.every(settings.contextInterval) { [weak self] in self?.sendContext() }
    }

    /// Stops a brain this app launched.
    public func stop() {
        contextTimer?.cancel()
        contextTimer = nil
        launcher.stop()
    }

    public func toggleMute() {
        muted.toggle()
        brain.send(.mute(muted))
    }

    /// The menu's "Pause messages from your phone". Only the Mac can switch it back on.
    public func setRemotePaused(_ on: Bool) {
        brain.send(.remotePause(on))
    }

    /// The menu's "Disconnect phone".
    public func forgetPhone() {
        brain.send(.remoteForget)
    }

    public func restartBrain() {
        launcher.restart()
    }

    /// The menu's "Dictation style": the same `set_setting` the Settings window sends. The brain answers with
    /// `settings`, which puts the old style back if it couldn't save the new one.
    public func setDictationStyle(_ style: DictationStyle) {
        settingsModel.change("dictation", "stream", to: .string(style.rawValue))
    }

    static let noConnections = "This version of Milo can't reach your calendar or reminders."

    static func needAccessibility(_ key: String) -> String {
        "I need Accessibility to hear the \(key) key and paste for you."
    }

    static let pasteBlocked = "I couldn't paste: macOS switched off my Accessibility. Your words are on the clipboard, press ⌘V."

    private func received(_ event: BrainEvent) {
        if let screen, screen.apply(event) { return }
        if let meetings, meetings.apply(event) { return }
        switch event {
        case let .dictation(text):
            // Without Accessibility macOS drops Milo's Cmd-V without an error. An ad-hoc signed
            // rebuild loses the permission while System Settings still shows it switched on.
            if accessibility.isTrusted(prompt: false) {
                inserter.insert(text)
                model.pasted(text)
                if learnsFromFixes { pasteWatcher?.pasted(text) } else { pasteWatcher?.stop() }
            } else {
                inserter.copy(text)
                NSLog("Milo: not trusted for Accessibility, dictation left on the clipboard")
                model.show(Self.pasteBlocked, action: .permissions)
            }
        case let .uiConfig(dictateKey, talkKey, handsFreeMax, whatsThisKey, character, meetingKey):
            if let handsFreeMax, handsFreeMax > 0 { pushToTalk.maxLocked = handsFreeMax }
            if let whatsThisKey { screen?.setShortcut(whatsThisKey) }
            if let meetingKey { meetings?.setShortcut(meetingKey) }
            if let character, character != model.character { model.character = character }
            let next = bindings.applying(dictateKey: dictateKey, talkKey: talkKey)
            guard next != bindings else { return }
            pushToTalkChanged(pushToTalk.rebind(next), at: nil)
            onBindingsChange?(next)
        case .history, .entry, .replyDelta, .activity, .conversations, .conversation, .searchResults, .reminders:
            transcript.apply(event)
        case .facts:
            knowledge.apply(event)
        case let .settings(report):
            settingsModel.apply(report)
        case let .usage(report):
            usage.apply(report)
        case let .appRequest(id, op, args):
            guard let connections else {
                brain.send(.appResponse(id: id, outcome: .failure(Self.noConnections)))
                return
            }
            connections.handle(op: op, args: args) { [weak self] outcome in
                self?.brain.send(.appResponse(id: id, outcome: outcome))
            }
        default:
            model.apply(event)
        }
    }

    /// A turn typed in the Milo window. `speak` false: the answer is text only. `conversation`: typed into
    /// that earlier conversation, which picks it up again.
    public func send(text: String, speak: Bool, conversation: String = "") {
        let text = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        brain.send(.text(text, speak: speak, conversation: conversation))
    }

    /// The Milo window opened. Reads the brain's in-memory tail and its list; no model call.
    public func requestHistory() {
        brain.send(.getHistory)
    }

    /// What the Milo window asks of the brain besides typing: open, search, rename, start fresh.
    public lazy var windowActions = WindowActions(
        open: { [weak self] in self?.brain.send(.openConversation(id: $0)) },
        search: { [weak self] in self?.brain.send(.searchConversations(query: $0)) },
        rename: { [weak self] id, title in self?.brain.send(.renameConversation(id: id, title: title)) },
        newConversation: { [weak self] in self?.brain.send(.newConversation) },
        older: { [weak self] in self?.brain.send(.getConversations(before: $0)) },
        send: { [weak self] text, speak, conversation in
            self?.send(text: text, speak: speak, conversation: conversation)
        })

    /// The "What Milo knows" window opened. Reads the brain's fact list; no model call.
    public func requestFacts() {
        brain.send(.getFacts)
    }

    public func forgetFact(id: String) {
        brain.send(.forgetFact(id: id))
    }

    public func editFact(id: String, text: String) {
        let text = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        brain.send(.editFact(id: id, text: text))
    }

    private func connectionChanged(_ up: Bool) {
        model.connected = up
        meetings?.connectionChanged(up)
        guard up else {
            // A brain that died mid-answer never sends idle; don't leave Milo speaking or listening.
            // A new brain sends its own state on connect. Its helpers died with it.
            pushToTalkChanged(pushToTalk.reset(), at: nil)
            model.apply(.state(.idle))
            model.apply(.helpers([]))
            // Its questions died with it too: Yes and No would go nowhere.
            if let question = model.question { model.apply(.confirmDone(id: question.id, answer: "timeout")) }
            return
        }
        // The brain's greeting carries its settings, so a restarted brain's changes show without asking.
        sendContext()
        brain.send(.mute(muted))
    }

    private func handleKey(_ event: KeyEvent) {
        pushToTalkChanged(pushToTalk.handle(event), at: event.timestamp)
    }

    /// Sends the outputs, shows the hands-free lock and re-arms the timer for the next deadline.
    /// `now` is on the key events' clock; nil when no key event caused the change (then no deadline is left).
    private func pushToTalkChanged(_ outputs: [PushToTalk.Output], at now: TimeInterval?) {
        outputs.forEach(send)
        if model.handsFree != pushToTalk.locked { model.handsFree = pushToTalk.locked }
        pushToTalkTimer?.cancel()
        pushToTalkTimer = nil
        guard let deadline = pushToTalk.deadline, let now else { return }
        pushToTalkTimer = scheduler.after(max(0, deadline - now)) { [weak self] in
            guard let self else { return }
            pushToTalkChanged(pushToTalk.expire(at: deadline), at: deadline)
        }
    }

    /// Shows the output on Milo first, in the same frame as the key, then tells the brain.
    private func send(_ output: PushToTalk.Output) {
        switch output {
        case let .start(mode):
            model.press(mode)
            brain.send(.listenStart(mode, tentative: true))
        case let .confirm(mode), let .lock(mode):
            model.hold(mode)
            brain.send(.listenConfirm)
        case let .stop(mode):
            model.release(mode)
            brain.send(.listenStop)
        case .cancel:
            model.cancelPress()
            brain.send(.listenCancel)
        }
    }

    private func sendContext() {
        let now = context.current()
        // Only on a change: every assignment redraws each view that watches the model, hidden windows too.
        let drowsy = now.idleSeconds > settings.drowsyAfter
        if model.drowsy != drowsy { model.drowsy = drowsy }
        brain.send(.context(app: now.app, idleSeconds: now.idleSeconds))
    }
}
