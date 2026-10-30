import AppKit
import AVFoundation
import CoreGraphics
import EventKit

/// The permissions as macOS reports them. Each check is a quick local lookup, without a dialog.
public final class SystemPermissions: PermissionSource {
    private lazy var store = EKEventStore()

    public init() {}

    public func state(of permission: Permission) -> PermissionState {
        switch permission {
        case .microphone:
            switch AVCaptureDevice.authorizationStatus(for: .audio) {
            case .authorized: .granted
            case .notDetermined: .notAsked
            default: .denied
            }
        case .accessibility: AXIsProcessTrusted() ? .granted : .denied
        case .screenRecording: CGPreflightScreenCaptureAccess() ? .granted : .denied
        case .calendars: Self.eventKit(.event)
        case .reminders: Self.eventKit(.reminder)
        case .automation: Self.automation(of: "com.apple.mail")
        }
    }

    public func prompt(_ permission: Permission) {
        switch permission {
        case .microphone: AVCaptureDevice.requestAccess(for: .audio) { _ in }
        case .calendars: store.requestFullAccessToEvents { _, _ in }
        case .reminders: store.requestFullAccessToReminders { _, _ in }
        case .accessibility, .screenRecording, .automation: openSettings(permission)
        }
    }

    public func openSettings(_ permission: Permission) {
        let page = switch permission {
        case .microphone: "Privacy_Microphone"
        case .accessibility: "Privacy_Accessibility"
        case .screenRecording: "Privacy_ScreenCapture"
        case .calendars: "Privacy_Calendars"
        case .reminders: "Privacy_Reminders"
        case .automation: "Privacy_Automation"
        }
        guard let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?\(page)") else { return }
        NSWorkspace.shared.open(url)
    }

    private static func eventKit(_ type: EKEntityType) -> PermissionState {
        switch EKEventStore.authorizationStatus(for: type) {
        case .fullAccess: .granted
        case .notDetermined: .notAsked
        default: .denied
        }
    }

    /// Whether Milo may send Apple Events to the app `bundleID`. Without asking, so it never shows a dialog;
    /// macOS can only tell while that app is running.
    private static func automation(of bundleID: String) -> PermissionState {
        var target = AEAddressDesc()
        let created = bundleID.withCString { AECreateDesc(typeApplicationBundleID, $0, strlen($0), &target) }
        guard created == noErr else { return .unknown }
        defer { AEDisposeDesc(&target) }
        switch AEDeterminePermissionToAutomateTarget(&target, typeWildCard, typeWildCard, false) {
        case noErr: return .granted
        case OSStatus(errAEEventWouldRequireUserConsent): return .notAsked
        case OSStatus(errAEEventNotPermitted): return .denied
        default: return .unknown
        }
    }
}
