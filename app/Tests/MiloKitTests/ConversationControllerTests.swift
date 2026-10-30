import Foundation
import Testing
@testable import MiloKit

/// The controller's part in the Milo window: transcript events go to the transcript, typing goes to the brain.
@Suite struct ConversationControllerTests {
    let brain = FakeBrainClient()
    let controller: MiloController

    init() {
        let scheduler = ManualScheduler()
        controller = MiloController(model: MiloModel(scheduler: scheduler), brain: brain,
                                    launcher: FakeBrainLauncher(), inserter: FakeTextInserter(),
                                    keys: FakeKeySource(), context: FakeContextProvider(),
                                    accessibility: FakeAccessibility(), scheduler: scheduler)
        controller.start()
    }

    @Test func transcriptEventsReachTheTranscriptNotTheBubble() {
        let entry = TranscriptEntry(id: "m", date: Date(), kind: .milo, text: "", done: false)
        brain.emit(.history([]))
        brain.emit(.entry(entry))
        brain.emit(.replyDelta(id: "m", text: "Hi there."))
        #expect(controller.transcript.entries.map(\.text) == ["Hi there."])
        #expect(controller.model.bubble == nil)
    }

    @Test func typingSendsTextWithTheSpeakSetting() {
        controller.send(text: "  hello  ", speak: false)
        controller.send(text: "   ", speak: true)
        controller.send(text: "again", speak: true)
        #expect(brain.sent == [.text("hello", speak: false), .text("again")])
    }

    @Test func openingTheWindowAsksForHistoryOnly() {
        controller.requestHistory()
        #expect(brain.sent == [.getHistory])
    }
}
