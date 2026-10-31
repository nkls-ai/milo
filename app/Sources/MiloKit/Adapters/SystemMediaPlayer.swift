import AppKit
import Foundation

/// The system's now-playing controls. MediaRemote (a private framework every Mac has) sends play, pause, next and
/// previous to whatever plays, without AppleScript and so without asking. If it can't be loaded, the media keys are
/// pressed instead, which only toggle play and pause.
public final class SystemMediaPlayer: MediaPlayer {
    private typealias SendCommand = @convention(c) (UInt32, CFDictionary?) -> Bool
    private typealias GetIsPlaying = @convention(c) (DispatchQueue, @escaping @convention(block) (Bool) -> Void) -> Void

    private lazy var bundle: CFBundle? = CFBundleCreate(
        kCFAllocatorDefault, NSURL(fileURLWithPath: "/System/Library/PrivateFrameworks/MediaRemote.framework"))

    public init() {}

    private func function<T>(_ name: String, as type: T.Type) -> T? {
        guard let bundle, let pointer = CFBundleGetFunctionPointerForName(bundle, name as CFString) else { return nil }
        return unsafeBitCast(pointer, to: type)
    }

    public func isPlaying(_ done: @escaping (Bool) -> Void) {
        guard let get = function("MRMediaRemoteGetNowPlayingApplicationIsPlaying", as: GetIsPlaying.self) else { return }
        get(DispatchQueue.main) { done($0) }
    }

    public func send(_ command: MediaCommand) -> Bool {
        // MRMediaRemoteCommand: play 0, pause 1, next track 4, previous track 5.
        let code: UInt32 = switch command {
        case .play: 0
        case .pause: 1
        case .next: 4
        case .previous: 5
        }
        if let send = function("MRMediaRemoteSendCommand", as: SendCommand.self) {
            return send(code, nil)
        }
        return pressMediaKey(command)
    }

    /// NX_KEYTYPE_PLAY (16), NX_KEYTYPE_NEXT (17), NX_KEYTYPE_PREVIOUS (18), as the keyboard's media keys send them.
    private func pressMediaKey(_ command: MediaCommand) -> Bool {
        let key: Int32 = switch command {
        case .play, .pause: 16
        case .next: 17
        case .previous: 18
        }
        for down in [true, false] {
            let flags = NSEvent.ModifierFlags(rawValue: down ? 0xA00 : 0xB00)
            let data1 = Int((key << 16) | ((down ? 0xA : 0xB) << 8))
            guard let event = NSEvent.otherEvent(with: .systemDefined, location: .zero, modifierFlags: flags,
                                                 timestamp: 0, windowNumber: 0, context: nil, subtype: 8,
                                                 data1: data1, data2: -1) else { return false }
            event.cgEvent?.post(tap: .cghidEventTap)
        }
        return true
    }
}
