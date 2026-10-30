import Foundation

/// The ports the screen features need. main.swift builds the real ones; tests hand in fakes.
public struct ScreenPorts {
    public var reader: ScreenReader
    public var hands: HandsExecutor
    public var input: UserInputSource
    public var hotkey: HotkeySource
    public var cursor: CursorDisplay
    public var windows: WindowWatcher

    public init(reader: ScreenReader, hands: HandsExecutor, input: UserInputSource, hotkey: HotkeySource,
                cursor: CursorDisplay = NoCursor(), windows: WindowWatcher = NoWindowWatcher()) {
        self.reader = reader
        self.hands = hands
        self.input = input
        self.hotkey = hotkey
        self.cursor = cursor
        self.windows = windows
    }
}

/// Looking at the screen, "What's this?" and the worker's actions on screen.
///
/// The worker acts in the background: his own cursor glides to each spot before the action runs, the window he
/// works in gets an outline (`MiloModel.workingWindow`) that follows it, and Pip perches on its corner. The
/// user keeps their mouse and keyboard, and only esc (or the Stop button on the outline) stops him.
///
/// When an action needs the real mouse or keyboard, the brain asks the user to lend them (`hands_borrow`).
/// While they are lent, the frame around the screen shows and any real input stops the worker at once, as
/// before: the app tells the brain (hands_stop), cancels what is running and refuses actions until the brain
/// ends the session. They go back to the user `lendFor` seconds after the last action.
///
/// Input is ignored while a question waits (`confirm` until `confirm_done`), since answering it means using
/// the mouse or the talk key. The question itself is MiloModel's, answered with `confirm_answer`.
public final class ScreenController {
    /// Tools that act on screen and get Milo's cursor.
    static let pointed: Set<String> = ["click", "type", "key", "scroll", "ax_press", "ax_set_value"]
    /// How long the real mouse and keyboard stay lent after the last action.
    public static let lendFor: TimeInterval = 15
    /// The longest an action waits for Milo's cursor to arrive.
    static let glideWait: TimeInterval = 1.2

    private let model: MiloModel
    private let brain: BrainClient
    private let ports: ScreenPorts
    private let now: () -> TimeInterval
    private let toAppKit: (ScreenPoint) -> CGPoint
    private let scheduler: Scheduler
    private var detector = TakeoverDetector(mode: .background)
    private var stoppedLocally = false
    /// Where Milo's cursor is headed (AppKit coordinates) and the actions waiting for it to get there.
    private var aim: CGPoint?
    private var gliding = false
    private var waiting: [() -> Void] = []
    private var glideTimeout: ScheduledTask?
    private var lapse: ScheduledTask?
    private var watchedPid: Int32?

    /// `now` is on the input events' clock. `toAppKit` turns a top-left-origin point into AppKit's.
    public init(model: MiloModel, brain: BrainClient, ports: ScreenPorts,
                now: @escaping () -> TimeInterval = { ProcessInfo.processInfo.systemUptime },
                toAppKit: @escaping (ScreenPoint) -> CGPoint, scheduler: Scheduler = MainQueueScheduler()) {
        self.model = model
        self.brain = brain
        self.ports = ports
        self.now = now
        self.toAppKit = toAppKit
        self.scheduler = scheduler
    }

    public func start() {
        ports.input.onInput = { [weak self] in self?.handle($0) }
        ports.hotkey.onPress = { [weak self] in self?.whatsThis() }
    }

    /// The shortcut from `ui_config`. Unknown text leaves it off.
    public func setShortcut(_ text: String) {
        let combo = KeyCombo(text)
        if !text.isEmpty && combo == nil { NSLog("Milo: ignoring whats_this_key %@", text) }
        if !ports.hotkey.register(combo), let combo {
            NSLog("Milo: macOS refused the What's this? shortcut %@", combo.displayName)
        }
    }

    /// Ask Milo about the selection, or the front window if nothing is selected.
    public func whatsThis() {
        ports.reader.capture(selection: true) { [weak self] capture in
            self?.brain.send(.whatsThis(capture))
        }
    }

    /// The user pressed Stop on the outline of the window Milo works in.
    public func stopPressed() {
        guard model.handsActive else { return }
        stop(.escape)
    }

    /// Handles the screen events; false for anything else. Questions only pause the takeover check and
    /// return false, so the model still shows them.
    public func apply(_ event: BrainEvent) -> Bool {
        switch event {
        case let .lookRequest(id, mode):
            ports.reader.capture(selection: mode == "selection") { [weak self] capture in
                self?.brain.send(.lookResult(id: id, capture))
            }
        case let .handsRequest(id, tool, args):
            perform(id: id, tool: tool, args: args)
        case let .handsSession(on):
            session(on)
        case let .handsBorrow(on):
            if model.handsActive { lend(on) }
        case let .flyTo(point):
            // While a window is known Pip stays perched on it; Milo's cursor shows the spot.
            if point == nil || model.workingWindow == nil { model.flyTarget = point.map(toAppKit) }
        case .confirm:
            detector.disarm()
            return false
        case let .confirmDone(id, _):
            // A click already took the question away; another question still waiting keeps the check off.
            if model.handsActive && (model.question == nil || model.question?.id == id) { detector.arm() }
            return false
        default:
            return false
        }
        return true
    }

