import AppKit
import Foundation
import SwiftUI
import Testing
@testable import MiloKit

/// Renders the overlay (bubble, pill, helpers, badges) in every state, for every skin, light and dark:
/// `MILO_RENDER_DIR=/tmp/milo-overlay swift test --filter OverlayRender`. `MILO_SKINS=pip,kit` renders only those.
@Suite(.enabled(if: ProcessInfo.processInfo.environment["MILO_RENDER_DIR"] != nil))
@MainActor
struct OverlayRenderTests {
    let dir = URL(fileURLWithPath: ProcessInfo.processInfo.environment["MILO_RENDER_DIR"] ?? "/tmp")

    /// One moment of the overlay, set up on a fresh model.
    struct Moment {
        var name: String
        var set: (MiloModel) -> Void
    }

    static let moments: [Moment] = [
        Moment(name: "01-idle") { _ in },
        Moment(name: "02-armed") { $0.press(.talk) },
        Moment(name: "03-listening") { m in
            m.press(.talk)
            m.apply(.state(.listening))
            for v in [0.1, 0.3, 0.6, 0.45, 0.2, 0.5, 0.7] { m.apply(.level(v)) }
        },
        Moment(name: "04-listening-words") { m in
            m.apply(.state(.listening))
            m.apply(.level(0.4))
            m.apply(.partial("Can you move my dentist appointment to Thursday"))
        },
        Moment(name: "05-dictating-handsfree") { m in
            m.apply(.state(.dictating))
            m.handsFree = .dictate
            m.apply(.level(0.3))
            m.apply(.partial("Dear Anna, thanks for the photos from the weekend, they made my day"))
        },
        Moment(name: "06-got-it") { m in
            m.apply(.state(.listening))
            m.release(.talk)
        },
        Moment(name: "07-transcribing") { m in
            m.apply(.state(.transcribing))
            m.apply(.partial("Can you move my dentist appointment to Thursday"))
        },
        Moment(name: "08-thinking") { m in
            m.apply(.heard("Can you move my dentist appointment to Thursday?"))
            m.apply(.state(.thinking))
        },
        Moment(name: "09-speaking") { m in
            m.apply(.heard("Do I have anything this afternoon?"))
            m.apply(.state(.speaking))
            m.apply(.bubble("Just the dentist at four. I'll remind you at half past three."))
        },
        Moment(name: "09b-spoken") { m in
            m.apply(.heard("Do I have anything this afternoon?"))
            m.apply(.state(.speaking))
            m.apply(.bubble("Just the dentist at four."))
            m.apply(.bubble("Just the dentist at four. I'll remind you at half past three."))
            m.apply(.state(.idle))
        },
        Moment(name: "10-speaking-long") { m in
            m.apply(.state(.speaking))
            m.apply(.bubble("""
                Open the photo in Preview, then choose Tools and Adjust Size. Pick a width of about 1600 pixels and \
                keep "Scale proportionally" ticked, so nothing gets squashed. Save it under a new name so the \
                original stays as it was. If there are many photos, select them all in the sidebar first.
                """))
        },
        Moment(name: "11-confirm") { m in
            m.apply(.confirm(id: "q", question: "Send the email to Dr. Lee about moving Thursday's appointment?"))
        },
        Moment(name: "11b-confirm-always") { m in
            m.apply(.confirm(id: "q", question: "Replace 8 filled cells in “Budget”?", always: true))
        },
        Moment(name: "11c-confirm-always-long") { m in
            m.apply(.confirm(id: "q", question: "Run a script in Microsoft Excel? It's in my window.", always: true))
        },
        Moment(name: "11d-confirm-always-longest") { m in
            // As long as approvals.fit_bubble lets a question get: eight lines, and the third button under them.
            m.apply(.confirm(id: "q", question: "May I use Microsoft Excel for this? You'll see each step. I'll fill "
                + "in the November budget, add the totals row, make the header bold and add a chart next to the table "
                + "so the months are easy to compare with October and the year before… (all of it is in the Milo window)",
                always: true))
        },
        Moment(name: "11e-confirm-money") { m in
            // Buying asks in every mode, with Yes and No only, and says it is about money (ADR 23).
            m.apply(.confirm(id: "q", question: "I'm about to click “Buy Now” in Safari. Go ahead?", money: true))
        },
        Moment(name: "12-error") { m in
            m.show(MiloController.pasteBlocked, action: .permissions)
        },
        Moment(name: "12b-access-ask") { m in
            // The line just before macOS asks whether Milo may control Excel (ADR 25).
            m.apply(.access(AccessNote(need: .control, state: .ask,
                                       text: "macOS will ask once whether I may use Microsoft Excel. Click Allow.",
                                       app: AccessApp(name: "Microsoft Excel", bundle: "com.microsoft.Excel"))))
        },
        Moment(name: "12c-access-no") { m in
            m.apply(.access(AccessNote(need: .control, state: .no,
                                       text: "Okay, I won't use Microsoft Excel. If you change your mind, Fix it shows the switch.",
                                       app: AccessApp(name: "Microsoft Excel", bundle: "com.microsoft.Excel"))))
        },
        Moment(name: "12d-access-ui") { m in
            m.apply(.access(AccessNote(need: .ui, state: .no,
                                       text: "To work in other apps' windows I need Accessibility. Fix it shows where to switch it on.")))
        },
        Moment(name: "13-status") { m in
            m.apply(.state(.thinking))
            m.apply(.status("Looking at your calendar…"))
        },
        Moment(name: "14-pasted") { m in
            m.pasted("Thanks for the photos, they made my day.")
        },
        Moment(name: "15-helpers") { m in
            m.apply(.helpers(HelperRenderTests.three))
        },
        Moment(name: "16-looking") { m in
            m.apply(.looking(true))
            m.apply(.state(.thinking))
        },
        Moment(name: "17-offline") { m in
            m.connected = false
        },
        Moment(name: "20-meeting-ask") { m in
            m.apply(.confirm(id: "q", question: "Looks like a meeting. Should I take notes?", choices: [
                ConfirmChoice(id: "yes", label: "Take notes"), ConfirmChoice(id: "no", label: "Not this time"),
                ConfirmChoice(id: "always", label: "Always for Zoom"), ConfirmChoice(id: "never", label: "Never for Zoom"),
            ]))
        },
        Moment(name: "21-meeting-started") { m in
            m.recording = true
            m.apply(.bubble("Taking notes. Stop me any time with the button next to me."))
            m.apply(.meetingStatus(MeetingRenders.status(.recording, elapsed: 4)))
        },
        Moment(name: "22-meeting-recording") { m in
            m.recording = true
            m.apply(.meetingStatus(MeetingRenders.status(.recording, elapsed: 754)))
        },
        Moment(name: "23-meeting-paused") { m in
            m.recording = true
            m.apply(.meetingStatus(MeetingRenders.status(.paused, elapsed: 1322)))
        },
        Moment(name: "24-meeting-error") { m in
            m.recording = true
            var status = MeetingRenders.status(.recording, elapsed: 65)
            status.error = "I can hear you, but not the others in the call. Milo needs “Screen & System Audio Recording”."
            status.fix = .callAudio
            m.apply(.meetingStatus(status))
        },
        Moment(name: "25-meeting-writing") { m in
            m.apply(.meetingStatus(MeetingRenders.status(.writing, elapsed: 1934, step: "Writing the summary")))
        },
        Moment(name: "26-meeting-ready") { m in
            m.apply(.meetingStatus(MeetingRenders.status(.writing, elapsed: 1934, step: "Writing the summary")))
            m.apply(.meetingStatus(MeetingRenders.status(
                .done, elapsed: 1934, step: "Your notes from “Weekly sync” are ready. Two to-dos for you.")))
        },
        Moment(name: "27-meeting-while-working") { m in
            // Notes and work at once: the capsule in its row above Milo, Stop and the helper beside him, and an
            // Allow always question above both.
            m.recording = true
            m.apply(.meetingStatus(MeetingRenders.status(.recording, elapsed: 754)))
            m.apply(.helpers([HelperInfo(id: "t-excel", title: "Budget table in Excel", status: .working,
                                         step: "Typing “Monday” in Excel", progress: 0.4)]))
            m.apply(.state(.thinking))
            m.apply(.confirm(id: "q", question: "Replace 8 filled cells in “Budget”?", always: true))
        },
    ]

