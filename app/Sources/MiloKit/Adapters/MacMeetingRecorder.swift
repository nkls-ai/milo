import AVFoundation
import CoreAudio
import ScreenCaptureKit

/// Records a meeting: the microphone through AVAudioEngine, the call through a Core Audio process tap of
/// everything the Mac plays except Milo (macOS 14.4+, permission "System Audio Recording"), or through
/// ScreenCaptureKit when there is no tap (permission "Screen Recording"). Both tracks go to disk as 30 s chunks
/// first (ChunkWriter), then the brain hears about them.
///
/// macOS has no way to ask whether the tap is allowed: without the permission it delivers silence. So a call
/// track that stays digitally silent for `silentAfter` seconds is reported as missing, and comes back as soon as
/// there is sound.
public final class MacMeetingRecorder: MeetingRecorder {
    public var onChunk: ((String, ChunkWriter.Finished) -> Void)?
    public var onTracks: (([String], String) -> Void)?
    public private(set) var tracks: [String] = []

    static let noMic = "I can't use the microphone for the notes. Turn it on for Milo in System Settings › Privacy & Security › Microphone."
    static let noCall = "I can only hear you, not the others. Turn on System Audio Recording for Milo in System Settings › Privacy & Security."
    static let silentCall = "I don't hear the others in the call. If they're talking, turn on System Audio Recording for Milo in System Settings › Privacy & Security."

    private let brainLock: URL?
    private let silentAfter: TimeInterval
    private let queue = DispatchQueue(label: "milo.meeting.writer")
    // On `queue`:
    private var writers: [String: ChunkWriter] = [:]
    private var lastSound: TimeInterval = 0
    private var muted = false
    // On the main queue:
    private var startHost: UInt64 = 0
    private var mic: MicCapture?
    private var call: CallCapture?
    private var callError = ""
    private var silent = false
    private var watchdog: Timer?

    /// `brainLock` holds the brain's pid, whose voice stays out of the call track.
    public init(brainLock: URL?, silentAfter: TimeInterval = 45) {
        self.brainLock = brainLock
        self.silentAfter = silentAfter
    }

    public var paused: Bool {
        get { queue.sync { muted } }
        set { queue.async { [weak self] in self?.muted = newValue } }
    }

    public func start(dir: URL) {
        stopCaptures()
        startHost = mach_absolute_time()
        silent = false
        callError = ""
        queue.sync {
            lastSound = 0
            writers = [:]
            for track in ["me", "them"] {
                let writer = ChunkWriter(dir: dir, track: track)
                writer.onChunk = { [weak self] chunk in
                    DispatchQueue.main.async { self?.onChunk?(track, chunk) }
                }
                writers[track] = writer
            }
        }
        let mic = MicCapture { [weak self] samples, host in self?.write("me", samples, host: host) }
        do {
            try mic.start()
            self.mic = mic
        } catch {
            NSLog("Milo: no microphone for the meeting: \(error)")
        }
        startCall()
        watchdog = Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { [weak self] _ in self?.check() }
        report()
    }

    public func stop(done: @escaping () -> Void) {
        stopCaptures()
        queue.async { [weak self] in
            guard let self else { return DispatchQueue.main.async(execute: done) }
            for writer in writers.values {
                do { try writer.finish() } catch { NSLog("Milo: closing a meeting chunk failed: \(error)") }
            }
            writers = [:]
            DispatchQueue.main.async {
                self.tracks = []
                done()
            }
        }
    }

    private func stopCaptures() {
        watchdog?.invalidate()
        watchdog = nil
        mic?.stop()
        mic = nil
        call?.stop()
        call = nil
    }