    private func perform(id: String, tool: String, args: [String: JSONValue]) {
        if stoppedLocally && tool != "describe" {
            brain.send(.handsResult(id: id, ok: false, result: [:], error: "stopped"))
            return
        }
        let run = { [weak self] in
            guard let self else { return }
            if stoppedLocally && tool != "describe" {
                return brain.send(.handsResult(id: id, ok: false, result: [:], error: "stopped"))
            }
            if model.handsBorrowed { lapse?.cancel() }
            detector.miloActs(at: now())
            ports.hands.perform(tool, args: args) { [weak self] result in
                self?.finished(id: id, tool: tool, args: args, result: result)
            }
        }
        // An action waits for Milo's cursor to reach its spot, so the user sees where it lands first.
        if Self.pointed.contains(tool) && gliding { waiting.append(run) } else { run() }
    }

    private func finished(id: String, tool: String, args: [String: JSONValue],
                          result: Result<[String: JSONValue], HandsFailure>) {
        detector.miloActs(at: now())
        if model.handsBorrowed { lapse?.cancel(); lapse = scheduler.after(Self.lendFor) { [weak self] in self?.lend(false) } }
        switch result {
        case let .success(value):
            if tool == "describe" { aim(at: HandsTarget(describe: value), tool: args["tool"]?.string ?? "") }
            if model.handsActive, let aim { cue(tool, at: aim) }
            brain.send(.handsResult(id: id, ok: true, result: value))
        case let .failure(failure):
            let result: [String: JSONValue] = failure.borrow.map { ["borrow": .string($0)] } ?? [:]
            brain.send(.handsResult(id: id, ok: false, result: result, error: failure.message))
        }
    }

    /// The window and spot `describe` found: outline the window, perch Pip on it, glide the cursor there.
    private func aim(at target: HandsTarget, tool: String) {
        guard Self.pointed.contains(tool) else { return }
        if let window = target.window {
            show(window: window)
            if let pid = target.pid, pid != watchedPid || model.workingWindow != appKit(window) {
                watchedPid = pid
                ports.windows.watch(pid: pid, frame: window) { [weak self] frame in
                    guard let self, model.handsActive else { return }
                    if let frame { show(window: frame) } else { model.workingWindow = nil; watchedPid = nil }
                }
            }
        }
        guard let point = target.point else { return }
        let spot = toAppKit(ScreenPoint(x: point.x, y: point.y))
        aim = spot
        gliding = true
        glideTimeout?.cancel()
        glideTimeout = scheduler.after(Self.glideWait) { [weak self] in self?.arrived() }
        ports.cursor.glide(to: spot) { [weak self] in self?.arrived() }
    }

    private func arrived() {
        glideTimeout?.cancel()
        glideTimeout = nil
        gliding = false
        let ready = waiting
        waiting.removeAll()
        ready.forEach { $0() }
    }

    private func cue(_ tool: String, at point: CGPoint) {
        switch tool {
        case "click", "ax_press": ports.cursor.click(at: point)
        case "type", "ax_set_value", "key": ports.cursor.typing(at: point)
        default: break
        }
    }

    private func show(window frame: CGRect) {
        let rect = appKit(frame)
        if model.workingWindow != rect { model.workingWindow = rect }
        if model.flyTarget != nil { model.flyTarget = nil }
    }

    /// A top-left-origin rectangle in AppKit's space: its bottom-left corner moves, the size stays.
    private func appKit(_ frame: CGRect) -> CGRect {
        let origin = toAppKit(ScreenPoint(x: frame.minX, y: frame.maxY))
        return CGRect(origin: origin, size: frame.size)
    }

    private func session(_ on: Bool) {
        stoppedLocally = false
        model.handsActive = on
        if on {
            detector.mode = model.handsBorrowed ? .borrowed : .background
            if model.question == nil { detector.arm() }
            ports.input.start()
        } else {
            detector.disarm()
            ports.input.stop()
            clearScreen()
        }
    }

    /// The real mouse and keyboard are lent (`on`) or given back.
    private func lend(_ on: Bool) {
        lapse?.cancel()
        lapse = on ? scheduler.after(Self.lendFor) { [weak self] in self?.lend(false) } : nil
        ports.hands.borrowed = on
        model.handsBorrowed = on
        detector.mode = on ? .borrowed : .background
    }

    private func handle(_ input: UserInput) {
        guard let reason = detector.handle(input) else { return }
        stop(reason)
    }

    private func stop(_ reason: TakeoverDetector.Reason) {
        detector.disarm()
        stoppedLocally = true
        ports.hands.cancel()
        ports.input.stop()
        model.handsActive = false
        clearScreen()
        brain.send(.handsStop(reason: reason.rawValue))
    }

    private func clearScreen() {
        lend(false)
        lapse = nil
        model.flyTarget = nil
        model.workingWindow = nil
        watchedPid = nil
        ports.windows.stop()
        ports.cursor.rest()
        aim = nil
        arrived()
    }
}
