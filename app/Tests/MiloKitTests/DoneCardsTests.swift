import AppKit
import Foundation
import Testing
@testable import MiloKit

/// The cards that show what Milo just did (`action_done`), and the caption under the working outline.
@Suite @MainActor struct DoneCardsTests {
    static let dentist = ActionDone(kind: .event, title: "Dentist", detail: "Dr. Lee",
                                    when: RoutineInfo.parseTime("2026-11-05T15:00"), app: "Calendar", undo: "t1")
    static let milk = ActionDone(kind: .todo, title: "Buy milk", app: "Reminders")

    private func connected() -> (MiloModel, FakeBrainClient, MiloController, ManualScheduler) {
        let brain = FakeBrainClient()
        let scheduler = ManualScheduler()
        let model = MiloModel(scheduler: scheduler)
        let controller = MiloController(model: model, brain: brain, launcher: FakeBrainLauncher(),
                                        inserter: FakeTextInserter(), keys: FakeKeySource(),
                                        context: FakeContextProvider(), accessibility: FakeAccessibility(),
                                        scheduler: ManualScheduler())
        controller.start()
        brain.connect()
        return (model, brain, controller, scheduler)
    }

    // MARK: The wire

    @Test func aTimeWithAZoneOrWithoutOneDecodes() throws {
        func decode(_ json: String) throws -> ActionDone {
            guard case let .actionDone(action) = try JSONDecoder().decode(BrainEvent.self, from: Data(json.utf8)) else {
                throw CancellationError()
            }
            return action
        }
        let zoned = try decode(#"{"type":"action_done","kind":"timer","title":"Pasta","when":"2026-11-05T14:00:00Z"}"#)
        #expect(zoned.when == Date(timeIntervalSince1970: 1_793_887_200))
        #expect(zoned.kind == .timer && zoned.detail.isEmpty && zoned.undo.isEmpty)
        let local = try decode(#"{"type":"action_done","kind":"event","title":"Dentist","when":"2026-11-05T15:00"}"#)
        #expect(local.when == RoutineInfo.parseTime("2026-11-05T15:00"))
        let newer = try decode(#"{"type":"action_done","kind":"booked_table","title":"Luigi's","when":""}"#)
        #expect(newer.kind == .other && newer.when == nil, "a kind a newer brain invents still shows a card")
        #expect(newer.lang.isEmpty, "an older brain sends no language")
        let german = try decode(#"{"type":"action_done","kind":"music","title":"Pausiert","lang":"de"}"#)
        #expect(german.lang == "de")
    }

    // MARK: Showing and tucking away

    @Test func aCardShowsForFourSecondsThenTucksAway() {
        let (model, brain, controller, scheduler) = connected()
        defer { withExtendedLifetime(controller) {} }
        brain.emit(.actionDone(Self.dentist))
        #expect(model.done.cards.map(\.action) == [Self.dentist])
        #expect(Presence.needs(model), "Milo stays on screen while a card shows")
        scheduler.advance(by: DoneCards.stay - 0.1)
        #expect(model.done.cards.count == 1)
        scheduler.advance(by: 0.2)
        #expect(model.done.cards.isEmpty)
    }

    @Test func theCardsStayWhileThePointerIsOnThem() {
        let (model, brain, controller, scheduler) = connected()
        defer { withExtendedLifetime(controller) {} }
        brain.emit(.actionDone(Self.dentist))
        model.done.hover(true)
        scheduler.advance(by: 30)
        #expect(model.done.cards.count == 1, "held while hovered")
        model.done.hover(false)
        scheduler.advance(by: DoneCards.afterHover + 0.1)
        #expect(model.done.cards.isEmpty, "goes a moment after the pointer leaves")
    }

    @Test func thePanelsPointerCheckHoldsThemTooWhenNoHoverIsHeard() {
        let scheduler = ManualScheduler()
        let done = DoneCards(scheduler: scheduler)
        var on = true
        done.pointing = { on }
        done.add(Self.dentist)
        scheduler.advance(by: 10)
        #expect(done.cards.count == 1 && done.hovered)
        on = false
        scheduler.advance(by: DoneCards.pointerCheck + DoneCards.afterHover + 0.1)
        #expect(done.cards.isEmpty && !done.hovered)
        #expect(scheduler.pendingCount == 0, "no pointer check left running without cards")
    }

    @Test func severalStackAndTheOldestGivesWayToAFourth() {
        let scheduler = ManualScheduler()
        let done = DoneCards(scheduler: scheduler)
        for n in 1...4 { done.add(ActionDone(kind: .note, title: "Note \(n)")) }
        #expect(done.cards.map(\.action.title) == ["Note 2", "Note 3", "Note 4"])
        scheduler.advance(by: DoneCards.stay + 0.1)
        #expect(done.cards.isEmpty, "each keeps its own clock, and a pushed-out one's never fires")
    }

    // MARK: Clicks

    @Test func aClickOpensTheItemAndTheCardGoes() throws {
        let scheduler = ManualScheduler()
        let done = DoneCards(scheduler: scheduler)
        var opened: [ActionDone] = []
        done.onOpen = { opened.append($0) }
        done.add(Self.milk)
        done.open(try #require(done.cards.first).id)
        #expect(opened == [Self.milk])
        #expect(done.cards.isEmpty)
    }

    @Test func undoOnACardSendsTheTasksUndo() throws {
        let (model, brain, controller, _) = connected()
        defer { withExtendedLifetime(controller) {} }
        brain.emit(.actionDone(Self.dentist))
        model.done.undo(try #require(model.done.cards.first).id)
        #expect(brain.sent.contains(.undoTask(id: "t1")), "a task the brain hasn't listed yet still goes")
    }

    @Test func undoOnACardGoesOnlyOnceAndNeverWithoutATask() throws {
        let (model, brain, controller, _) = connected()
        defer { withExtendedLifetime(controller) {} }
        brain.emit(.undoPoints([UndoPoint(id: "t1", title: "Dentist", state: .undoing)]))
        brain.emit(.actionDone(Self.dentist))
        brain.emit(.actionDone(Self.milk))
        for card in model.done.cards { model.done.undo(card.id) }
        #expect(!brain.sent.contains { if case .undoTask = $0 { true } else { false } })
    }

    // MARK: Where a click goes

    @Test func eachKindOpensWhereItLives() {
        #expect(DonePlace.of(Self.dentist) == .event(app: "Calendar", title: "Dentist", start: Self.dentist.when))
        #expect(DonePlace.of(Self.milk) == .reminder(app: "Reminders", title: "Buy milk"))
        #expect(DonePlace.of(ActionDone(kind: .reminder, title: "Call the dentist")) == .today,
                "Milo's own reminders are on Today")
        #expect(DonePlace.of(ActionDone(kind: .reminder, title: "Call", app: "Reminders")) ==
                .reminder(app: "Reminders", title: "Call"))
        #expect(DonePlace.of(ActionDone(kind: .note, title: "Packing list")) == .app("Notes"))
        #expect(DonePlace.of(ActionDone(kind: .draft, title: "To Anna")) == .app("Mail"))
        #expect(DonePlace.of(ActionDone(kind: .opened, title: "YouTube", detail: "youtube.com", app: "Safari")) ==
                .page("https://youtube.com"))
        #expect(DonePlace.of(ActionDone(kind: .opened, title: "Excel", app: "Microsoft Excel")) ==
                .app("Microsoft Excel"))
        #expect(DonePlace.of(ActionDone(kind: .other, title: "Something")) == .none)
        #expect(DonePlace.of(ActionDone(kind: .opened, title: "evil.com", app: "Finder")) == .app("Finder"),
                "a file named like a site opened in Finder: its name never becomes a page to open")
    }

    // MARK: Words

    @Test func theLineUnderTheTitleSaysWhenAndWhat() throws {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = try #require(TimeZone(identifier: "Europe/Berlin"))
        let locale = Locale(identifier: "en_GB")
        func at(_ text: String) -> Date { ISO8601DateFormatter().date(from: text)! }
        let now = at("2026-11-04T10:00:00+01:00")
        func line(_ action: ActionDone) -> String { DoneCardText.line(action, now: now, calendar: calendar, locale: locale) }
        #expect(line(ActionDone(kind: .reminder, title: "Standup", when: at("2026-11-04T15:00:00+01:00"))) ==
                "Today 15:00")
        #expect(line(ActionDone(kind: .reminder, title: "Dentist", detail: "Dr. Lee",
                                when: at("2026-11-05T09:30:00+01:00"))) == "Tomorrow 9:30, Dr. Lee")
        #expect(line(ActionDone(kind: .reminder, title: "Trip", when: at("2026-11-12T08:00:00+01:00"))) ==
                "Thu 12 Nov, 8:00")
        #expect(line(ActionDone(kind: .event, title: "Dentist", detail: "Dr. Lee", when: at("2026-11-12T08:00:00+01:00")))
                == "8:00, Dr. Lee", "the calendar page shows the day")
        #expect(line(ActionDone(kind: .timer, title: "Pasta", when: at("2026-11-04T10:12:00+01:00"))) == "Rings at 10:12")
        #expect(line(ActionDone(kind: .todo, title: "Buy milk", app: "Reminders")) == "In Reminders")
        #expect(line(ActionDone(kind: .draft, title: "To Anna")) == "Draft, not sent")
        #expect(line(ActionDone(kind: .music, title: "Paused")) == "Music", "never \"Playing\" for a pause")
        #expect(line(ActionDone(kind: .music, title: "Paused", app: "Spotify")) == "Spotify")
    }

    @Test func theCardsOwnWordsFollowTheLanguageMiloSpoke() throws {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = try #require(TimeZone(identifier: "Europe/Berlin"))
        func at(_ text: String) -> Date { ISO8601DateFormatter().date(from: text)! }
        let now = at("2026-11-04T10:00:00+01:00")
        func line(_ action: ActionDone, _ locale: String) -> String {
            DoneCardText.line(action, now: now, calendar: calendar, locale: Locale(identifier: locale))
        }
        let call = ActionDone(kind: .reminder, title: "Anna anrufen", when: at("2026-11-05T09:30:00+01:00"), lang: "de")
        #expect(line(call, "en_GB") == "Morgen 9:30", "the language Milo spoke wins over the Mac's")
        #expect(line(ActionDone(kind: .draft, title: "An Anna", lang: "de"), "en_GB") == "Entwurf, nicht gesendet")
        #expect(line(ActionDone(kind: .timer, title: "Nudeln", when: at("2026-11-04T10:12:00+01:00"), lang: "de"),
                     "en_GB") == "Klingelt um 10:12")
        #expect(line(ActionDone(kind: .draft, title: "To Anna"), "de_DE") == "Entwurf, nicht gesendet",
                "no language from the brain: the Mac's")
        #expect(line(ActionDone(kind: .draft, title: "To Anna", lang: "en"), "de_DE") == "Draft, not sent")
        #expect(line(ActionDone(kind: .draft, title: "Al Anna", lang: "it"), "en_GB") == "Draft, not sent",
                "a language the card has no words in: English")
        #expect(DoneCardText.opens(ActionDone(kind: .note, title: "Packliste", app: "Notes", lang: "de")) ==
                "Öffnet es in Notes")
        #expect(DoneCardText.spoken(ActionDone(kind: .todo, title: "Milch", app: "Reminders", lang: "de"), now: now)
                .hasPrefix("Zu deinen To-dos hinzugefügt: Milch"))
    }

    // MARK: Clicks through the panel

    @Test func aCardReachingIntoMilosSquareTakesTheClick() throws {
        let model = MiloModel(scheduler: ManualScheduler())
        let panel = OverlayPanel(model: model)
        let host = try #require(panel.contentView as? DraggableHostingView<OverlayView>)
        func point(_ p: CGPoint) -> NSPoint { host.isFlipped ? NSPoint(x: p.x, y: host.bounds.maxY - p.y) : p }
        // Bottom-left origin, inside his square but left of Milo himself.
        let spot = CGPoint(x: OverlayPanel.size.width - DraggableHostingView<OverlayView>.characterArea + 6, y: 120)
        #expect(host.isOnCharacter(point(spot)), "no card: it's Milo's square")
        model.done.add(Self.dentist)
        model.done.area = CGRect(x: 20, y: OverlayPanel.size.height - 150, width: 156, height: 56)  // top-left origin
        #expect(!host.isOnCharacter(point(spot)), "the card's corner takes the click, not a drag of Milo")
        #expect(host.isOnCharacter(point(OverlayPanel.characterCenter)), "Milo himself still drags")
        model.done.dismiss(try #require(model.done.cards.first).id)
        #expect(host.isOnCharacter(point(spot)), "gone with the card")
    }

    // MARK: The caption under the outline

    @Test func theCaptionFollowsTheHandsStepsOnly() {
        let (model, brain, controller, _) = connected()
        defer { withExtendedLifetime(controller) {} }
        brain.emit(.activity(taskID: "t2", step: ActivityStep(id: "hands_3", kind: "app",
                                                              title: "Typing “youtube.com” in Safari", detail: "",
                                                              status: .running)))
        model.handsActive = true
        #expect(model.workingStep == "Typing “youtube.com” in Safari")
        brain.emit(.activity(taskID: "t2", step: ActivityStep(id: "toolu_9", kind: "tool", title: "Typing", detail: "",
                                                              status: .running)))
        #expect(model.workingStep == "Typing “youtube.com” in Safari", "the worker's own steps don't replace it")
        brain.emit(.activity(taskID: "t2", step: ActivityStep(id: "hands_3", kind: "app",
                                                              title: "Typing “youtube.com” in Safari", detail: "",
                                                              status: .done)))
        #expect(model.workingStep == "Typing “youtube.com” in Safari", "it stays up until the next step")
        model.handsActive = false  // the screen controller's, on `hands_session` off or a stop
        #expect(model.workingStep == nil, "gone when the hands stop")
    }
}