    private func startCall() {
        let excluded = excludedPIDs()
        // Taps exist since 14.2, but asking for the permission works from 14.4.
        if #available(macOS 14.4, *) {
            let tap = ProcessTapCapture(excluding: excluded) { [weak self] samples, host in
                self?.write("them", samples, host: host)
            }
            do {
                try tap.start()
                call = tap
                return
            } catch {
                NSLog("Milo: no process tap for the meeting (\(error)); trying ScreenCaptureKit")
            }
        }
        let stream = ScreenAudioCapture(excluding: excluded) { [weak self] samples, host in
            self?.write("them", samples, host: host)
        } failed: { [weak self] error in
            NSLog("Milo: no call audio for the meeting: \(error)")
            guard let self else { return }
            call = nil
            callError = Self.noCall
            report()
        }
        stream.start()
        call = stream
    }

    /// Milo itself and its brain, which speaks through the same speakers.
    private func excludedPIDs() -> [pid_t] {
        var pids = [ProcessInfo.processInfo.processIdentifier]
        if let lock = brainLock, let text = try? String(contentsOf: lock, encoding: .utf8),
           let pid = pid_t(text.split(whereSeparator: \.isNewline).first.map(String.init) ?? "") {
            pids.append(pid)
        }
        return pids
    }

    /// Called from the capture threads.
    private func write(_ track: String, _ samples: [Float], host: UInt64) {
        let time = AVAudioTime.seconds(forHostTime: host) - AVAudioTime.seconds(forHostTime: startHost)
        queue.async { [weak self] in
            guard let self, let writer = writers[track] else { return }
            // Paused: silence keeps the times right, and a quiet call while paused is no reason to worry.
            if track == "them", muted || samples.contains(where: { $0 != 0 }) { lastSound = max(time, 0.001) }
            let kept = muted ? [Float](repeating: 0, count: samples.count) : samples
            do { try writer.append(kept, at: max(0, time)) } catch { NSLog("Milo: writing the meeting failed: \(error)") }
        }
    }

    private func check() {
        if let tap = call as? ProcessTapCapture14 {
            if tap.outputChanged {
                // A tap follows the output device it was made on: make a new one for headphones plugged in.
                NSLog("Milo: the output device changed; a new tap for the meeting")
                call?.stop()
                call = nil
                startCall()
            } else {
                tap.refresh(excluding: excludedPIDs())
            }
        }
        guard call != nil else { return }
        let now = AVAudioTime.seconds(forHostTime: mach_absolute_time()) - AVAudioTime.seconds(forHostTime: startHost)
        let heard = queue.sync { lastSound }
        let quiet = now - heard > silentAfter
        if quiet != silent {
            silent = quiet
            report()
        }
    }

    private func report() {
        var tracks: [String] = []
        var errors: [String] = []
        if mic != nil { tracks.append("me") } else { errors.append(Self.noMic) }
        if call != nil && !silent {
            tracks.append("them")
        } else {
            errors.append(call != nil ? Self.silentCall : (callError.isEmpty ? Self.noCall : callError))
        }
        self.tracks = tracks
        onTracks?(tracks, errors.joined(separator: " "))
    }
}

private protocol CallCapture: AnyObject {
    func stop()
}

/// Lets `check()` reach the tap without an availability check at every use.
private protocol ProcessTapCapture14: AnyObject {
    var outputChanged: Bool { get }
    func refresh(excluding pids: [pid_t])
}

/// Converts any PCM buffer to 16 kHz mono float samples.
private final class Resampler {
    static let target = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: 16_000, channels: 1,
                                      interleaved: false)!
    private let converter: AVAudioConverter
    private let ratio: Double

    init?(from format: AVAudioFormat) {
        guard let converter = AVAudioConverter(from: format, to: Self.target) else { return nil }
        converter.downmix = true
        self.converter = converter
        ratio = Self.target.sampleRate / format.sampleRate
    }

    func convert(_ buffer: AVAudioPCMBuffer) -> [Float] {
        let capacity = AVAudioFrameCount(Double(buffer.frameLength) * ratio) + 64
        guard buffer.frameLength > 0, let out = AVAudioPCMBuffer(pcmFormat: Self.target, frameCapacity: capacity) else {
            return []
        }
        var given = false
        var error: NSError?
        converter.convert(to: out, error: &error) { _, status in
            if given {
                status.pointee = .noDataNow
                return nil
            }
            given = true
            status.pointee = .haveData
            return buffer
        }
        guard error == nil, let data = out.floatChannelData else { return [] }
        return Array(UnsafeBufferPointer(start: data[0], count: Int(out.frameLength)))
    }
}

/// The microphone through AVAudioEngine; restarts itself when the input device changes.
private final class MicCapture {
    private let engine = AVAudioEngine()
    private let sink: ([Float], UInt64) -> Void
    private var observer: NSObjectProtocol?

    init(sink: @escaping ([Float], UInt64) -> Void) {
        self.sink = sink
    }

    func start() throws {
        guard AVCaptureDevice.authorizationStatus(for: .audio) == .authorized else {
            throw NSError(domain: "Milo", code: 1, userInfo: [NSLocalizedDescriptionKey: "microphone not allowed"])
        }
        try begin()
        observer = NotificationCenter.default.addObserver(forName: .AVAudioEngineConfigurationChange, object: engine,
                                                          queue: .main) { [weak self] _ in
            guard let self else { return }
            engine.inputNode.removeTap(onBus: 0)
            do { try begin() } catch { NSLog("Milo: the microphone for the meeting didn't come back: \(error)") }
        }
    }

