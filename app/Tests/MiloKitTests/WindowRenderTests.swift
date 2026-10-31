import AppKit
import Foundation
import SwiftUI
import Testing
@testable import MiloKit

/// Renders the Milo window with its sidebar offscreen into PNGs: Today, a conversation, an older one, a task's page,
/// search, the narrow window and the empty states, light and dark:
/// `MILO_RENDER_DIR=/tmp/milo-window swift test --filter WindowRender`.
@Suite(.enabled(if: ProcessInfo.processInfo.environment["MILO_RENDER_DIR"] != nil), .serialized)
@MainActor
struct WindowRenderTests {
    static let size = CGSize(width: 780, height: 580)
    let dir = URL(fileURLWithPath: ProcessInfo.processInfo.environment["MILO_RENDER_DIR"] ?? "/tmp")

    @Test func renderEveryPage() throws {
        _ = NSApplication.shared
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        TodayView.entrance = false
        let clock = ConversationsSidebar.now
        ConversationsSidebar.now = { Day.now }
        defer { TodayView.entrance = true; ConversationsSidebar.now = clock }

        for dark in [false, true] {
            let mode = dark ? "dark" : "light"
            try render(.today, name: "today-\(mode)", dark: dark, busy: true)
            try render(.today, name: "today-calm-\(mode)", dark: dark, empty: true)
            try render(.live, name: "conversation-\(mode)", dark: dark)
            try render(.conversation("c-hamburg"), name: "older-\(mode)", dark: dark)
            try render(.task("t-photos"), name: "task-done-\(mode)", dark: dark)
            try render(.task("t-excel"), name: "task-running-\(mode)", dark: dark, busy: true)
            try render(.live, name: "search-\(mode)", dark: dark, search: "photos")
            try render(.live, name: "empty-\(mode)", dark: dark, empty: true)
            try render(.live, name: "narrow-\(mode)", dark: dark, size: CGSize(width: 440, height: 580))
            try render(.live, name: "narrow-sidebar-\(mode)", dark: dark, size: CGSize(width: 440, height: 580),
                       sidebar: true)
            try render(.usage, name: "usage-\(mode)", dark: dark, usage: UsageModel(report: Month.report()),
                       size: CGSize(width: 900, height: 1100))
            try renderMeetings(mode: mode, dark: dark)
            try render(.usage, name: "usage-new-\(mode)", dark: dark, usage: UsageModel(report: Month.report(empty: true)))
            try render(.usage, name: "usage-narrow-\(mode)", dark: dark, usage: UsageModel(report: Month.report()),
                       size: CGSize(width: 440, height: 1300))
        }
    }

    /// A meeting's page while it records, while the notes are written, and its notes, to-dos and transcript after.
    private func renderMeetings(mode: String, dark: Bool) throws {
        let questions = [
            TranscriptEntry(id: "m0", date: Day.at(-19 * 3600), kind: .milo,
                            text: "Taking notes. Stop me any time with the button next to me.", conversation: "c-sync"),
            TranscriptEntry(id: "m1", date: Day.at(-19 * 3600 + 120), kind: .user, text: "What did I miss?",
                            via: .typed, conversation: "c-sync"),
            TranscriptEntry(id: "m2", date: Day.at(-19 * 3600 + 124), kind: .milo,
                            text: "The launch moves to Friday because of the app review. Anna sends the slides.",
                            conversation: "c-sync"),
        ]
        let transcript = { TranscriptModel(entries: Day.budget, conversations: Day.conversations, current: "c-budget",
                                           opened: ["c-sync": questions]) }
        let live: (MiloModel, MeetingStatus.Phase, Int) -> Void = { model, phase, count in
            model.recording = phase != .writing
            model.apply(.meetingStatus(MeetingRenders.status(phase, elapsed: 754,
                                                             step: phase == .writing ? "Writing the summary" : "")))
            model.apply(.meetingLines(id: MeetingRenders.id, lines: Array(MeetingRenders.lines.prefix(count)), reset: true))
        }
        try render(.conversation("c-sync"), name: "meeting-live-\(mode)", dark: dark, transcript: transcript()) {
            live($0, .recording, 7)
        }
        try render(.conversation("c-sync"), name: "meeting-start-\(mode)", dark: dark,
                   transcript: TranscriptModel(entries: Day.budget, conversations: Day.conversations,
                                               current: "c-budget", opened: ["c-sync": [questions[0]]])) {
            live($0, .recording, 0)
        }
        try render(.conversation("c-sync"), name: "meeting-paused-\(mode)", dark: dark, transcript: transcript()) {
            live($0, .paused, 8)
        }
        try render(.conversation("c-sync"), name: "meeting-writing-\(mode)", dark: dark, transcript: transcript()) {
            live($0, .writing, 8)
        }
        try render(.conversation("c-sync"), name: "meeting-live-narrow-\(mode)", dark: dark,
                   size: CGSize(width: 440, height: 580), transcript: transcript()) { live($0, .recording, 7) }
        let done: (MiloModel) -> Void = { model in
            model.apply(.meetingNotes(MeetingRenders.notes))
            model.apply(.meetingLines(id: MeetingRenders.id, lines: MeetingRenders.lines, reset: true))
        }
        defer { MeetingPage.startTab = .notes }
        for tab in MeetingPage.Tab.allCases {
            MeetingPage.startTab = tab
            try render(.conversation("c-sync"), name: "meeting-\(tab.rawValue.lowercased())-\(mode)", dark: dark,
                       transcript: transcript(), setup: done)
        }
        MeetingPage.startTab = .notes
        try render(.conversation("c-sync"), name: "meeting-notes-narrow-\(mode)", dark: dark,
                   size: CGSize(width: 440, height: 580), transcript: transcript(), setup: done)
    }

