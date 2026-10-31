import CoreGraphics
import Foundation
import Testing
@testable import MiloKit

/// Milo leaves the screen after a while with nothing going on, and anything that needs him brings him back.
@Suite struct PresenceTests {
    let scheduler = ManualScheduler()
    let model: MiloModel
    var presence: Presence { model.presence }

    init() {
        let scheduler = scheduler
        model = MiloModel(scheduler: scheduler, clock: { scheduler.now })
        model.connected = true
        model.presence.hideAfter = 60  // the times below count a minute; the default is shorter
    }

    /// Lets the model's change reach the presence (it looks a moment later, once the change is in).
    func settle() { scheduler.advance(by: 0) }

    func away() {
        scheduler.advance(by: 60 + Presence.leaveDuration(plain: false))
        #expect(presence.phase == .away)
    }

    @Test func leavesAfterAMinuteWithNothingGoingOn() {
        scheduler.advance(by: 59.9)
        #expect(presence.phase == .here)
        scheduler.advance(by: 0.1)
        #expect(presence.phase == .leaving(since: 60, plain: false))
        scheduler.advance(by: Presence.leaveDuration(plain: false))
        #expect(presence.phase == .away)
    }

    @Test func reduceMotionFadesInsteadOfFlying() {
        model.presence.reduceMotion = { true }
        scheduler.advance(by: 60)
        #expect(presence.phase == .leaving(since: 60, plain: true))
        let pose = presence.pose(at: 60 + Presence.leaveDuration(plain: true) / 2)
        #expect(pose.offset == .zero && pose.heading == nil && pose.opacity > 0.3 && pose.opacity < 0.7)
        scheduler.advance(by: Presence.leaveDuration(plain: true))
        #expect(presence.phase == .away)
    }

    @Test func neverLeavesWhileSomethingNeedsHim() {
        let needs: [(String, (MiloModel) -> Void)] = [
            ("listening", { $0.apply(.state(.listening)) }),
            ("dictating", { $0.apply(.state(.dictating)) }),
            ("thinking", { $0.apply(.state(.thinking)) }),
            ("speaking", { $0.apply(.state(.speaking)) }),
            ("transcribing", { $0.apply(.state(.transcribing)) }),
            ("key down", { $0.press(.dictate) }),
            ("hands-free", { $0.handsFree = .talk }),
            ("question", { $0.apply(.confirm(id: "q", question: "Send it?")) }),
            ("helper", { $0.apply(.helpers([HelperInfo(id: "h", title: "Excel", status: .working)])) }),
            ("helper needs you", { $0.apply(.helpers([HelperInfo(id: "h", title: "Excel", status: .needsYou)])) }),
            ("hands", { $0.handsActive = true }),
            ("borrowed", { $0.handsBorrowed = true }),
            ("looking", { $0.looking = true }),
            ("recording", { $0.recording = true }),
            ("meeting", { $0.apply(.meetingStatus(MeetingStatus(id: "m", phase: .recording, title: "Sync"))) }),
            ("writing notes", { $0.apply(.meetingStatus(MeetingStatus(id: "m", phase: .writing, title: "Sync"))) }),
            ("working window", { $0.workingWindow = CGRect(x: 0, y: 0, width: 400, height: 300) }),
            ("fly target", { $0.flyTarget = CGPoint(x: 300, y: 300) }),
            ("in the air", { $0.flight = .flying(heading: CGVector(dx: 1, dy: 0)) }),
        ]
        for (name, need) in needs {
            let scheduler = ManualScheduler()
            let model = MiloModel(scheduler: scheduler, clock: { scheduler.now })
            model.connected = true
            need(model)
            scheduler.advance(by: 0)
            #expect(Presence.needs(model), "\(name)")
            scheduler.advance(by: 3600)
            #expect(model.presence.phase == .here, "\(name)")
        }
    }

    @Test func aBubbleKeepsHimUntilItIsGoneAndThenTheMinuteStarts() {
        scheduler.advance(by: 50)
        model.apply(.bubble("Your dentist is at four."))
        settle()
        let shown = MiloModel.bubbleDuration(for: "Your dentist is at four.")
        scheduler.advance(by: shown)
        #expect(model.bubble == nil)
        scheduler.advance(by: 59.9)
        #expect(presence.phase == .here, "the minute starts when the bubble goes")
        scheduler.advance(by: 0.1)
        #expect(presence.phase == .leaving(since: 50 + shown + 60, plain: false))
    }