    @Test func renderEveryMoment() throws {
        _ = NSApplication.shared
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        for dark in [false, true] {
            for moment in Self.moments {
                let model = MiloModel(scheduler: ManualScheduler())
                model.connected = true
                moment.set(model)
                try render(model, name: "overlay-\(dark ? "dark" : "light")-\(moment.name)", dark: dark)
            }
        }
    }

    /// Frames of Milo leaving the screen and coming back (`Presence.Pose`), pinned on a clock of their own.
    @Test func renderLeavingAndComingBack() throws {
        _ = NSApplication.shared
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        final class Clock { var now: TimeInterval = 0 }
        for plain in [false, true] {
            let clock = Clock(), scheduler = ManualScheduler()
            let model = MiloModel(scheduler: scheduler, clock: { clock.now })
            model.connected = true
            model.presence.reduceMotion = { plain }
            let kind = plain ? "fade" : "fly"
            model.presence.dismiss()
            let leave = Presence.leaveDuration(plain: plain)
            for (i, f) in [0, 0.2, 0.4, 0.55, 0.7, 0.85, 1].enumerated() {
                clock.now = leave * f
                try render(model, name: "presence-\(kind)-1leave-\(i)", dark: false)
            }
            scheduler.advance(by: leave)
            clock.now = 10
            model.presence.summon()
            let arrive = Presence.arriveDuration(plain: plain)
            for (i, f) in [0, 0.15, 0.3, 0.45, 0.6, 0.75, 0.9].enumerated() {
                clock.now = 10 + arrive * f
                try render(model, name: "presence-\(kind)-2arrive-\(i)", dark: false)
            }
            scheduler.advance(by: arrive)
            try render(model, name: "presence-\(kind)-3here", dark: false)
            // Called back by a question: the bubble with its buttons is there at once, while he flies in.
            model.presence.dismiss()
            scheduler.advance(by: leave)
            clock.now = 20
            model.apply(.confirm(id: "q", question: "Send the email to Dr. Lee?"))
            scheduler.advance(by: 0)
            clock.now = 20 + arrive * 0.3
            try render(model, name: "presence-\(kind)-4question", dark: false)
        }
    }

