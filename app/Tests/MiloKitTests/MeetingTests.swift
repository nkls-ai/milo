import Foundation
import Testing
@testable import MiloKit

final class FakeRecorder: MeetingRecorder {
    var onChunk: ((String, ChunkWriter.Finished) -> Void)?
    var onTracks: (([String], String) -> Void)?
    var tracks: [String] = []
    var paused = false
    private(set) var started: [URL] = []
    private(set) var pendingStop: (() -> Void)?

    func start(dir: URL) {
        started.append(dir)
        tracks = ["me", "them"]
        onTracks?(tracks, "")
    }

    func stop(done: @escaping () -> Void) { pendingStop = done }

    /// The recorder wrote its last chunks.
    func finishStop() {
        tracks = []
        pendingStop?()
        pendingStop = nil
    }

    func chunk(_ track: String, _ index: Int, seconds: Double = 30) {
        onChunk?(track, ChunkWriter.Finished(index: index, path: "/m/audio/\(track)-000\(index).wav",
                                             start: Double(index - 1) * 30, seconds: seconds))
    }
}

final class FakeCallSignals: CallSignals {
    var clients: [MicClient] = []
    var titles: [String: [String]] = [:]
    func micClients() -> [MicClient] { clients }
    func windowTitles(bundle: String) -> [String] { titles[bundle] ?? [] }
}

private final class Rig {
    let brain = FakeBrainClient()
    let recorder = FakeRecorder()
    let signals = FakeCallSignals()
    let scheduler = ManualScheduler()
    let hotkey = FakeHotkey()
    let model: MiloModel
    let meetings: MeetingController

    init() {
        model = MiloModel(scheduler: scheduler)
        meetings = MeetingController(model: model, brain: brain, recorder: recorder, signals: signals,
                                     scheduler: scheduler, pollInterval: 2, hotkey: hotkey)
        meetings.start()
    }

    func record(_ on: Bool, id: String = "m1") {
        #expect(meetings.apply(.meetingRecord(id: id, dir: "/m/audio", on: on)))
    }
}