    @Test func thingsThatNeedNoOneDoNotResetTheMinute() {
        scheduler.advance(by: 40)
        model.apply(.emotion(.happy))
        model.drowsy = true
        model.connected = false
        settle()
        scheduler.advance(by: 20)
        #expect(presence.phase == .leaving(since: 60, plain: false))
    }

    @Test func theDictateKeyBringsHimBack() {
        away()
        model.press(.dictate)
        settle()
        #expect(presence.phase == .arriving(since: scheduler.now, plain: false))
        scheduler.advance(by: Presence.arriveDuration(plain: false))
        #expect(presence.phase == .here)
    }

    @Test func aTapThatTurnsOutToBeNothingStillBringsHimBackAndRestartsTheMinute() {
        away()
        model.press(.talk)
        model.cancelPress()
        settle()
        let back = scheduler.now
        #expect(presence.phase == .arriving(since: back, plain: false))
        scheduler.advance(by: 59.9)
        #expect(presence.phase == .here)
        scheduler.advance(by: 0.1)
        #expect(presence.phase == .leaving(since: back + 60, plain: false))
    }

    @Test func aQuestionBringsHimBackAndKeepsHimForAsLongAsItWaits() {
        away()
        model.apply(.confirm(id: "q", question: "Buy it?", money: true))
        settle()
        #expect(presence.phase == .arriving(since: scheduler.now, plain: false))
        scheduler.advance(by: 3600)
        #expect(presence.phase == .here && model.question != nil)
    }

    @Test func everythingThatNeedsHimBringsHimBack() {
        let needs: [(String, (MiloModel) -> Void)] = [
            ("speaks", { $0.apply(.state(.speaking)) }),
            ("a bubble, a nudge, a reminder", { $0.apply(.bubble("Time for the dentist.")) }),
            ("status", { $0.apply(.status("Looking at your calendar…")) }),
            ("question", { $0.apply(.confirm(id: "q", question: "Send it?")) }),
            ("helper needs you", { $0.apply(.helpers([HelperInfo(id: "h", title: "Excel", status: .needsYou)])) }),
            ("hands", { $0.handsActive = true }),
            ("meeting", { $0.recording = true }),
            ("talk key", { $0.press(.talk) }),
        ]
        for (name, need) in needs {
            let scheduler = ManualScheduler()
            let model = MiloModel(scheduler: scheduler, clock: { scheduler.now })
            model.connected = true
            scheduler.advance(by: 61)
            scheduler.advance(by: Presence.leaveDuration(plain: false))
            #expect(model.presence.phase == .away, "\(name)")
            need(model)
            scheduler.advance(by: 0)
            #expect(model.presence.phase == .arriving(since: scheduler.now, plain: false), "\(name)")
        }
    }

