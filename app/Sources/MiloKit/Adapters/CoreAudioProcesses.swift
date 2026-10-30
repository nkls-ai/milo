import AppKit
import CoreAudio

/// Reading Core Audio's objects: the default output device, and (macOS 14.2+) the processes that use audio.
enum CoreAudio {
    static func address(_ selector: AudioObjectPropertySelector,
                        scope: AudioObjectPropertyScope = kAudioObjectPropertyScopeGlobal) -> AudioObjectPropertyAddress {
        AudioObjectPropertyAddress(mSelector: selector, mScope: scope, mElement: kAudioObjectPropertyElementMain)
    }

    static func value<T: BitwiseCopyable>(_ object: AudioObjectID, _ selector: AudioObjectPropertySelector, default value: T) -> T {
        var address = address(selector)
        var result = value
        var size = UInt32(MemoryLayout<T>.size)
        let status = withUnsafeMutableBytes(of: &result) { bytes in
            AudioObjectGetPropertyData(object, &address, 0, nil, &size, bytes.baseAddress!)
        }
        return status == noErr ? result : value
    }

    static func string(_ object: AudioObjectID, _ selector: AudioObjectPropertySelector) -> String? {
        var address = address(selector)
        var result: Unmanaged<CFString>?
        var size = UInt32(MemoryLayout<Unmanaged<CFString>?>.size)
        guard AudioObjectGetPropertyData(object, &address, 0, nil, &size, &result) == noErr, let result else { return nil }
        return result.takeRetainedValue() as String
    }

    static func objects(_ object: AudioObjectID, _ selector: AudioObjectPropertySelector) -> [AudioObjectID] {
        var address = address(selector)
        var size: UInt32 = 0
        guard AudioObjectGetPropertyDataSize(object, &address, 0, nil, &size) == noErr, size > 0 else { return [] }
        var ids = [AudioObjectID](repeating: 0, count: Int(size) / MemoryLayout<AudioObjectID>.size)
        guard AudioObjectGetPropertyData(object, &address, 0, nil, &size, &ids) == noErr else { return [] }
        return ids
    }

    static var defaultOutputUID: String? {
        let device = value(AudioObjectID(kAudioObjectSystemObject), kAudioHardwarePropertyDefaultSystemOutputDevice,
                           default: AudioObjectID(kAudioObjectUnknown))
        return device == kAudioObjectUnknown ? nil : string(device, kAudioDevicePropertyDeviceUID)
    }

    /// The audio process object of `pid`, nil while that process has never used audio.
    @available(macOS 14.2, *)
    static func process(pid: pid_t) -> AudioObjectID? {
        var address = address(kAudioHardwarePropertyTranslatePIDToProcessObject)
        var pid = pid
        var object = AudioObjectID(kAudioObjectUnknown)
        var size = UInt32(MemoryLayout<AudioObjectID>.size)
        let status = AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &address,
                                                UInt32(MemoryLayout<pid_t>.size), &pid, &size, &object)
        return status == noErr && object != kAudioObjectUnknown ? object : nil
    }
}

/// Who uses the microphone (Core Audio, macOS 14.2+) and what a browser's windows are called (Accessibility).
public final class MacCallSignals: CallSignals {
    public init() {}

    public func micClients() -> [MicClient] {
        guard #available(macOS 14.2, *) else { return [] }
        let me = ProcessInfo.processInfo.processIdentifier
        return CoreAudio.objects(AudioObjectID(kAudioObjectSystemObject), kAudioHardwarePropertyProcessObjectList)
            .compactMap { object -> MicClient? in
                guard CoreAudio.value(object, kAudioProcessPropertyIsRunningInput, default: UInt32(0)) != 0 else {
                    return nil
                }
                let pid = CoreAudio.value(object, kAudioProcessPropertyPID, default: pid_t(-1))
                guard pid != me else { return nil }
                let bundle = CoreAudio.string(object, kAudioProcessPropertyBundleID)
                    ?? NSRunningApplication(processIdentifier: pid)?.bundleIdentifier ?? ""
                return bundle.isEmpty ? nil : MicClient(bundle: bundle, pid: pid)
            }
    }

    public func windowTitles(bundle: String) -> [String] {
        NSRunningApplication.runningApplications(withBundleIdentifier: bundle).flatMap { app -> [String] in
            let element = AXUIElementCreateApplication(app.processIdentifier)
            let windows: [AXUIElement] = AX.attribute(element, kAXWindowsAttribute) ?? []
            return windows.compactMap { AX.string($0, kAXTitleAttribute) }
        }
    }
}
