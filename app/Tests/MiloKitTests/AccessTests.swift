import Foundation
import Testing
@testable import MiloKit

/// The first time Milo controls an app (ADR 25): the brain's `access.*` ops, the note in the bubble with Fix it,
/// the list of apps macOS was asked about, and the guard that keeps sandboxed apps from asking for file access.

final class FakeAccessSource: AccessSource {
    var states: [String: AccessState] = [:]
    var clicks: [String: AccessState] = [:]
    var ui = AccessState.yes
    var places: [String: [String]] = [:]
    var calls: [String] = []
    var opened: [AccessNeed] = []

    func check(_ need: AccessNeed, app: AccessApp?, launch: Bool) -> AccessAnswer {
        calls.append("check \(need.rawValue) \(app?.name ?? "") launch=\(launch)")
        if need != .control { return AccessAnswer(ui, system: "macOS", label: "Accessibility") }
        let name = app?.name ?? ""
        return AccessAnswer(states[name] ?? .yes, app: AccessApp(name: name, bundle: "com.example.\(name)"),
                            system: "macOS", button: "Allow")
    }

    func request(_ need: AccessNeed, app: AccessApp?) -> AccessAnswer {
        calls.append("request \(need.rawValue) \(app?.name ?? "")")
        let name = app?.name ?? ""
        if states[name] == .ask { states[name] = clicks[name] ?? .yes }
        return check(need, app: app, launch: false)
    }

    func places(for app: AccessApp) -> [String]? { places[app.name] }
    func openSettings(_ need: AccessNeed, app: AccessApp?) { opened.append(need) }
}

private func defaults() -> UserDefaults {
    let name = "AccessTests-\(UUID().uuidString)"
    let d = UserDefaults(suiteName: name)!
    d.removePersistentDomain(forName: name)
    return d
}

private func handle(_ requests: AccessRequests, _ op: String, _ args: [String: JSONValue]) -> AppOutcome? {
    var outcome: AppOutcome?
    requests.handle(op: op, args: .object(args)) { outcome = $0 }
    return outcome
}

private func inline() -> DispatchQueue { DispatchQueue(label: "access-tests") }

@Suite struct AccessRequestsTests {
    func make(_ source: FakeAccessSource, next: AppConnections? = nil) -> (AccessRequests, ControlledApps) {
        let apps = ControlledApps(defaults: defaults())
        // Off-main work runs synchronously and "main" runs inline, so the answer is there when handle returns.
        let requests = AccessRequests(source: source, apps: apps, next: next, queue: inline(), main: { $0() })
        return (requests, apps)
    }

    func sync(_ requests: AccessRequests, _ op: String, _ args: [String: JSONValue]) -> AppOutcome? {
        var outcome: AppOutcome?
        let done = DispatchSemaphore(value: 0)
        requests.handle(op: op, args: .object(args)) { outcome = $0; done.signal() }
        done.wait()
        return outcome
    }

    @Test func aCheckAnswersInTheBrainsWordsAndNeverAsks() {
        let source = FakeAccessSource()
        source.states["Microsoft Excel"] = .ask
        let (requests, apps) = make(source)
        let outcome = sync(requests, "access.check", ["need": .string("control"), "app": .string("Microsoft Excel"),
                                                     "launch": .bool(true)])
        #expect(outcome == .success(.object(["access": .string("ask"), "app": .string("Microsoft Excel"),
                                             "bundle": .string("com.example.Microsoft Excel"),
                                             "system": .string("macOS"), "button": .string("Allow")])))
        #expect(source.calls == ["check control Microsoft Excel launch=true"])
        #expect(apps.entries.isEmpty, "not decided yet: nothing to list")
    }

    @Test func whileTheSystemAsksTheTakeoverCheckIsToldAndTheAnswerIsListed() {
        let source = FakeAccessSource()
        source.states["Microsoft Excel"] = .ask
        source.clicks["Microsoft Excel"] = .no
        let (requests, apps) = make(source)
        var asking: [Bool] = []
        requests.onAsking = { asking.append($0) }
        let outcome = sync(requests, "access.request", ["need": .string("control"), "app": .string("Microsoft Excel")])
        #expect(outcome?.accessState == "no")
        #expect(asking == [true, false])
        #expect(apps.entries.map(\.allowed) == [false])
        #expect(apps.entries.first?.app.name == "Microsoft Excel")
    }

    @Test func placesSayWhetherTheAppIsSandboxed() {
        let source = FakeAccessSource()
        source.places["Microsoft Excel"] = ["/c/Excel"]
        let (requests, _) = make(source)
        #expect(sync(requests, "access.places", ["app": .string("Microsoft Excel")])
            == .success(.object(["sandboxed": .bool(true), "places": .array([.string("/c/Excel")])])))
        #expect(sync(requests, "access.places", ["app": .string("TextEdit")])
            == .success(.object(["sandboxed": .bool(false), "places": .array([])])))
    }

    @Test func otherOpsGoOnToCalendarAndReminders() {
        let next = FakeConnections()
        let (requests, _) = make(FakeAccessSource(), next: next)
        _ = handle(requests, "calendar.events", [:])
        #expect(next.handled.map(\.op) == ["calendar.events"])
    }

    @Test func aControlCheckWithoutAnAppIsRefused() {
        let (requests, _) = make(FakeAccessSource())
        guard case .failure = handle(requests, "access.check", ["need": .string("control")]) else {
            Issue.record("expected a failure")
            return
        }
    }
}