    @Test func comingBackHalfWayOffTurnsAroundWhereHeIs() {
        scheduler.advance(by: 60)
        let crouch = Presence.crouch, flight = Presence.leaveDuration(plain: false) - Presence.crouch
        scheduler.advance(by: crouch + flight * 0.3)
        let there = presence.pose(at: scheduler.now)
        model.press(.talk)
        settle()
        guard case let .arriving(since, _) = presence.phase else { return #expect(Bool(false), "not arriving") }
        let back = presence.pose(at: scheduler.now)
        #expect(abs(back.offset.width - there.offset.width) < 0.01 && abs(back.offset.height - there.offset.height) < 0.01)
        #expect(scheduler.now - since > 0, "part of the way back is already done")
        scheduler.advance(by: Presence.arriveDuration(plain: false))
        #expect(presence.phase == .here)
    }

    @Test func theWayOffStartsAtHisPerchAndEndsOffTheBottomRightEdge() {
        let start = Presence.Pose.leaving(0, plain: false)
        #expect(start.offset == .zero && start.opacity == 1)
        #expect(start.heading != nil, "he crouches with his wings ready, so the wren plays his takeoff")
        let gone = Presence.Pose.leaving(Presence.leaveDuration(plain: false), plain: false)
        #expect(gone.offset.width > 80 && gone.offset.height > 140 && gone.opacity == 0)
        let back = Presence.Pose.arriving(Presence.arriveDuration(plain: false), plain: false)
        #expect(back.offset == .zero && back.opacity == 1)
        let swooping = Presence.Pose.arriving(Presence.arriveDuration(plain: false) * 0.5, plain: false)
        let heading = try! #require(swooping.heading)
        #expect(heading.dx < 0, "he flies in from the right")
        // a hop above his perch on the way: on the way back he swoops up past it and settles down onto it
        let lowest = stride(from: 0.0, through: 1.0, by: 0.01)
            .map { Presence.Pose.arriving(Presence.arriveDuration(plain: false) * $0, plain: false).offset.height }.min()!
        #expect(lowest < -20 && lowest > -40)
    }

    @Test func neverMeansHeStays() {
        presence.hideAfter = nil
        scheduler.advance(by: 3600)
        #expect(presence.phase == .here)
    }

    @Test func choosingNeverWhileHeIsAwayBringsHimBack() {
        away()
        presence.hideAfter = nil
        #expect(presence.phase == .arriving(since: scheduler.now, plain: false))
    }

    @Test func aNewTimeAppliesAtOnceAndCountsFromTheChange() {
        scheduler.advance(by: 20)
        presence.hideAfter = 30
        scheduler.advance(by: 29.9)
        #expect(presence.phase == .here)
        scheduler.advance(by: 0.1)
        #expect(presence.phase == .leaving(since: 50, plain: false))
    }

    @Test func notWhileTheUserDragsHim() {
        scheduler.advance(by: 30)
        presence.held = true
        scheduler.advance(by: 600)
        #expect(presence.phase == .here)
        presence.held = false
        scheduler.advance(by: 59.9)
        #expect(presence.phase == .here)
        scheduler.advance(by: 0.1)
        #expect(presence.phase == .leaving(since: 690, plain: false))
    }

    @Test func notWhileThePointerRestsOnHim() {
        var on = true
        presence.pointing = { on }
        scheduler.advance(by: 60 + Presence.pointerWait * 3)
        #expect(presence.phase == .here)
        on = false
        scheduler.advance(by: Presence.pointerWait)
        #expect(presence.phase == .leaving(since: 60 + Presence.pointerWait * 4, plain: false))
    }

    @Test func theMenuBarBringsHimBackAndRestartsTheMinute() {
        away()
        presence.summon()
        let back = scheduler.now
        #expect(presence.phase == .arriving(since: back, plain: false))
        scheduler.advance(by: 30)
        presence.summon()
        scheduler.advance(by: 59.9)
        #expect(presence.phase == .here)
        scheduler.advance(by: 0.1)
        #expect(presence.phase == .leaving(since: back + 90, plain: false))
    }

    @Test func hideMiloSendsHimOffNowButNotWhileHeIsNeeded() {
        model.apply(.confirm(id: "q", question: "Send it?"))
        settle()
        presence.dismiss()
        #expect(presence.phase == .here)
        model.answer(true)
        settle()
        presence.dismiss()
        #expect(presence.phase == .leaving(since: scheduler.now, plain: false))
    }

    @Test func clickingHimWhileHeLeavesBringsHimBack() {
        scheduler.advance(by: 60.2)
        presence.summon()
        guard case .arriving = presence.phase else { return #expect(Bool(false), "not arriving") }
    }
}

@Suite struct HideChoicesTests {
    static let setting = Setting(section: "ui", key: "hide_after_s", value: 60, options: [30, 60, 300, 0],
                                 labels: ["After 30 seconds", "After a minute", "After 5 minutes", "Never"])

    @Test func theFourChoicesInPlainWords() {
        #expect(SettingsView.hideChoices(Self.setting).map(\.label)
            == ["After 30 seconds", "After a minute", "After 5 minutes", "Never"])
    }

    @Test func aTimeSetByHandShowsFirstInWords() {
        var setting = Self.setting
        setting.value = 120
        #expect(SettingsView.hideChoices(setting).first?.label == "After 2 minutes")
        setting.value = 45
        #expect(SettingsView.hideChoices(setting).first?.label == "After 45 seconds")
    }
}
