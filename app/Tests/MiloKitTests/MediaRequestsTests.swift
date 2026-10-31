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

    final class Keys: BrightnessKeys {
        var pressed: [Bool] = []
        var takes = true

        func press(up: Bool) -> Bool {
            pressed.append(up)
            return takes
        }
    }

    /// Runs everything at once: "later" is now, so a test sees the timeout too.
    private func requests(_ player: Player, brightness: BrightnessKeys? = nil,
                          next: AppConnections? = nil) -> MediaRequests {
        MediaRequests(player: player, brightness: brightness, next: next, main: { $0() }, after: { _, work in work() })
    }

    private func call(_ r: MediaRequests, _ op: String, _ args: JSONValue = .object([:])) -> [AppOutcome] {
        var outcomes: [AppOutcome] = []
        r.handle(op: op, args: args) { outcomes.append($0) }
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
        let next = FakeConnections()
        _ = call(requests(Player(), next: next), "calendar.events")
        #expect(next.handled.map(\.op) == ["calendar.events"])
    }

    /// ADR 36: "make the screen brighter" presses the brightness key, a few times, like the keyboard does.
    @Test func brightnessPressesTheKeyAsOftenAsAsked() {
        let keys = Keys()
        let r = requests(Player(), brightness: keys)
        #expect(call(r, "media.brightness_up", .object(["steps": .number(3)]))
                == [.success(.object(["steps": .number(3)]))])
        #expect(call(r, "media.brightness_down") == [.success(.object(["steps": .number(1)]))])
        #expect(keys.pressed == [true, true, true, false])
        #expect(call(r, "media.brightness_down", .object(["steps": .number(99)]))
                == [.success(.object(["steps": .number(16)]))], "never more than the whole range")
    }

    @Test func brightnessWithoutKeysIsAPlainFailure() {
        let keys = Keys()
        keys.takes = false
        #expect(call(requests(Player(), brightness: keys), "media.brightness_up")
                == [.failure("I couldn't reach the brightness keys.")])
        #expect(call(requests(Player()), "media.brightness_up")
                == [.failure("Milo's app can't change the brightness here.")])
    }
}