    private func begin() throws {
        let input = engine.inputNode
        let format = input.outputFormat(forBus: 0)
        guard format.sampleRate > 0, let resampler = Resampler(from: format) else {
            throw NSError(domain: "Milo", code: 2, userInfo: [NSLocalizedDescriptionKey: "no input device"])
        }
        let sink = self.sink
        input.installTap(onBus: 0, bufferSize: 4096, format: format) { buffer, when in
            let host = when.isHostTimeValid ? when.hostTime : mach_absolute_time()
            sink(resampler.convert(buffer), host)
        }
        engine.prepare()
        try engine.start()
    }

    func stop() {
        if let observer { NotificationCenter.default.removeObserver(observer) }
        observer = nil
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
    }
}

/// Everything the Mac plays except the excluded processes, through a Core Audio process tap on a private
/// aggregate device (the approach of AudioCap, BSD-2, and Apple's "Capturing system audio with Core Audio taps").
@available(macOS 14.2, *)
private final class ProcessTapCapture: CallCapture, ProcessTapCapture14 {
    private let sink: ([Float], UInt64) -> Void
    private var excludedPIDs: Set<pid_t>
    private var description: CATapDescription
    private var tap = AudioObjectID(kAudioObjectUnknown)
    private var device = AudioObjectID(kAudioObjectUnknown)
    private var proc: AudioDeviceIOProcID?
    private var output: String?
    private let queue = DispatchQueue(label: "milo.meeting.tap", qos: .userInitiated)

    var outputChanged: Bool { output != nil && CoreAudio.defaultOutputUID != output }

    init(excluding pids: [pid_t], sink: @escaping ([Float], UInt64) -> Void) {
        self.sink = sink
        excludedPIDs = Set(pids.filter { CoreAudio.process(pid: $0) != nil })
        description = CATapDescription(stereoGlobalTapButExcludeProcesses: pids.compactMap { CoreAudio.process(pid: $0) })
        description.uuid = UUID()
        description.name = "Milo meeting notes"
        description.isPrivate = true
        description.muteBehavior = .unmuted
    }

    func start() throws {
        try check(AudioHardwareCreateProcessTap(description, &tap), "create the tap")
        guard let output = CoreAudio.defaultOutputUID else { stop(); throw Self.error("no output device") }
        self.output = output
        let aggregate: [String: Any] = [
            kAudioAggregateDeviceNameKey: "Milo meeting notes",
            kAudioAggregateDeviceUIDKey: UUID().uuidString,
            kAudioAggregateDeviceMainSubDeviceKey: output,
            kAudioAggregateDeviceIsPrivateKey: true,
            kAudioAggregateDeviceIsStackedKey: false,
            kAudioAggregateDeviceTapAutoStartKey: true,
            kAudioAggregateDeviceSubDeviceListKey: [[kAudioSubDeviceUIDKey: output]],
            kAudioAggregateDeviceTapListKey: [[kAudioSubTapDriftCompensationKey: true,
                                               kAudioSubTapUIDKey: description.uuid.uuidString]],
        ]
        do {
            try check(AudioHardwareCreateAggregateDevice(aggregate as CFDictionary, &device), "create the device")
            var asbd = CoreAudio.value(tap, kAudioTapPropertyFormat, default: AudioStreamBasicDescription())
            guard let format = AVAudioFormat(streamDescription: &asbd), let resampler = Resampler(from: format) else {
                throw Self.error("the tap has no usable format")
            }
            let sink = self.sink
            try check(AudioDeviceCreateIOProcIDWithBlock(&proc, device, queue) { _, input, inputTime, _, _ in
                guard let buffer = AVAudioPCMBuffer(pcmFormat: format, bufferListNoCopy: input, deallocator: nil) else {
                    return
                }
                let time = inputTime.pointee
                let host = time.mFlags.contains(.hostTimeValid) ? time.mHostTime : mach_absolute_time()
                sink(resampler.convert(buffer), host)
            }, "add the reader")
            try check(AudioDeviceStart(device, proc), "start")
        } catch {
            stop()
            throw error
        }
    }

