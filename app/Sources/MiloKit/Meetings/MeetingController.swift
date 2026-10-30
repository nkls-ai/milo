import Foundation

/// The app's half of meeting notes (docs/design/meetings.md): it notices calls, records when the brain says so,
/// and tells the brain about every chunk on disk. The brain decides when to record and does everything else.
/// Knows no concrete adapter; main.swift hands them in.
public final class MeetingController {
    private let model: MiloModel
    private let brain: BrainClient
    private let recorder: MeetingRecorder
    private let signals: CallSignals?
    private let hotkey: HotkeySource?
    private let scheduler: Scheduler
    private let pollInterval: TimeInterval
    private let brainGrace: TimeInterval
    private var detector: CallDetector
    private var poller: ScheduledTask?
    private var brainGone: ScheduledTask?
    /// The meeting being recorded, until the recorder has written its last chunk.
    public private(set) var meeting: String?
    private var stopping = false

    public init(model: MiloModel, brain: BrainClient, recorder: MeetingRecorder, signals: CallSignals?,
                scheduler: Scheduler, pollInterval: TimeInterval = 2.5, brainGrace: TimeInterval = 300,
                detector: CallDetector = CallDetector(), hotkey: HotkeySource? = nil) {
        self.model = model
        self.brain = brain
        self.recorder = recorder
        self.signals = signals
        self.hotkey = hotkey
        self.scheduler = scheduler
        self.pollInterval = pollInterval
        self.brainGrace = brainGrace
        self.detector = detector
    }

    public func start() {
        hotkey?.onPress = { [weak self] in self?.toggle() }
        recorder.onChunk = { [weak self] track, chunk in
            guard let self, let id = meeting else { return }
            brain.send(.meetingChunk(MeetingChunk(id: id, track: track, index: chunk.index, path: chunk.path,
                                                  start: chunk.start, seconds: chunk.seconds)))
        }
        recorder.onTracks = { [weak self] tracks, error in
            guard let self, let id = meeting, !stopping else { return }
            brain.send(.meetingRecording(id: id, on: true, tracks: tracks, error: error))
        }
        if signals != nil {
            poller = scheduler.every(pollInterval) { [weak self] in self?.poll() }
        }
    }

    /// Handles `meeting_record`; false for every other event.
    public func apply(_ event: BrainEvent) -> Bool {
        guard case let .meetingRecord(id, dir, on) = event else { return false }
        if on {
            begin(id: id, dir: dir)
        } else if let current = meeting, current == id || id.isEmpty {
            end()
        }
        return true
    }

    /// Tells a new brain what is being recorded, so it goes on with that meeting, or finishes one it was taking
    /// notes in when it stopped. Recording goes on while the brain restarts, so no minute is lost, but not for
    /// longer than `brainGrace` without one.
    public func connectionChanged(_ up: Bool) {
        brainGone?.cancel()
        brainGone = nil
        guard up else {
            if meeting != nil {
                brainGone = scheduler.after(brainGrace) { [weak self] in
                    NSLog("Milo: no brain for the meeting; stopping the recording")
                    self?.end()
                }
            }
            return
        }
        if let meeting, !stopping {
            brain.send(.meetingRecording(id: meeting, on: true, tracks: recorder.tracks))
        } else {
            brain.send(.meetingRecording(id: "", on: false, tracks: []))
        }
    }

    /// The shortcut from `ui_config` (`[ui] meeting_key`), for calls Milo doesn't notice himself. "" turns it off;
    /// unknown text leaves it off.
    public func setShortcut(_ text: String) {
        let combo = KeyCombo(text)
        if !text.isEmpty && combo == nil { NSLog("Milo: ignoring meeting_key %@", text) }
        if hotkey?.register(combo) == false, let combo {
            NSLog("Milo: macOS refused the meeting notes shortcut %@", combo.displayName)
        }
    }

    /// "Take meeting notes" or "Stop taking notes" in the menu. Starting is the brain's to decide (it answers with
    /// `meeting_record`); stopping happens here at once, brain or not.
    public func toggle() {
        let stop = model.recording
        brain.send(.meetingToggle(!stop))
        if stop { end() }
    }

    private func begin(id: String, dir: String) {
        if meeting == id && !stopping {
            brain.send(.meetingRecording(id: id, on: true, tracks: recorder.tracks))
            return
        }
        guard meeting == nil else {
            NSLog("Milo: asked to record meeting \(id) while \(meeting ?? "") still records; ignored")
            return
        }
        meeting = id
        stopping = false
        model.recording = true
        recorder.start(dir: URL(fileURLWithPath: dir, isDirectory: true))
    }

    private func end() {
        guard let id = meeting, !stopping else { return }
        stopping = true
        model.recording = false
        recorder.stop { [weak self] in
            guard let self else { return }
            meeting = nil
            stopping = false
            brain.send(.meetingRecording(id: id, on: false, tracks: []))
        }
    }

    private func poll() {
        guard let signals else { return }
        let calls = CallApps.calls(signals.micClients(), titles: signals.windowTitles(bundle:))
        for change in detector.update(calls) {
            switch change {
            case let .started(call): brain.send(.callStarted(app: call.app, bundle: call.bundle, title: call.title))
            case let .ended(call): brain.send(.callEnded(app: call.app))
            }
        }
    }
}