    private func render(_ page: WindowPage, name: String, dark: Bool, busy: Bool = false, empty: Bool = false,
                        search: String = "", usage: UsageModel = UsageModel(),
                        size: CGSize = CGSize(width: 780, height: 580), sidebar: Bool = false,
                        transcript given: TranscriptModel? = nil, setup: (MiloModel) -> Void = { _ in }) throws {
        let model = MiloModel(scheduler: ManualScheduler())
        model.connected = true
        setup(model)
        let transcript = given ?? (empty ? TranscriptModel() : Day.transcript())
        if busy {
            model.apply(.helpers([
                HelperInfo(id: "t-excel", title: "Budget table in Excel", status: .working,
                           step: "Typing “Monday” in Excel", progress: 0.4),
            ]))
            model.apply(.confirm(id: "q1", question: "I'm about to run your shortcut “Text Anna I'm late”. Go ahead?"))
        }
        if !empty && busy { transcript.apply(.reminders(Day.reminders)) }
        if !search.isEmpty {
            transcript.apply(.searchResults(query: search, results: [
                SearchHit(conversation: "c-photos", title: "Photos from Friday", date: Day.at(-50 * 60),
                          snippet: "can you rename the photos from Friday by the date they were taken", via: [.voice]),
                SearchHit(conversation: "c-mum", title: "Mum's birthday", date: Day.at(-3 * 86400),
                          snippet: "and send her the photos from the garden", via: [.message]),
            ]))
        }
        let route = WindowRoute(page: .live)
        route.go(page)
        route.search = search
        route.sidebarShown = sidebar
        let view = ConversationView(transcript: transcript, model: model,
                                    settings: ConversationSettings(talkKey: "right ⌥"), route: route,
                                    actions: WindowActions(reveal: { _ in }), usage: usage)
            .themed(by: model)
            .frame(width: size.width, height: size.height)
        let host = NSHostingView(rootView: view)
        host.frame = NSRect(origin: .zero, size: size)
        let window = NSWindow(contentRect: host.frame, styleMask: [.titled], backing: .buffered, defer: false)
        window.appearance = NSAppearance(named: dark ? .darkAqua : .aqua)
        window.contentView = host
        host.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.4))
        let rep = try #require(host.bitmapImageRepForCachingDisplay(in: host.bounds))
        host.cacheDisplay(in: host.bounds, to: rep)
        let png = try #require(rep.representation(using: .png, properties: [:]))
        try png.write(to: dir.appendingPathComponent("\(name).png"))
    }
}

/// A morning with Milo: the photos renamed, a train asked about from the phone, a meeting and a routine run.
enum Day {
    static let now = Calendar.current.date(from: DateComponents(year: 2026, month: 10, day: 30, hour: 10, minute: 20))!

    static func at(_ seconds: TimeInterval) -> Date { now.addingTimeInterval(seconds) }

    static let reminders = [
        ReminderItem(due: at(5 * 3600 + 10 * 60), text: "Leave for the dentist"),
        ReminderItem(due: at(23 * 3600), text: "Call Anna about Sunday"),
    ]

