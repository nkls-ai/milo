import AppKit
import Foundation
import SwiftUI
import Testing
@testable import MiloKit

@Suite struct KnowledgeTests {
    static let facts = [
        MemoryFact(id: "f1", text: "Anna is the user's sister.", topic: "people", since: "2026-10-01T09:00:00"),
        MemoryFact(id: "f2", text: "The user's name is Niklas.", topic: "basics", since: "2026-10-01T09:00:00",
                   pinned: true),
        MemoryFact(id: "f3", text: "Likes tea in the afternoon.", topic: "preferences", since: "2026-10-02T09:00:00"),
        MemoryFact(id: "f4", text: "Has a cat called Pixel.", topic: "pets", since: "2026-10-03T09:00:00"),
        MemoryFact(id: "f5", text: "Lena is the user's partner.", topic: "people", since: "2026-10-04T09:00:00"),
    ]

    @Test func factsAreGroupedByTopicInProfileOrder() {
        let model = KnowledgeModel()
        #expect(!model.loaded)
        model.apply(.facts(Self.facts))
        #expect(model.loaded)
        #expect(model.groups.map(\.title) == ["Basics", "People", "Preferences", "Pets"])
        #expect(model.groups[1].facts.map(\.id) == ["f1", "f5"])
        model.apply(.bubble("hi"))
        #expect(model.facts.count == 5)
    }

    @Test func aFactWithoutTopicOrPinDecodes() throws {
        let fact = try JSONDecoder().decode(MemoryFact.self, from: Data(#"{"id":"x","text":"Hi"}"#.utf8))
        #expect(fact == MemoryFact(id: "x", text: "Hi", topic: "learned", since: ""))
    }
}

/// The controller's part in the "What Milo knows" window.
@Suite struct KnowledgeControllerTests {
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

    @Test func factsReachTheWindowNotTheBubble() {
        brain.emit(.facts(KnowledgeTests.facts))
        #expect(controller.knowledge.facts == KnowledgeTests.facts)
        #expect(controller.model.bubble == nil)
    }

    @Test func openingAsksAndTheButtonsSendTheirCommands() {
        controller.requestFacts()
        controller.forgetFact(id: "f1")
        controller.editFact(id: "f3", text: "  Likes green tea.  ")
        controller.editFact(id: "f3", text: "   ")
        #expect(brain.sent == [.getFacts, .forgetFact(id: "f1"), .editFact(id: "f3", text: "Likes green tea.")])
    }
}

/// Renders the "What Milo knows" window offscreen for a visual check:
/// `MILO_RENDER_DIR=/tmp/milo-render swift test --filter KnowledgeRender`.
@Suite(.enabled(if: ProcessInfo.processInfo.environment["MILO_RENDER_DIR"] != nil))
@MainActor
struct KnowledgeRenderTests {
    @Test func renderTheWindow() throws {
        _ = NSApplication.shared
        let dir = URL(fileURLWithPath: ProcessInfo.processInfo.environment["MILO_RENDER_DIR"] ?? "/tmp")
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let cases: [(String, KnowledgeModel)] = [
            ("knowledge", KnowledgeModel(facts: KnowledgeTests.facts, loaded: true)),
            ("knowledge-empty", KnowledgeModel(facts: [], loaded: true)),
            ("knowledge-asking", KnowledgeModel()),
        ]
        // The window takes Milo's colours, light and dark.
        for (name, model) in cases {
            for dark in [false, true] {
                let size = CGSize(width: 440, height: 520)
                let skin = MiloModel(scheduler: ManualScheduler())
                let host = NSHostingView(rootView: KnowledgeView(knowledge: model, forget: { _ in }, edit: { _, _ in })
                    .frame(width: size.width, height: size.height)
                    .themed(by: skin))
                host.frame = NSRect(origin: .zero, size: size)
                let window = NSWindow(contentRect: host.frame, styleMask: [.titled], backing: .buffered, defer: false)
                window.appearance = NSAppearance(named: dark ? .darkAqua : .aqua)
                window.contentView = host
                host.layoutSubtreeIfNeeded()
                RunLoop.main.run(until: Date().addingTimeInterval(0.3))
                let rep = try #require(host.bitmapImageRepForCachingDisplay(in: host.bounds))
                host.cacheDisplay(in: host.bounds, to: rep)
                let png = try #require(rep.representation(using: .png, properties: [:]))
                try png.write(to: dir.appendingPathComponent("\(name)-\(dark ? "dark" : "light").png"))
            }
        }
    }
}
