import AppKit
import Foundation
import SwiftUI
import Testing
@testable import MiloKit

/// Renders the Milo window offscreen into PNGs for a visual check:
/// `MILO_RENDER_DIR=/tmp/milo-render swift test --filter ConversationRender`.
@Suite(.enabled(if: ProcessInfo.processInfo.environment["MILO_RENDER_DIR"] != nil))
@MainActor
struct ConversationRenderTests {
    static let size = CGSize(width: 420, height: 560)
    let dir = URL(fileURLWithPath: ProcessInfo.processInfo.environment["MILO_RENDER_DIR"] ?? "/tmp")

    @Test func renderEveryState() throws {
        _ = NSApplication.shared
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        TaskBlock.openDetails = ["fail-3"]
        defer { TaskBlock.openDetails = [] }
        for (name, entries, state) in Samples.all {
            for dark in [false, true] {
                try render(entries: entries, state: state, name: "\(name)-\(dark ? "dark" : "light")", dark: dark,
                           question: name == "asking" ? Samples.question : nil)
            }
        }
    }

    @Test func renderRoutines() throws {
        _ = NSApplication.shared
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let previous = UserDefaults.standard.object(forKey: "showRoutines")
        defer { UserDefaults.standard.set(previous, forKey: "showRoutines") }
        for open in [false, true] {
            UserDefaults.standard.set(open, forKey: "showRoutines")
            for dark in [false, true] {
                try render(entries: Samples.oneTurn, state: .idle,
                           name: "routines-\(open ? "open" : "closed")-\(dark ? "dark" : "light")", dark: dark,
                           routines: .routines(Samples.routines, drafts: open ? [] : [Samples.draft]))
            }
        }
    }

    private func render(entries: [TranscriptEntry], state: MiloState, name: String, dark: Bool,
                        question: String? = nil, routines: BrainEvent? = nil, style: CharacterStyle = .milo) throws {
        let model = MiloModel(scheduler: ManualScheduler())
        model.character = style
        model.state = state
        if let routines { model.apply(routines) }
        if let question { model.apply(.confirm(id: "q1", question: question)) }
        let view = ConversationView(transcript: TranscriptModel(entries: entries), model: model,
                                    settings: ConversationSettings(talkKey: "right ⌥"), send: { _, _ in })
            .themed(by: model)
            .frame(width: Self.size.width, height: Self.size.height)
        let host = NSHostingView(rootView: view)
        host.frame = NSRect(origin: .zero, size: Self.size)
        let window = NSWindow(contentRect: host.frame, styleMask: [.titled], backing: .buffered, defer: false)
        window.appearance = NSAppearance(named: dark ? .darkAqua : .aqua)
        window.contentView = host
        host.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.3))
        let rep = try #require(host.bitmapImageRepForCachingDisplay(in: host.bounds))
        host.cacheDisplay(in: host.bounds, to: rep)
        let png = try #require(rep.representation(using: .png, properties: [:]))
        try png.write(to: dir.appendingPathComponent("\(name).png"))
    }
}

enum Samples {
    static let base = Date(timeIntervalSinceNow: -600)

    static let routines = [
        RoutineInfo(id: "monday-report", name: "Monday report", description: "Adds up last week's sales.",
                    schedule: "every Monday at 09:00", lastRun: "2026-10-26 09:00, done",
                    nextRun: Date(timeIntervalSinceNow: 3 * 86400), inputs: ["month"]),
        RoutineInfo(id: "tidy-downloads", name: "Tidy downloads", schedule: "every day at 18:00", paused: true),
        RoutineInfo(id: "invoices", name: "File the invoices", lastRun: "2026-10-29 16:12, done"),
        RoutineInfo(id: "broken", name: "broken", problem: "It must start with a line of three dashes (---)."),
    ]

    static let draft = RoutineDraft(id: "d1", name: "Monday report", recipe: """
        ---
        name: Monday report
        inputs:
          - name: month
            ask: Which month?
            default: last month
        schedule: every Monday at 09:00
        ---

        ## Goal

        A one-page sales report for the month in ~/Reports.

        ## Steps

        1. Read ~/Sales/{month}.csv.
           Check: it has one row for each day of the month.
        2. Make a table in Numbers with the total per week (sheet_write).
           Check: the table has a Total row.
        3. Save it as ~/Reports/{month}.numbers.
           Check: the file is there.

        ## Ask first

        - If the sales file for the month is missing.
        """, schedule: "every Monday at 09:00")

    static func at(_ seconds: TimeInterval) -> Date { base.addingTimeInterval(seconds) }

    static let oneTurn: [TranscriptEntry] = [
        TranscriptEntry(id: "u1", date: at(0), kind: .user, text: "Do I have anything this afternoon?", via: .voice),
        TranscriptEntry(id: "m1", date: at(4), kind: .milo, text: "Just the dentist at four. I'll remind you at half past three.",
                        emotion: .happy),
    ]

