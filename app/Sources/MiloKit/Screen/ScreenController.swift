import Foundation

/// The ports the screen features need. main.swift builds the real ones; tests hand in fakes.
public struct ScreenPorts {
    public var reader: ScreenReader
    public var hands: HandsExecutor
    public var input: UserInputSource
    public var hotkey: HotkeySource

    public init(reader: ScreenReader, hands: HandsExecutor, input: UserInputSource, hotkey: HotkeySource) {
        self.reader = reader
        self.hands = hands
        self.input = input
        self.hotkey = hotkey
    }
}

/// Looking at the screen, "What's this?" and the worker's actions on screen.
///
/// While the worker acts (hands_session on), real mouse or keyboard input stops it at once: the app tells
/// the brain (hands_stop), cancels what is running and refuses actions until the brain ends the session.
/// Input is ignored while a question waits (`confirm` until `confirm_done`), since answering it means using
/// the mouse or the talk key. The question itself is MiloModel's, answered with `confirm_answer`.
public final class ScreenController {
    private let model: MiloModel
    private let brain: BrainClient
    private let ports: ScreenPorts
    private let now: () -> TimeInterval
    private let toAppKit: (ScreenPoint) -> CGPoint
    private var detector = TakeoverDetector()
    private var stoppedLocally = false

    /// `now` is on the input events' clock. `toAppKit` turns a top-left-origin point into AppKit's.
    public init(model: MiloModel, brain: BrainClient, ports: ScreenPorts,
                now: @escaping () -> TimeInterval = { ProcessInfo.processInfo.systemUptime },
                toAppKit: @escaping (ScreenPoint) -> CGPoint) {
        self.model = model
        self.brain = brain
        self.ports = ports
        self.now = now
        self.toAppKit = toAppKit
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
        case let .flyTo(point):
            model.flyTarget = point.map(toAppKit)
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
        detector.miloActs(at: now())
        ports.hands.perform(tool, args: args) { [weak self] result in
            guard let self else { return }
            detector.miloActs(at: now())
            switch result {
            case let .success(value): brain.send(.handsResult(id: id, ok: true, result: value))
            case let .failure(failure): brain.send(.handsResult(id: id, ok: false, result: [:], error: failure.message))
            }
        }
    }

    private func session(_ on: Bool) {
        stoppedLocally = false
        model.handsActive = on
        if on {
            if model.question == nil { detector.arm() }
            ports.input.start()
        } else {
            detector.disarm()
            ports.input.stop()
            model.flyTarget = nil
        }
    }

    private func handle(_ input: UserInput) {
        guard let reason = detector.handle(input) else { return }
        detector.disarm()
        stoppedLocally = true
        ports.hands.cancel()
        ports.input.stop()
        model.handsActive = false
        model.flyTarget = nil
        brain.send(.handsStop(reason: reason.rawValue))
    }
}
