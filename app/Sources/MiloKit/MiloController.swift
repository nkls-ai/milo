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
        /// The second tap must start within this long of the first.
        public var doubleTap: TimeInterval
        /// A hands-free recording stops by itself after this long, until `ui_config` says otherwise.
        public var handsFreeMax: TimeInterval

        public init(contextInterval: TimeInterval = 15, drowsyAfter: TimeInterval = 600,
                    bindings: HotkeyBindings = .default, minHold: TimeInterval = 0.25,
                    doubleTap: TimeInterval = 0.35, handsFreeMax: TimeInterval = 300) {
            self.contextInterval = contextInterval
            self.drowsyAfter = drowsyAfter
            self.bindings = bindings
            self.minHold = minHold
            self.doubleTap = doubleTap
            self.handsFreeMax = handsFreeMax
        }
    }

    public let model: MiloModel
    /// The conversation the Milo window shows.
    public let transcript = TranscriptModel()
    /// Looking at the screen and the worker's actions on it; nil without those ports.
    public let screen: ScreenController?
    public private(set) var muted = false
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
                screen: ScreenController? = nil) {
        self.model = model
        self.screen = screen
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
                                     doubleTap: settings.doubleTap, maxLocked: settings.handsFreeMax)
    }

    public func start() {
        model.onAnswer = { [weak self] question, yes in self?.brain.send(.confirmAnswer(id: question.id, yes: yes)) }
        model.onStopHelper = { [weak self] id in self?.brain.send(.stopHelper(id: id)) }
        model.onRoutine = { [weak self] id, action in self?.brain.send(.routine(id: id, action: action)) }
        model.onDraftAnswer = { [weak self] id, save in self?.brain.send(.routineDraftAnswer(id: id, save: save)) }
        brain.onEvent = { [weak self] in self?.received($0) }
        brain.onConnectionChange = { [weak self] in self?.connectionChanged($0) }
        // Development brains are started by hand; only launch one if nothing answers.
        if !brain.probe() { launcher.start() }
        brain.start()

        keys.onEvent = { [weak self] in self?.handleKey($0) }
        keys.start()
        screen?.start()

        if !accessibility.isTrusted(prompt: true) {
            model.show("Grant me Accessibility in System Settings so I can hear the \(bindings.dictate.displayName) key and paste for you.")
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

    public func restartBrain() {
        launcher.restart()
    }

    static let noConnections = "This version of Milo can't reach your calendar or reminders."

    static let pasteBlocked = "I can't paste: macOS turned off my Accessibility permission. Your text is on the clipboard, press ⌘V. To fix it, remove Milo in System Settings › Privacy & Security › Accessibility and add him again."

    private func received(_ event: BrainEvent) {
        if let screen, screen.apply(event) { return }
        switch event {
        case let .dictation(text):
            // Without Accessibility macOS drops Milo's Cmd-V without an error. An ad-hoc signed
            // rebuild loses the permission while System Settings still shows it switched on.
            if accessibility.isTrusted(prompt: false) {
                inserter.insert(text)
            } else {
                inserter.copy(text)
                NSLog("Milo: not trusted for Accessibility, dictation left on the clipboard")
                model.show(Self.pasteBlocked)
            }
        case let .uiConfig(dictateKey, talkKey, handsFreeMax, whatsThisKey, character):
            if let handsFreeMax, handsFreeMax > 0 { pushToTalk.maxLocked = handsFreeMax }
            if let whatsThisKey { screen?.setShortcut(whatsThisKey) }
            if let character, character != model.character { model.character = character }
            let next = bindings.applying(dictateKey: dictateKey, talkKey: talkKey)
            guard next != bindings else { return }
            pushToTalkChanged(pushToTalk.rebind(next), at: nil)
            onBindingsChange?(next)
        case .history, .entry, .replyDelta, .activity:
            transcript.apply(event)
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

    /// A turn typed in the Milo window. `speak` false: the answer is text only.
    public func send(text: String, speak: Bool) {
        let text = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        brain.send(.text(text, speak: speak))
    }

    /// The Milo window opened. Reads the brain's in-memory tail; no model call.
    public func requestHistory() {
        brain.send(.getHistory)
    }

    private func connectionChanged(_ up: Bool) {
        model.connected = up
        guard up else {
            // A brain that died mid-answer never sends idle; don't leave Milo speaking or listening.
            // A new brain sends its own state on connect. Its helpers died with it.
            pushToTalkChanged(pushToTalk.reset(), at: nil)
            model.apply(.state(.idle))
            model.apply(.helpers([]))
            return
        }
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

    private func send(_ output: PushToTalk.Output) {
        switch output {
        case let .start(mode): brain.send(.listenStart(mode, tentative: true))
        case .confirm, .lock: brain.send(.listenConfirm)
        case .stop: brain.send(.listenStop)
        case .cancel: brain.send(.listenCancel)
        }
    }

    private func sendContext() {
        let now = context.current()
        model.drowsy = now.idleSeconds > settings.drowsyAfter
        brain.send(.context(app: now.app, idleSeconds: now.idleSeconds))
    }
}