    /// The brain may start using audio after the tap began; leave it out from then on.
    func refresh(excluding pids: [pid_t]) {
        guard tap != kAudioObjectUnknown else { return }
        let found = pids.filter { CoreAudio.process(pid: $0) != nil }
        guard !Set(found).isSubset(of: excludedPIDs) else { return }
        excludedPIDs.formUnion(found)
        description.processes = found.compactMap { CoreAudio.process(pid: $0) }
        var address = CoreAudio.address(kAudioTapPropertyDescription)
        var ref = Unmanaged.passUnretained(description)
        let status = AudioObjectSetPropertyData(tap, &address, 0, nil,
                                                UInt32(MemoryLayout<Unmanaged<CATapDescription>>.size), &ref)
        if status != noErr { NSLog("Milo: couldn't leave Milo's voice out of the meeting tap: \(status)") }
    }

    func stop() {
        if device != kAudioObjectUnknown {
            if let proc {
                AudioDeviceStop(device, proc)
                AudioDeviceDestroyIOProcID(device, proc)
            }
            AudioHardwareDestroyAggregateDevice(device)
        }
        if tap != kAudioObjectUnknown { AudioHardwareDestroyProcessTap(tap) }
        proc = nil
        device = AudioObjectID(kAudioObjectUnknown)
        tap = AudioObjectID(kAudioObjectUnknown)
    }

    private func check(_ status: OSStatus, _ what: String) throws {
        if status != noErr { throw Self.error("couldn't \(what): \(status)") }
    }

    private static func error(_ text: String) -> NSError {
        NSError(domain: "Milo.ProcessTap", code: 1, userInfo: [NSLocalizedDescriptionKey: text])
    }
}

/// The call's audio through ScreenCaptureKit, for a Mac without process taps. Needs Screen Recording, which
/// Milo already asks for to look at the screen.
private final class ScreenAudioCapture: NSObject, CallCapture, SCStreamOutput, SCStreamDelegate {
    private let excluded: [pid_t]
    private let sink: ([Float], UInt64) -> Void
    private let failed: (Error) -> Void
    private var stream: SCStream?
    private var resampler: Resampler?
    private var format: AVAudioFormat?
    private let queue = DispatchQueue(label: "milo.meeting.screen-audio", qos: .userInitiated)
    private var stopped = false

    init(excluding pids: [pid_t], sink: @escaping ([Float], UInt64) -> Void, failed: @escaping (Error) -> Void) {
        excluded = pids
        self.sink = sink
        self.failed = failed
    }

    func start() {
        SCShareableContent.getExcludingDesktopWindows(false, onScreenWindowsOnly: true) { [weak self] content, error in
            DispatchQueue.main.async { self?.begin(content, error) }
        }
    }

    private func begin(_ content: SCShareableContent?, _ error: Error?) {
        guard !stopped else { return }
        guard let content, let display = content.displays.first else {
            failed(error ?? NSError(domain: "Milo", code: 3, userInfo: [NSLocalizedDescriptionKey: "no display"]))
            return
        }
        let milo = content.applications.filter { excluded.contains($0.processID) }
        let filter = SCContentFilter(display: display, excludingApplications: milo, exceptingWindows: [])
        let config = SCStreamConfiguration()
        config.capturesAudio = true
        config.excludesCurrentProcessAudio = true
        config.sampleRate = 16_000
        config.channelCount = 1
        config.width = 2
        config.height = 2
        config.minimumFrameInterval = CMTime(value: 1, timescale: 1)
        let stream = SCStream(filter: filter, configuration: config, delegate: self)
        do {
            try stream.addStreamOutput(self, type: .audio, sampleHandlerQueue: queue)
        } catch {
            failed(error)
            return
        }
        self.stream = stream
        stream.startCapture { [weak self] error in
            guard let error else { return }
            DispatchQueue.main.async { self?.failed(error) }
        }
    }

    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .audio, let description = sampleBuffer.formatDescription else { return }
        if format == nil {
            let format = AVAudioFormat(cmAudioFormatDescription: description)
            self.format = format
            resampler = Resampler(from: format)
        }
        let frames = AVAudioFrameCount(sampleBuffer.numSamples)
        guard let format, let resampler, frames > 0,
              let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: frames) else { return }
        buffer.frameLength = frames
        guard CMSampleBufferCopyPCMDataIntoAudioBufferList(sampleBuffer, at: 0, frameCount: Int32(frames),
                                                           into: buffer.mutableAudioBufferList) == noErr else { return }
        let seconds = sampleBuffer.presentationTimeStamp.seconds
        let host = seconds.isFinite ? AVAudioTime.hostTime(forSeconds: seconds) : mach_absolute_time()
        sink(resampler.convert(buffer), host)
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        DispatchQueue.main.async { [weak self] in
            guard let self, !stopped else { return }
            failed(error)
        }
    }

    func stop() {
        stopped = true
        stream?.stopCapture { _ in }
        stream = nil
    }
}