    private func render(_ model: MiloModel, name: String, dark: Bool) throws {
        let size = OverlayPanel.size
        let view = ZStack {
            Wallpaper(dark: dark)
            OverlayView(model: model)
        }
        .frame(width: size.width, height: size.height)
        let host = NSHostingView(rootView: view)
        host.frame = NSRect(origin: .zero, size: size)
        let window = NSWindow(contentRect: host.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.appearance = NSAppearance(named: dark ? .darkAqua : .aqua)
        window.contentView = host
        host.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.35))
        let rep = try #require(host.bitmapImageRepForCachingDisplay(in: host.bounds))
        host.cacheDisplay(in: host.bounds, to: rep)
        let png = try #require(rep.representation(using: .png, properties: [:]))
        try png.write(to: dir.appendingPathComponent("\(name).png"))
    }
}

/// A meeting as the brain describes it, for renders.
enum MeetingRenders {
    static let id = "2026-10-29-1400-weekly-sync"

    static let lines: [MeetingLine] = [
        MeetingLine(at: 4, end: 9, who: "Anna", text: "Okay, let's start. Ben, how's the launch looking?"),
        MeetingLine(at: 11, end: 26, who: "Ben",
                    text: "Mostly fine. The app review came back with one question about the login screen, so Thursday is tight."),
        MeetingLine(at: 28, end: 33, who: "You", me: true, text: "Can we answer it today?"),
        MeetingLine(at: 34, end: 47, who: "Ben", text: "I think so, but then we'd still need a day for the store to approve it."),
        MeetingLine(at: 50, end: 58, who: "Anna", text: "Then let's move the launch to Friday. Better than rushing it."),
        MeetingLine(at: 60, end: 64, who: "You", me: true, text: "Agreed. I'll tell the customer."),
        MeetingLine(at: 66, end: 80, who: "Anna",
                    text: "Good. I'll send the slides around by Thursday so everyone sees the new date."),
        MeetingLine(at: 83, end: 95, who: "Ben", text: "And I'll answer the review question this afternoon."),
    ]

    static let markdown = """
        # Weekly sync

        Thursday 29 October 2026, 14:00–14:32 · Zoom · with Anna and Ben

        ## Summary

        The app review asked about the login screen, so the launch moves from Thursday to **Friday**. Ben answers \
        the review today; Anna sends the slides with the new date.

        ## Decisions

        - Launch on Friday instead of Thursday
        - Answer the review question today rather than changing the screen

        ## To-dos

        - [ ] You: Tell the customer about Friday (today)
        - [ ] Anna: Send the slides around (Thursday)
        - [ ] Ben: Answer the app review question

        ## Follow-up mail

        Hi all, thanks for today. The launch moves to Friday; Anna sends the slides by Thursday.

        [The whole transcript](transcript.md)
        """

    static var notes: MeetingNotes {
        MeetingNotes(id: id, title: "Weekly sync", started: Day.at(-19 * 3600), duration: 1920, markdown: markdown,
                     summary: "The app review asked about the login screen, so the launch moves from Thursday to Friday.",
                     decisions: ["Launch on Friday instead of Thursday"],
                     todos: [MeetingNotes.Todo(text: "Tell the customer about Friday", due: "today", mine: true),
                             MeetingNotes.Todo(text: "Send the slides around", owner: "Anna", due: "Thursday",
                                               added: false),
                             MeetingNotes.Todo(text: "Answer the app review question", owner: "Ben")],
                     followup: "Hi all, thanks for today.", people: ["Anna", "Ben"], app: "Zoom", conversation: "c-sync",
                     folder: "/Users/you/Milo/meetings/\(id)", reminders: true, mail: true)
    }

    static func status(_ phase: MeetingStatus.Phase, elapsed: Double, step: String = "") -> MeetingStatus {
        MeetingStatus(id: Self.id, phase: phase, title: "Weekly sync", app: "Zoom",
                      started: Day.at(-elapsed), elapsed: elapsed, conversation: "c-sync",
                      speakers: ["You", "Anna", "Ben"], step: step,
                      consent: "Milo is taking notes for me. They stay on my computer.")
    }
}