    static let photosTask = TranscriptEntry(
        id: "t-photos", date: at(-49 * 60), kind: .task,
        text: "Rename the photos from Friday in ~/Pictures/Friday to the date they were taken", status: .done,
        result: "I renamed all 40 photos by the date they were taken. The list of old and new names is in renamed.txt.",
        steps: [
            ActivityStep(id: "1", kind: "read", title: "Looking in your Pictures folder", detail: "ls ~/Pictures",
                         status: .done),
            ActivityStep(id: "2", kind: "command", title: "Reading when each photo was taken",
                         detail: "python3 read_dates.py", status: .done),
            ActivityStep(id: "3", kind: "edit", title: "Renaming 40 photos",
                         detail: "mv IMG_4012.jpg \"2026-10-24 18.02.jpg\"", status: .done),
            ActivityStep(id: "4", kind: "edit", title: "Writing the list of names", detail: "renamed.txt", status: .done),
        ],
        conversation: "c-photos", title: "Rename Friday's photos",
        files: ["~/Pictures/Friday/renamed.txt", "~/Pictures/Friday"])

    static let excelTask = TranscriptEntry(
        id: "t-excel", date: at(-4 * 60), kind: .task, text: "Make a budget table for November in Excel",
        status: .running, steps: [
            ActivityStep(id: "1", kind: "app", title: "Opening Microsoft Excel", status: .done),
            ActivityStep(id: "2", kind: "app", title: "Typing “Monday” in Excel", status: .running),
        ], conversation: "c-budget", title: "November budget")

    static let budget: [TranscriptEntry] = [
        TranscriptEntry(id: "b1", date: at(-5 * 60), kind: .user, text: "can you make me a budget table for November",
                        via: .voice, conversation: "c-budget"),
        TranscriptEntry(id: "b2", date: at(-5 * 60 + 4), kind: .milo,
                        text: "Sure. I'll put it in Excel with a row for each week.", emotion: .excited,
                        conversation: "c-budget"),
        excelTask,
        TranscriptEntry(id: "b3", date: at(-60), kind: .user, text: "and put the rent in as 900", via: .typed,
                        conversation: "c-budget"),
        TranscriptEntry(id: "b4", date: at(-56), kind: .milo,
                        text: "Got it, the rent goes in at 900 for every week. I'll tell you when the table is ready.",
                        emotion: .happy, conversation: "c-budget"),
    ]

    static let photos: [TranscriptEntry] = [
        TranscriptEntry(id: "p1", date: at(-50 * 60), kind: .user,
                        text: "can you rename the photos from Friday by the date they were taken", via: .voice,
                        conversation: "c-photos"),
        TranscriptEntry(id: "p2", date: at(-50 * 60 + 3), kind: .milo, text: "On it. I'll sort them by date.",
                        emotion: .happy, conversation: "c-photos"),
        photosTask,
        TranscriptEntry(id: "p3", date: at(-47 * 60), kind: .milo,
                        text: "Done: all 40 are renamed. The list is in renamed.txt if you want to check.",
                        emotion: .happy, conversation: "c-photos"),
    ]

    static let hamburg: [TranscriptEntry] = [
        TranscriptEntry(id: "h1", date: at(-160 * 60), kind: .user, text: "is my train to Hamburg on time",
                        via: .message, conversation: "c-hamburg"),
        TranscriptEntry(id: "h2", date: at(-160 * 60 + 5), kind: .milo,
                        text: "Yes, the 8:12 from Berlin is on time. It leaves from platform 6.", emotion: .happy,
                        conversation: "c-hamburg"),
        TranscriptEntry(id: "h3", date: at(-158 * 60), kind: .user, text: "and when do I get in", via: .message,
                        conversation: "c-hamburg"),
        TranscriptEntry(id: "h4", date: at(-158 * 60 + 4), kind: .milo, text: "At 9:58 in Hamburg Hbf.",
                        emotion: .neutral, conversation: "c-hamburg"),
    ]

