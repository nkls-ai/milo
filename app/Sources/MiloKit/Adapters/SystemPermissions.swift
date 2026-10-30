import AppKit
import AVFoundation
import CoreGraphics
import EventKit

/// The permissions as macOS reports them. Each check is a quick local lookup, without a dialog.
public final class SystemPermissions: PermissionSource {
    private lazy var store = EKEventStore()
    private let bundleID: String

    /// Mail stands for Automation: Milo's mail and notes tools script it, and macOS asks per app.
    static let automationTarget = "com.apple.mail"

    public init(bundleID: String = Bundle.main.bundleIdentifier ?? "dev.nkls.milo") {
        self.bundleID = bundleID
    }

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
        case .automation: Self.automation(ask: false)
        }
    }

    public func register(_ permission: Permission) {
        switch permission {
        case .microphone: AVCaptureDevice.requestAccess(for: .audio) { _ in }
        case .accessibility:
            // Adds Milo to the list (switched off) and shows macOS's dialog pointing there.
            let key = kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String
            _ = AXIsProcessTrustedWithOptions([key: true] as CFDictionary)
        case .screenRecording: _ = CGRequestScreenCaptureAccess()
        case .calendars: store.requestFullAccessToEvents { _, _ in }
        case .reminders: store.requestFullAccessToReminders { _, _ in }
        case .automation:
            // A question with no effect on Mail. Asking blocks until the user answers, so off the main thread.
            DispatchQueue.global(qos: .userInitiated).async { _ = Self.automation(ask: true) }
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
        let pane = "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?\(page)"
        guard let url = URL(string: pane) else { return }
        NSWorkspace.shared.open(url)
    }

    public func reset(_ permission: Permission) {
        let service = switch permission {
        case .accessibility: "Accessibility"
        case .screenRecording: "ScreenCapture"
        default: ""
        }
        guard !service.isEmpty else { return }
        let reset = Process()
        reset.executableURL = URL(fileURLWithPath: "/usr/bin/tccutil")
        reset.arguments = ["reset", service, bundleID]
        do {
            try reset.run()
            reset.waitUntilExit()
        } catch {
            NSLog("Milo: tccutil reset %@ failed: %@", service, error.localizedDescription)
        }
    }

    private static func eventKit(_ type: EKEntityType) -> PermissionState {
        switch EKEventStore.authorizationStatus(for: type) {
        case .fullAccess: .granted
        case .notDetermined: .notAsked
        default: .denied
        }
    }

    /// Whether Milo may send Apple Events to Mail. macOS can only tell while Mail is running.
    private static func automation(ask: Bool) -> PermissionState {
        var target = AEAddressDesc()
        let created = automationTarget.withCString { AECreateDesc(typeApplicationBundleID, $0, strlen($0), &target) }
        guard created == noErr else { return .unknown }
        defer { AEDisposeDesc(&target) }
        switch AEDeterminePermissionToAutomateTarget(&target, typeWildCard, typeWildCard, ask) {
        case noErr: return .granted
        case OSStatus(errAEEventWouldRequireUserConsent): return .notAsked
        case OSStatus(errAEEventNotPermitted): return .denied
        default: return .unknown
        }
    }
}