private extension AppOutcome {
    var accessState: String? {
        if case let .success(value) = self { return value["access"]?.string }
        return nil
    }
}

@Suite struct ControlledAppsTests {
    @Test func onlyAYesOrANoIsListedInNameOrderAndRemembered() {
        let store = defaults()
        let apps = ControlledApps(defaults: store)
        apps.note(AccessAnswer(.yes, app: AccessApp(name: "Numbers", bundle: "com.apple.iWork.Numbers")))
        apps.note(AccessAnswer(.ask, app: AccessApp(name: "Keynote", bundle: "com.apple.iWork.Keynote")))
        apps.note(AccessAnswer(.unknown, app: AccessApp(name: "Pages")))
        apps.note(AccessAnswer(.no, app: AccessApp(name: "Microsoft Excel", bundle: "com.microsoft.Excel")))
        apps.note(AccessAnswer(.yes, app: AccessApp(name: "Microsoft Excel", bundle: "com.microsoft.Excel")))
        #expect(apps.entries.map(\.app.name) == ["Microsoft Excel", "Numbers"])
        #expect(apps.entries.map(\.allowed) == [true, true], "the newer answer replaces the older")
        #expect(ControlledApps(defaults: store).entries == apps.entries)
    }

    @Test func theMenuTicksAllowedAppsAndSaysWhichArent() {
        let apps = ControlledApps(defaults: defaults())
        apps.note(AccessAnswer(.yes, app: AccessApp(name: "Mail", bundle: "com.apple.mail")))
        apps.note(AccessAnswer(.no, app: AccessApp(name: "Numbers", bundle: "com.apple.iWork.Numbers")))
        let rows = StatusMenu.appRows(apps.entries)
        #expect(rows.map(\.title) == ["Mail", "Numbers: not allowed"])
        #expect(rows.map(\.allowed) == [true, false])
    }
}

@Suite @MainActor struct AccessBubbleTests {
    let excel = AccessApp(name: "Microsoft Excel", bundle: "com.microsoft.Excel")

    @Test func aRefusalShowsFixItForThatApp() {
        let model = MiloModel(scheduler: ManualScheduler())
        var fixed: [BubbleAction] = []
        model.onBubbleAction = { fixed.append($0) }
        model.apply(.access(AccessNote(need: .control, state: .no, text: "Okay, I won't use Microsoft Excel.", app: excel)))
        #expect(model.bubble == "Okay, I won't use Microsoft Excel.")
        #expect(model.bubbleAction == .access(.control, excel))
        #expect(model.bubbleAction?.title == "Fix it")
        model.performBubbleAction()
        #expect(fixed == [.access(.control, excel)])
    }

    @Test func theLineBeforeTheSystemsQuestionHasNoButton() {
        let model = MiloModel(scheduler: ManualScheduler())
        model.apply(.access(AccessNote(need: .control, state: .ask, text: "macOS will ask once.", app: excel)))
        #expect(model.bubble == "macOS will ask once.")
        #expect(model.bubbleAction == nil)
    }

