import Foundation
import Testing
@testable import MiloKit

/// The brain's `media.*` ops (ADR 29): play, pause and skip whatever plays, without a script and its question.
@Suite struct MediaRequestsTests {
    final class Player: MediaPlayer {
        var sent: [MediaCommand] = []
        var playing: Bool?
        var takes = true

        func isPlaying(_ done: @escaping (Bool) -> Void) {
            if let playing { done(playing) }
        }

        func send(_ command: MediaCommand) -> Bool {
            sent.append(command)
            return takes
        }
    }

    final class Next: AppConnections {
        var ops: [String] = []
        func handle(op: String, args: JSONValue, reply: @escaping (AppOutcome) -> Void) {
            ops.append(op)
            reply(.success(.null))
        }
    }

    /// Runs everything at once: "later" is now, so a test sees the timeout too.
    private func requests(_ player: Player, next: AppConnections? = nil) -> MediaRequests {
        MediaRequests(player: player, next: next, main: { $0() }, after: { _, work in work() })
    }

    private func call(_ r: MediaRequests, _ op: String) -> [AppOutcome] {
        var outcomes: [AppOutcome] = []
        r.handle(op: op, args: .object([:])) { outcomes.append($0) }
        return outcomes
    }

    @Test func commandsGoToThePlayerAndSayTheStateAfter() {
        let player = Player()
        let r = requests(player)
        #expect(call(r, "media.pause") == [.success(.object(["state": .string("paused")]))])
        #expect(call(r, "media.next") == [.success(.object(["state": .string("playing")]))])
        #expect(player.sent == [.pause, .next])
    }

    @Test func aPlayerThatTakesNothingIsAPlainFailure() {
        let player = Player()
        player.takes = false
        #expect(call(requests(player), "media.play") == [.failure("I couldn't reach the music player.")])
        #expect(call(requests(player), "media.louder") == [.failure("The music player can't louder.")])
    }

    @Test func theStateAnswersOnceAndASilentSystemDoesntKeepTheBrainWaiting() {
        let player = Player()
        player.playing = true
        #expect(call(requests(player), "media.state") == [.success(.object(["state": .string("playing")]))])
        player.playing = nil
        #expect(call(requests(player), "media.state") == [.success(.object(["state": .string("")]))])
    }

    @Test func otherOpsGoOnToCalendarAndReminders() {
        let next = Next()
        _ = call(requests(Player(), next: next), "calendar.events")
        #expect(next.ops == ["calendar.events"])
    }
}
