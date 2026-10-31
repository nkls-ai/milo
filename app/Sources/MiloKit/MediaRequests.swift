import Foundation

/// The brain's `media.*` ops (ADR 0029), in front of the other app connections.
///
/// - `media.state` {}: {state: "playing" | "paused" | ""}. "" when the system doesn't say within `stateTimeout`.
/// - `media.play`, `media.pause`, `media.next`, `media.previous` {}: {state} as it will be after the command.
/// - `media.brightness_up`, `media.brightness_down` {steps}: presses the brightness key 1 to 16 times (ADR 36).
///   Answers {steps} pressed.
public final class MediaRequests: AppConnections {
    private let player: MediaPlayer
    private let brightness: BrightnessKeys?
    private let next: AppConnections?
    private let stateTimeout: TimeInterval
    private let main: (@escaping () -> Void) -> Void
    private let after: (TimeInterval, @escaping () -> Void) -> Void

    public init(player: MediaPlayer, brightness: BrightnessKeys? = nil, next: AppConnections? = nil,
                stateTimeout: TimeInterval = 0.5,
                main: @escaping (@escaping () -> Void) -> Void = { DispatchQueue.main.async(execute: $0) },
                after: @escaping (TimeInterval, @escaping () -> Void) -> Void = { delay, work in
                    DispatchQueue.main.asyncAfter(deadline: .now() + delay, execute: work)
                }) {
        self.player = player
        self.brightness = brightness
        self.next = next
        self.stateTimeout = stateTimeout
        self.main = main
        self.after = after
    }

    public func handle(op: String, args: JSONValue, reply: @escaping (AppOutcome) -> Void) {
        guard op.hasPrefix("media.") else {
            guard let next else { return reply(.failure("Milo's app doesn't know how to do \(op).")) }
            return next.handle(op: op, args: args, reply: reply)
        }
        let name = String(op.dropFirst("media.".count))
        if name == "state" {
            // The system may never answer (newer macOS keeps now-playing to itself): the brain mustn't wait on it.
            var answered = false
            let once: (String) -> Void = { [main] state in
                main {
                    guard !answered else { return }
                    answered = true
                    reply(.success(.object(["state": .string(state)])))
                }
            }
            player.isPlaying { once($0 ? "playing" : "paused") }
            after(stateTimeout) { once("") }
            return
        }
        if name == "brightness_up" || name == "brightness_down" {
            guard let brightness else { return reply(.failure("Milo's app can't change the brightness here.")) }
            let steps = max(1, min(16, Int(args["steps"]?.number ?? 1)))
            for _ in 0..<steps {
                guard brightness.press(up: name == "brightness_up") else {
                    return reply(.failure("I couldn't reach the brightness keys."))
                }
            }
            return reply(.success(.object(["steps": .number(Double(steps))])))
        }
        guard let command = MediaCommand(rawValue: name) else {
            return reply(.failure("The music player can't \(name)."))
        }
        guard player.send(command) else { return reply(.failure("I couldn't reach the music player.")) }
        reply(.success(.object(["state": .string(command == .pause ? "paused" : "playing")])))
    }
}