    @Test func theWireNoteDecodes() throws {
        let line = #"{"type": "access", "need": "ui", "state": "no", "text": "To work in other apps' windows I need Accessibility.", "app": "", "bundle": ""}"#
        let event = try JSONDecoder().decode(BrainEvent.self, from: Data(line.utf8))
        #expect(event == .access(AccessNote(need: .ui, state: .no,
                                            text: "To work in other apps' windows I need Accessibility.")))
    }
}

@Suite struct SandboxGuardTests {
    let container = "/Users/you/Library/Containers/com.microsoft.Excel/Data"
    func places(_ app: AccessApp) -> [String]? {
        app.name == "Microsoft Excel" || app.bundle == "com.microsoft.Excel" ? [container] : nil
    }

    func refusal(_ script: String) -> String? {
        SandboxGuard.refusal(script: script, home: "/Users/you", places: places)
    }

    @Test func savingExcelOutsideItsFolderIsRefusedBeforeMacOSCanAsk() {
        let script = """
        tell application "Microsoft Excel"
          save workbook as active workbook filename "/Users/you/Milo/work/Budget.xlsx"
        end tell
        """
        let why = refusal(script)
        #expect(why?.contains("Grant File Access") == true)
        #expect(why?.contains(container) == true, "it says where a working copy may go")
        #expect(refusal(script.replacingOccurrences(of: "/Users/you/Milo/work", with: "~/Desktop")) != nil)
        #expect(refusal(script.replacingOccurrences(of: "\"/Users/you/Milo/work/Budget.xlsx\"",
                                                    with: "\"Macintosh HD:Users:you:Desktop:Budget.xlsx\"")) != nil)
        #expect(refusal(#"tell application id "com.microsoft.Excel" to save active workbook in "/tmp/x.xlsx""#) != nil)
    }

    @Test func aFolderFromPathToCountsAsOutside() {
        #expect(refusal("""
        tell application "Microsoft Excel"
          save workbook as active workbook filename ((path to desktop as text) & "Budget.xlsx")
        end tell
        """) != nil)
    }

    @Test func savingInsideItsOwnFolderOrInPlaceGoesThrough() {
        #expect(refusal("""
        tell application "Microsoft Excel"
          save workbook as active workbook filename "\(container)/Milo/snapshot.xlsx"
        end tell
        """) == nil)
        #expect(refusal(#"tell application "Microsoft Excel" to save active workbook"#) == nil)
        #expect(refusal(#"tell application "Microsoft Excel" to set value of range "A1" to "/Users/you""#) == nil,
                "no save: a path in a cell is only text")
    }

    @Test func appsThatArentSandboxedSaveAnywhere() {
        #expect(refusal(#"tell application "TextEdit" to save document 1 in POSIX file "/Users/you/Desktop/a.rtf""#) == nil)
    }

    @Test func theSandboxPlacesComeFromTheEntitlements() {
        let entitlements: [String: Any] = [
            "com.apple.security.app-sandbox": true,
            "com.apple.security.application-groups": ["UBF8T346G9.Office"],
            "com.apple.security.files.downloads.read-write": true,
            "com.apple.security.temporary-exception.files.home-relative-path.read-write": ["/Library/Fonts/"],
        ]
        #expect(MacAppAccess.places(entitlements: entitlements, bundle: "com.microsoft.Excel", home: "/Users/you") == [
            "/Users/you/Library/Containers/com.microsoft.Excel/Data",
            "/Users/you/Library/Group Containers/UBF8T346G9.Office",
            "/Users/you/Downloads",
            "/Users/you/Library/Fonts/",
        ])
        #expect(MacAppAccess.places(entitlements: [:], bundle: "com.apple.TextEdit", home: "/Users/you") == nil)
    }
}

@Suite struct HandsAccessibilityTests {
    @Test func scriptsAndOpeningAppsDontNeedAccessibility() {
        #expect(!MacHands.needsAccessibility("run_applescript", [:]))
        #expect(!MacHands.needsAccessibility("describe", ["tool": .string("run_applescript")]))
        #expect(!MacHands.needsAccessibility("describe", ["tool": .string("open_app")]))
        #expect(MacHands.needsAccessibility("describe", ["tool": .string("click")]))
        #expect(MacHands.needsAccessibility("ax_tree", [:]))
    }
}
