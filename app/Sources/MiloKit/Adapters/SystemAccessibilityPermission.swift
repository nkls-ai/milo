import ApplicationServices

public struct SystemAccessibilityPermission: AccessibilityPermission {
    public init() {}

    public func isTrusted(prompt: Bool) -> Bool {
        let key = kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String
        return AXIsProcessTrustedWithOptions([key: prompt] as CFDictionary)
    }
}