@Suite struct MeetingControllerTests {
    @Test func recordsWhenTheBrainSaysSoAndReportsEveryChunk() {
        let rig = Rig()
        rig.record(true)
        #expect(rig.recorder.started == [URL(fileURLWithPath: "/m/audio", isDirectory: true)])
        #expect(rig.model.recording)
        rig.recorder.chunk("them", 1)
        rig.recorder.onTracks?(["me"], "I can only hear you.")
        #expect(rig.brain.sent == [
            .meetingRecording(id: "m1", on: true, tracks: ["me", "them"]),
            .meetingChunk(MeetingChunk(id: "m1", track: "them", index: 1, path: "/m/audio/them-0001.wav", start: 0,
                                       seconds: 30)),
            .meetingRecording(id: "m1", on: true, tracks: ["me"], error: "I can only hear you."),
        ])
    }

    @Test func stoppingSendsTheLastChunksThenSaysItStopped() {
        let rig = Rig()
        rig.record(true)
        rig.brain.clearSent()
        rig.record(false)
        #expect(!rig.model.recording)  // the dot goes at once
        rig.recorder.chunk("me", 2, seconds: 12)
        rig.recorder.finishStop()
        #expect(rig.brain.sent == [
            .meetingChunk(MeetingChunk(id: "m1", track: "me", index: 2, path: "/m/audio/me-0002.wav", start: 30,
                                       seconds: 12)),
            .meetingRecording(id: "m1", on: false, tracks: []),
        ])
        #expect(rig.meetings.meeting == nil)
    }

    @Test func aStopForAnotherMeetingIsIgnoredAndARepeatedStartOnlyReportsAgain() {
        let rig = Rig()
        rig.record(true)
        rig.record(false, id: "other")
        #expect(rig.model.recording && rig.recorder.pendingStop == nil)
        rig.brain.clearSent()
        rig.record(true)
        #expect(rig.recorder.started.count == 1)
        #expect(rig.brain.sent == [.meetingRecording(id: "m1", on: true, tracks: ["me", "them"])])
    }

    @Test func aNewBrainHearsWhatIsBeingRecorded() {
        let rig = Rig()
        rig.meetings.connectionChanged(false)
        rig.meetings.connectionChanged(true)
        #expect(rig.brain.sent == [.meetingRecording(id: "", on: false, tracks: [])])
        rig.record(true)
        rig.brain.clearSent()
        rig.meetings.connectionChanged(true)
        #expect(rig.brain.sent == [.meetingRecording(id: "m1", on: true, tracks: ["me", "them"])])
    }

    @Test func stopOnTheCapsuleEndsTheRecordingAtOnceAndTellsTheBrain() {
        let rig = Rig()
        rig.record(true)
        rig.brain.clearSent()
        rig.model.meeting.stop()
        #expect(rig.brain.sent == [.meetingToggle(false)])
        #expect(!rig.model.recording && rig.recorder.pendingStop != nil)
        rig.recorder.finishStop()
        #expect(rig.brain.sent.last == .meetingRecording(id: "m1", on: false, tracks: []))
    }

    @Test func pauseSilencesTheRecorderAndTellsTheBrainOncePerChange() {
        let rig = Rig()
        rig.model.meeting.pause(true)
        #expect(rig.brain.sent.isEmpty && !rig.recorder.paused)  // nothing records: nothing to pause
        rig.record(true)
        rig.brain.clearSent()
        rig.model.meeting.pause(true)
        rig.model.meeting.pause(true)
        #expect(rig.recorder.paused && rig.brain.sent == [.meetingPause(true)])
        rig.model.meeting.pause(false)
        #expect(!rig.recorder.paused && rig.brain.sent == [.meetingPause(true), .meetingPause(false)])
    }

    @Test func theMenuAsksTheBrainToStartButStopsAtOnce() {
        let rig = Rig()
        rig.meetings.toggle()
        #expect(rig.brain.sent == [.meetingToggle(true)] && rig.recorder.started.isEmpty)
        rig.record(true)
        rig.brain.clearSent()
        rig.meetings.toggle()
        #expect(!rig.model.recording && rig.recorder.pendingStop != nil)
        rig.recorder.finishStop()
        #expect(rig.brain.sent == [.meetingToggle(false), .meetingRecording(id: "m1", on: false, tracks: [])])
    }

    @Test func theShortcutTogglesNotesLikeTheMenu() {
        let rig = Rig()
        rig.meetings.setShortcut("ctrl+option+n")
        #expect(rig.hotkey.registered.last == KeyCombo("ctrl+option+n"))
        rig.hotkey.press()
        #expect(rig.brain.sent == [.meetingToggle(true)])
        rig.record(true)
        rig.brain.clearSent()
        rig.hotkey.press()
        #expect(rig.brain.sent.first == .meetingToggle(false) && !rig.model.recording)
        rig.meetings.setShortcut("")
        #expect(rig.hotkey.registered.last == .some(nil), "an empty shortcut turns it off")
    }

    @Test func recordingGoesOnWhileTheBrainRestartsButNotWithoutOneForLong() {
        let rig = Rig()
        rig.record(true)
        rig.meetings.connectionChanged(false)
        rig.scheduler.advance(by: 60)
        rig.meetings.connectionChanged(true)  // back: the same meeting goes on
        rig.scheduler.advance(by: 600)
        #expect(rig.model.recording && rig.recorder.pendingStop == nil)
        rig.meetings.connectionChanged(false)
        rig.scheduler.advance(by: 301)
        #expect(!rig.model.recording && rig.recorder.pendingStop != nil)
    }

    @Test func otherEventsAreNotTheMeetingsBusiness() {
        #expect(!Rig().meetings.apply(.looking(true)))
    }

    @Test func theMiloControllerPassesMeetingEventsAndTheConnectionOn() {
        let rig = Rig()
        let controller = MiloController(model: rig.model, brain: rig.brain, launcher: FakeBrainLauncher(),
                                        inserter: FakeTextInserter(), keys: FakeKeySource(),
                                        context: FakeContextProvider(), accessibility: FakeAccessibility(),
                                        scheduler: rig.scheduler, meetings: rig.meetings)
        controller.start()
        rig.brain.connect()
        #expect(rig.brain.sent.contains(.meetingRecording(id: "", on: false, tracks: [])))
        rig.brain.emit(.meetingRecord(id: "m1", dir: "/m/audio", on: true))
        #expect(rig.recorder.started.count == 1 && rig.model.recording && rig.model.bubble == nil)
    }

    @Test func aCallStartsAfterTwoPollsAndEndsAfterThreeWithout() {
        let rig = Rig()
        rig.signals.clients = [MicClient(bundle: "us.zoom.xos", pid: 42)]
        rig.scheduler.advance(by: 2)
        #expect(rig.brain.sent.isEmpty)
        rig.scheduler.advance(by: 2)
        #expect(rig.brain.sent == [.callStarted(app: "Zoom", bundle: "us.zoom.xos", title: "")])
        rig.signals.clients = []
        rig.scheduler.advance(by: 4)
        rig.signals.clients = [MicClient(bundle: "us.zoom.xos", pid: 42)]  // muted for a moment, then back
        rig.scheduler.advance(by: 2)
        rig.signals.clients = []
        rig.scheduler.advance(by: 6)
        #expect(rig.brain.sent == [.callStarted(app: "Zoom", bundle: "us.zoom.xos", title: ""), .callEnded(app: "Zoom")])
    }
}