    static let longReply: [TranscriptEntry] = oneTurn + [
        TranscriptEntry(id: "u2", date: at(90), kind: .user, text: "how do I make the photos smaller before I email them",
                        via: .typed),
        TranscriptEntry(id: "m2", date: at(95), kind: .milo, text: """
            Open the photo in Preview, then choose Tools and Adjust Size. Pick a width of about 1600 pixels and \
            keep "Scale proportionally" ticked, so nothing gets squashed. Save it under a new name so the original \
            stays as it was. If there are many photos, select them all in Preview's sidebar first and resize them \
            in one go. Mail can also do it for you: when you attach them, the Image Size menu at the bottom right \
            of the message lets you choose Medium.
            """, emotion: .neutral, done: false),
    ]

    static let runningTask: [TranscriptEntry] = [
        TranscriptEntry(id: "u1", date: at(0), kind: .user, text: "rename the photos from Friday by the date they were taken",
                        via: .voice),
        TranscriptEntry(id: "m1", date: at(3), kind: .milo, text: "On it. I'll sort them by date.", emotion: .excited),
        TranscriptEntry(id: "t1", date: at(4), kind: .task,
                        text: "Rename the photos from Friday in ~/Pictures/Friday to their capture date",
                        status: .running, steps: [
                            ActivityStep(id: "1", kind: "read", title: "Looking in your Pictures folder",
                                         detail: "ls ~/Pictures", status: .done),
                            ActivityStep(id: "2", kind: "read", title: "Looking in the Friday folder",
                                         detail: "ls ~/Pictures/Friday", status: .done),
                            ActivityStep(id: "3", kind: "command", title: "Running a small program",
                                         detail: "python3 read_dates.py", status: .done),
                            ActivityStep(id: "4", kind: "edit", title: "Making the Sorted folder",
                                         detail: "mkdir -p ~/Pictures/Friday/Sorted", status: .done),
                            ActivityStep(id: "5", kind: "edit", title: "Moving IMG_4012.jpg",
                                         detail: "mv IMG_4012.jpg Sorted/2026-10-24 18.02.jpg", status: .done),
                            ActivityStep(id: "6", kind: "edit", title: "Moving IMG_4013.jpg",
                                         detail: "mv IMG_4013.jpg Sorted/2026-10-24 18.05.jpg", status: .running),
                        ]),
    ]

    static let failedStep: [TranscriptEntry] = [
        TranscriptEntry(id: "u1", date: at(0), kind: .user, text: "put the Hetzner invoice in my tax folder", via: .voice),
        TranscriptEntry(id: "m1", date: at(3), kind: .milo, text: "Sure, let me look for it.", emotion: .happy),
        TranscriptEntry(id: "t1", date: at(4), kind: .task, text: "Find the newest Hetzner invoice PDF and move it to ~/Documents/Tax",
                        status: .failed, result: "I couldn't find a Tax folder. Should I make one?",
                        steps: [
                            ActivityStep(id: "1", kind: "search", title: "Looking for files in your Downloads folder",
                                         detail: "find ~/Downloads -iname '*hetzner*'", status: .done),
                            ActivityStep(id: "2", kind: "read", title: "Reading Hetzner_2026-10.pdf",
                                         detail: "pdftotext Hetzner_2026-10.pdf -", status: .done),
                            ActivityStep(id: "fail-3", kind: "edit", title: "Moving Hetzner_2026-10.pdf",
                                         detail: "mv Hetzner_2026-10.pdf ~/Documents/Tax/\n\nmv: ~/Documents/Tax/: No such file or directory",
                                         status: .failed),
                        ]),
        TranscriptEntry(id: "u2", date: at(70), kind: .user, text: "yes please", via: .typed),
    ]

    static let question = "I'm about to run your shortcut “Text Anna I'm late”. Go ahead?"

    static let asking: [TranscriptEntry] = [
        TranscriptEntry(id: "u1", date: at(0), kind: .user, text: "tell Anna I'm running late", via: .voice),
        TranscriptEntry(id: "m1", date: at(2), kind: .milo, text: "On it.", emotion: .happy),
        TranscriptEntry(id: "t1", date: at(3), kind: .task, text: "Tell Anna the user is running late",
                        status: .running, steps: [
                            ActivityStep(id: "1", kind: "app", title: "Checking your shortcuts",
                                         detail: "milo.shortcuts_list {}", status: .done),
                            ActivityStep(id: "2", kind: "app", title: "Running your shortcut “Text Anna I'm late”",
                                         detail: "milo.shortcuts_run {\"name\": \"Text Anna I'm late\"}",
                                         status: .running),
                        ]),
        TranscriptEntry(id: "m2", date: at(4), kind: .milo, text: question, emotion: .thinking),
    ]

    static let all: [(String, [TranscriptEntry], MiloState)] = [
        ("empty", [], .idle),
        ("one-turn", oneTurn, .idle),
        ("long-reply", longReply, .speaking),
        ("running-task", runningTask, .idle),
        ("failed-step", failedStep, .thinking),
        ("asking", asking, .idle),
    ]
}
