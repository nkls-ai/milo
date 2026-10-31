import Foundation

/// Keeps a script from making a sandboxed app (Excel, Word) save somewhere macOS would stop it to ask for file
/// access. That question ("Grant File Access") blocks the app until someone clicks it, so a task that runs in
/// the background would sit there stuck (ADR 25).
///
/// Like `risk.py`, a brake, not a sandbox: it reads the script's words. A script that saves or exports and names a
/// path outside the app's own folders is refused, and so is one that saves to a folder it gets with `path to`.
/// Saving in place (a plain `save`), and paths it builds some other way, go through.
public enum SandboxGuard {
    /// Why the script must not run, in words for the worker, or nil. `places` says where an app can write without
    /// being asked (nil: anywhere, it isn't sandboxed).
    public static func refusal(script: String, home: String = NSHomeDirectory(),
                               places: (AccessApp) -> [String]?) -> String? {
        guard matches(writes, script) else { return nil }
        let sandboxed = apps(in: script).compactMap { app in places(app).map { (app, $0) } }
        guard let (app, allowed) = sandboxed.first else { return nil }
        let allowedPaths = sandboxed.flatMap(\.1).map { standard($0, home: home) }
        let outside = matches(pathTo, script)
            || paths(in: script, home: home).contains { path in !allowedPaths.contains { inside(path, $0) } }
        guard outside else { return nil }
        let name = app.label
        let place = allowed.first.map { " save it in \($0)" } ?? " save it inside \(name)'s own folder"
        return "\(name) is sandboxed: saving outside its own folder makes macOS stop \(name) with a “Grant File "
            + "Access” question until someone clicks it, so this script didn't run. Leave the document open and "
            + "tell the user to save it where they want, or, for a working copy only \(name) opens again,\(place)."
    }

    /// The apps a script talks to: `application "Name"`, `app "Name"` or `application id "bundle"`.
    static func apps(in script: String) -> [AccessApp] {
        var found: [AccessApp] = []
        for match in appRef.matches(in: script, range: NSRange(script.startIndex..., in: script)) {
            guard let name = Range(match.range(at: 2), in: script).map({ String(script[$0]) }) else { continue }
            let app = match.range(at: 1).location != NSNotFound ? AccessApp(name: "", bundle: name) : AccessApp(name: name)
            if !found.contains(app) { found.append(app) }
        }
        return found
    }

    /// Quoted strings that are paths: POSIX ("/Users/…", "~/…") or HFS ("Macintosh HD:Users:…"), as POSIX paths.
    static func paths(in script: String, home: String) -> [String] {
        quoted.matches(in: script, range: NSRange(script.startIndex..., in: script)).compactMap { match in
            guard let range = Range(match.range(at: 1), in: script) else { return nil }
            let text = String(script[range])
            if text.hasPrefix("/") || text.hasPrefix("~/") { return standard(text, home: home) }
            // HFS: a volume name, then colons. The boot volume's paths start at "/".
            let parts = text.split(separator: ":", omittingEmptySubsequences: false)
            guard parts.count >= 3, !parts[0].isEmpty, !parts[0].contains("/"), !text.contains("\n") else { return nil }
            return standard("/" + parts.dropFirst().joined(separator: "/"), home: home)
        }
    }

    static func inside(_ path: String, _ folder: String) -> Bool {
        let folder = folder.hasSuffix("/") ? String(folder.dropLast()) : folder
        return path == folder || path.hasPrefix(folder + "/")
    }

    private static func standard(_ path: String, home: String) -> String {
        let expanded = path.hasPrefix("~/") ? home + path.dropFirst() : path
        return (expanded as NSString).standardizingPath
    }

    private static func matches(_ pattern: NSRegularExpression, _ text: String) -> Bool {
        pattern.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)) != nil
    }

    private static let writes = try! NSRegularExpression(pattern: #"\b(save|export)\b"#, options: .caseInsensitive)
    private static let pathTo = try! NSRegularExpression(pattern: #"\bpath to\b"#, options: .caseInsensitive)
    private static let appRef = try! NSRegularExpression(pattern: #"\bapp(?:lication)?\s+(id\s+)?"([^"]+)""#,
                                                         options: .caseInsensitive)
    private static let quoted = try! NSRegularExpression(pattern: #""([^"]*)""#)
}