@Suite struct CallAppsTests {
    private func call(_ bundle: String, titles: [String: [String]] = [:]) -> Call? {
        CallApps.call(for: MicClient(bundle: bundle, pid: 1)) { titles[$0] ?? [] }
    }

    @Test func callAppsUsingTheMicAreCalls() {
        #expect(call("us.zoom.xos")?.app == "Zoom")
        #expect(call("com.microsoft.teams2")?.app == "Microsoft Teams")
        #expect(call("com.microsoft.teams2.helper")?.app == "Microsoft Teams")
        #expect(call("com.apple.FaceTime")?.app == "FaceTime")
        #expect(call("com.tinyspeck.slackmacgap", titles: ["com.tinyspeck.slackmacgap": ["Huddle with Anna"]])
                == Call(app: "Slack", bundle: "com.tinyspeck.slackmacgap", title: "Huddle with Anna"))
        #expect(call("com.apple.Music") == nil)
        #expect(call("us.zoom.xosx") == nil)
        #expect(call("com.hnc.Discord")?.app == "Discord")
        #expect(call("com.hnc.Discord.helper")?.app == "Discord")
        #expect(call("com.hnc.DiscordPTB")?.app == "Discord")
        #expect(call("net.whatsapp.WhatsApp")?.app == "WhatsApp")
        #expect(call("org.whispersystems.signal-desktop")?.app == "Signal")
        #expect(call("ru.keepcoder.Telegram")?.app == "Telegram")
        #expect(call("com.skype.skype")?.app == "Skype")
    }

    @Test func aBrowserIsACallOnlyWithAMeetingTab() {
        let chrome = ["com.google.Chrome": ["Inbox - Gmail", "Meet - abc-defg-hij"]]
        #expect(call("com.google.Chrome.helper", titles: chrome)
                == Call(app: "Google Meet", bundle: "com.google.Chrome", title: "Meet - abc-defg-hij"))
        #expect(call("com.google.Chrome.helper", titles: ["com.google.Chrome": ["Dictation test"]]) == nil)
        let safari = ["com.apple.Safari": ["Weekly sync | Microsoft Teams"]]
        #expect(call("com.apple.WebKit.GPU", titles: safari)?.app == "Microsoft Teams")
        let discord = ["com.google.Chrome": ["#general | Gaming - Discord"]]
        #expect(call("com.google.Chrome.helper", titles: discord)?.app == "Discord")
    }

    @Test func oneCallPerApp() {
        let clients = [MicClient(bundle: "us.zoom.xos", pid: 1), MicClient(bundle: "us.zoom.xos", pid: 2),
                       MicClient(bundle: "com.apple.Music", pid: 3)]
        #expect(CallApps.calls(clients) { _ in [] } == [Call(app: "Zoom", bundle: "us.zoom.xos")])
    }

    @Test func aQuickMicCheckIsNoCall() {
        var detector = CallDetector(startAfter: 2, endAfter: 3)
        let zoom = Call(app: "Zoom", bundle: "us.zoom.xos")
        #expect(detector.update([zoom]).isEmpty)
        #expect(detector.update([]).isEmpty)
        #expect(detector.update([zoom]).isEmpty)
        #expect(detector.update([zoom]) == [.started(zoom)])
        #expect(detector.current == zoom)
    }
}