    static var conversations: [ConversationInfo] {
        [
            ConversationInfo(id: "c-budget", started: at(-5 * 60), last: at(-56), title: "November budget",
                             via: [.voice, .typed], turns: 2, preview: "Got it, the rent goes in at 900.",
                             tasks: [TaskSummary(id: "t-excel", title: "November budget", status: .running,
                                                 date: at(-4 * 60))]),
            ConversationInfo(id: "c-photos", started: at(-50 * 60), last: at(-47 * 60), title: "Photos from Friday",
                             via: [.voice], turns: 1, preview: "Done: all 40 are renamed.",
                             tasks: [TaskSummary(id: "t-photos", title: "Rename Friday's photos", status: .done,
                                                 date: at(-47 * 60))]),
            ConversationInfo(id: "c-hamburg", started: at(-160 * 60), last: at(-158 * 60), title: "Train to Hamburg",
                             titledBy: "words", via: [.message], turns: 2, preview: "At 9:58 in Hamburg Hbf."),
            ConversationInfo(id: "c-sync", kind: .meeting, started: at(-19 * 3600), title: "Weekly sync",
                             preview: "Launch moves to Friday. Anna sends the slides.",
                             source: "meeting:2026-10-29-1400-weekly-sync"),
            ConversationInfo(id: "c-report", kind: .routine, started: at(-3 * 86400 - 3600), title: "Monday report",
                             preview: "The report is in Reports.",
                             tasks: [TaskSummary(id: "t-report", title: "Monday report", status: .done,
                                                 date: at(-3 * 86400 - 3600))],
                             source: "routine:Monday report"),
            ConversationInfo(id: "c-mum", started: at(-3 * 86400 - 7200), title: "Mum's birthday", via: [.message],
                             turns: 4, preview: "I put it in your calendar for Sunday."),
            ConversationInfo(id: "c-printer", started: at(-12 * 86400), title: "The printer won't print",
                             turns: 6, preview: "It works again: the paper tray was open.",
                             tasks: [TaskSummary(id: "t-printer", title: "Fix the printer", status: .failed,
                                                 date: at(-12 * 86400))]),
        ]
    }

    static func transcript() -> TranscriptModel {
        TranscriptModel(entries: budget, conversations: conversations, current: "c-budget",
                        opened: ["c-photos": photos, "c-hamburg": hamburg])
    }
}

/// A month with Milo: talking most days, a few big tasks, dictating into Slack and Mail, quiet weekends.
enum Month {
    static func report(empty: Bool = false) -> UsageReport {
        let calendar = Calendar.current
        let days = (0..<30).map { i -> UsageDay in
            let date = calendar.date(byAdding: .day, value: i - 29, to: Day.now)!
            let c = calendar.dateComponents([.year, .month, .day], from: date)
            let day = String(format: "%04d-%02d-%02d", c.year!, c.month!, c.day!)
            let weekend = calendar.isDateInWeekend(date)
            if empty || (i < 6) { return UsageDay(day: day) }
            let wave = (i * 37) % 11
            let calls = weekend ? wave % 3 : 4 + wave
            let input = calls * 9_000 + (i % 5 == 0 ? 60_000 : 0)
            return UsageDay(day: day, calls: calls, inputTokens: input, cachedInputTokens: input * 7 / 10,
                            outputTokens: calls * 140, dictations: weekend ? 1 : 6 + wave, words: weekend ? 12 : 80 + wave * 21)
        }
        return UsageReport(
            span: 30, today: days.last!.day, since: empty ? "" : days[6].day, daily: days,
            sources: empty ? [] : [UsageSource(source: "task", calls: 21, tokens: 1_310_000),
                                   UsageSource(source: "chat", calls: 164, tokens: 842_000),
                                   UsageSource(source: "memory", calls: 9, tokens: 96_000)],
            apps: empty ? [] : [UsageApp(app: "Slack", dictations: 88, words: 2_140),
                                UsageApp(app: "Mail", dictations: 41, words: 1_610),
                                UsageApp(app: "Notes", dictations: 17, words: 530),
                                UsageApp(app: "", dictations: 3, words: 40)],
            accounts: empty ? [] : [
                UsageAccount(service: "Claude", uses: ["Talking"], plan: "Max", who: "you@example.com"),
                UsageAccount(service: "ChatGPT", uses: ["Tasks"], detail: "Signed in with ChatGPT"),
                UsageAccount(service: "ElevenLabs", uses: ["Milo's voice", "Hearing you"], state: .unknown,
                             detail: "Can't see the plan: the API key lacks the user_read permission."),
                UsageAccount(service: "This Mac", uses: ["Dictation"], state: .local,
                             detail: "Whisper, nothing leaves the Mac"),
            ])
    }
}
