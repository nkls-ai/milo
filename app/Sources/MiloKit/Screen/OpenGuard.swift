import Foundation

/// What Milo may open the moment the user asks (ADR 28), decided without AppKit so it can be tested.
///
/// Opening an app, a web page or a document changes nothing, so it needs no question. Two things would: an address
/// with another scheme (`shortcuts://run-shortcut`, `x-apple.systempreferences:`, `file:`) and a file that runs
/// code when opened (an app, a `.command` script, an installer). Those are refused here, whoever asks.
public enum OpenGuard {
    /// Content types that run something when opened.
    static let runningTypes: Set<String> = [
        "public.executable", "public.unix-executable", "com.apple.application", "com.apple.application-bundle",
        "com.apple.application-file", "public.script", "public.shell-script", "com.apple.terminal.shell-script",
        "com.apple.applescript.script", "com.apple.applescript.script-bundle", "com.apple.applescript.text",
        "com.apple.automator-workflow", "com.apple.installer-package-archive", "com.apple.installer-package",
        "com.apple.shortcut", "com.apple.systempreference.prefpane",
    ]
    /// The same by file extension, for files whose type the system doesn't know.
    static let runningExtensions: Set<String> = [
        "app", "command", "tool", "sh", "zsh", "bash", "csh", "terminal", "workflow", "action", "pkg", "mpkg",
        "scpt", "scptd", "applescript", "shortcut", "prefpane", "saver", "kext", "fileloc", "jar",
    ]

    /// Why this address can't be opened, or nil: only web pages (http and https with a host) open as addresses.
    public static func refuses(url text: String) -> String? {
        guard let url = URL(string: text), let scheme = url.scheme?.lowercased(),
              ["http", "https"].contains(scheme), url.host?.isEmpty == false else {
            return "Milo opens web pages only (http and https), not \(text)."
        }
        return nil
    }

    /// Why this file can't be opened, or nil. `types` are its content type and every type it conforms to.
    /// A folder always opens. A plain file with the executable bit and no known type is refused too.
    public static func refuses(path: String, isDirectory: Bool, types: [String], executable: Bool) -> String? {
        if isDirectory && URL(fileURLWithPath: path).pathExtension.lowercased() != "app" { return nil }
        let name = URL(fileURLWithPath: path).lastPathComponent
        let ext = URL(fileURLWithPath: path).pathExtension.lowercased()
        if runningExtensions.contains(ext) || types.contains(where: runningTypes.contains) {
            return "Milo doesn't open \(name): opening it would run a program. Ask the user to open it themselves."
        }
        let known = types.contains { $0 != "public.data" && $0 != "public.item" && $0 != "public.content" }
        if executable && !known {
            return "Milo doesn't open \(name): it is a program. Ask the user to open it themselves."
        }
        return nil
    }

    /// Calls `check` every `poll` seconds until it says yes or `timeout` has passed. Returns whether it said yes.
    /// For waiting until an app is in front with a window, bounded so a slow app never holds Milo up for long.
    public static func wait(timeout: TimeInterval, poll: TimeInterval = 0.05, _ check: () -> Bool) -> Bool {
        let end = Date().addingTimeInterval(timeout)
        while true {
            if check() { return true }
            if Date() >= end { return false }
            Thread.sleep(forTimeInterval: min(poll, max(0, end.timeIntervalSinceNow)))
        }
    }
}