@Suite struct ChunkWriterTests {
    private func folder() throws -> URL {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("milo-chunks-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        return url
    }

    private func samples(_ url: URL) throws -> [Int16] {
        let data = try Data(contentsOf: url)
        return data.dropFirst(44).withUnsafeBytes { Array($0.bindMemory(to: Int16.self)) }
    }

    @Test func writesFullChunksWithRightHeadersAndReportsEach() throws {
        let dir = try folder()
        let writer = ChunkWriter(dir: dir, track: "me", sampleRate: 100, chunkSeconds: 1)
        var done: [ChunkWriter.Finished] = []
        writer.onChunk = { done.append($0) }
        try writer.append([Float](repeating: 0.5, count: 250))
        #expect(done.map(\.index) == [1, 2])
        try writer.finish()
        #expect(done == [
            .init(index: 1, path: dir.appendingPathComponent("me-0001.wav").path, start: 0, seconds: 1),
            .init(index: 2, path: dir.appendingPathComponent("me-0002.wav").path, start: 1, seconds: 1),
            .init(index: 3, path: dir.appendingPathComponent("me-0003.wav").path, start: 2, seconds: 0.5),
        ])
        let last = try Data(contentsOf: dir.appendingPathComponent("me-0003.wav"))
        #expect(last.count == 44 + 100)
        #expect(last.prefix(4) == Data("RIFF".utf8))
        #expect(last[40..<44].withUnsafeBytes { $0.loadUnaligned(as: UInt32.self) } == 100)
        #expect(try samples(dir.appendingPathComponent("me-0001.wav")).allSatisfy { $0 == 16383 })
    }

    @Test func aGapInTheAudioBecomesSilenceSoTimesStayRight() throws {
        let dir = try folder()
        let writer = ChunkWriter(dir: dir, track: "them", sampleRate: 100, chunkSeconds: 10)
        try writer.append([Float](repeating: 1, count: 100), at: 0)
        try writer.append([Float](repeating: 1, count: 100), at: 1.1)  // jitter: no gap
        try writer.append([Float](repeating: -1, count: 50), at: 3.0)  // a second lost
        try writer.finish()
        let all = try samples(dir.appendingPathComponent("them-0001.wav"))
        #expect(all.count == 350)
        #expect(all[0..<200].allSatisfy { $0 == 32767 })
        #expect(all[200..<300].allSatisfy { $0 == 0 })
        #expect(all[300...].allSatisfy { $0 == -32767 })
        #expect(writer.position == 350)
    }

    @Test func aChunkTheAppNeverClosedStillHasItsSamples() throws {
        let dir = try folder()
        let writer = ChunkWriter(dir: dir, track: "me", sampleRate: 100, chunkSeconds: 10)
        try writer.append([Float](repeating: 0.25, count: 120))
        // The app dies here: no finish(). The header still says 0 bytes, but the samples are in the file.
        let url = dir.appendingPathComponent("me-0001.wav")
        #expect(try Data(contentsOf: url).count == 44 + 240)
        let mode = try FileManager.default.attributesOfItem(atPath: url.path)[.posixPermissions] as? Int
        #expect(mode == 0o600)
    }
}
