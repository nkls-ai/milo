import Foundation

/// A process that uses the microphone right now, from Core Audio's process list.
public struct MicClient: Equatable, Sendable {
    public var bundle: String
    public var pid: Int32

    public init(bundle: String, pid: Int32) {
        self.bundle = bundle
        self.pid = pid
    }
}

/// A call going on in an app: what `call_started` tells the brain.
public struct Call: Equatable, Sendable {
    /// "Zoom", "Microsoft Teams", "Google Meet", "FaceTime", "Slack".
    public var app: String
    public var bundle: String
    /// The window or tab title, "" if unknown.
    public var title: String

    public init(app: String, bundle: String, title: String = "") {
        self.app = app
        self.bundle = bundle
        self.title = title
    }
}

/// Which microphone users are calls. Call apps use the mic only in a call (or a huddle), so for them the mic is
/// enough. A browser uses it for many things, so a browser counts only with a meeting tab open.
public enum CallApps {
    /// Bundle id (or its prefix, for helper processes) to the name the user knows.
    static let native: [(bundle: String, name: String)] = [
        ("us.zoom.xos", "Zoom"),
        ("com.microsoft.teams2", "Microsoft Teams"),
        ("com.microsoft.teams", "Microsoft Teams"),
        ("com.apple.FaceTime", "FaceTime"),
        ("com.apple.avconferenced", "FaceTime"),
        ("com.tinyspeck.slackmacgap", "Slack"),
        ("Cisco-Systems.Spark", "Webex"),
        ("com.hnc.Discord", "Discord"),
        ("com.hnc.DiscordPTB", "Discord"),
        ("com.hnc.DiscordCanary", "Discord"),
        ("net.whatsapp.WhatsApp", "WhatsApp"),
        ("desktop.WhatsApp", "WhatsApp"),
        ("org.whispersystems.signal-desktop", "Signal"),
        ("ru.keepcoder.Telegram", "Telegram"),
        ("org.telegram.desktop", "Telegram"),
        ("com.skype.skype", "Skype"),
    ]

    /// Browsers by the bundle of the process that holds the mic; Safari's is WebKit's GPU process.
    static let browsers: [(process: String, browser: String)] = [
        ("com.google.Chrome", "com.google.Chrome"),
        ("com.apple.WebKit.GPU", "com.apple.Safari"),
        ("com.apple.Safari", "com.apple.Safari"),
        ("org.mozilla.firefox", "org.mozilla.firefox"),
        ("company.thebrowser.Browser", "company.thebrowser.Browser"),
        ("com.microsoft.edgemac", "com.microsoft.edgemac"),
        ("com.brave.Browser", "com.brave.Browser"),
        ("com.vivaldi.Vivaldi", "com.vivaldi.Vivaldi"),
        ("com.operasoftware.Opera", "com.operasoftware.Opera"),
    ]

    /// Tab titles of web meetings, matched in the browser's window titles.
    static let webMeetings: [(name: String, matches: (String) -> Bool)] = [
        ("Google Meet", { $0.hasPrefix("Meet - ") || $0.hasPrefix("Meet – ") || $0.contains("Google Meet") }),
        ("Microsoft Teams", { $0.contains("Microsoft Teams") }),
        ("Zoom", { $0.contains("Zoom Meeting") || $0.contains("Zoom Workplace") }),
        ("Slack", { $0.localizedCaseInsensitiveContains("huddle") }),
        ("Webex", { $0.contains("Webex") }),
        ("Whereby", { $0.contains("Whereby") }),
        ("Jitsi Meet", { $0.contains("Jitsi Meet") }),
        ("Discord", { $0.hasSuffix("- Discord") || $0.hasSuffix("| Discord") }),
    ]

    static func matches(_ bundle: String, _ prefix: String) -> Bool {
        bundle == prefix || bundle.hasPrefix(prefix + ".")
    }

    /// The call `client` is in, if any. `titles` gives a browser's window titles by its bundle id.
    public static func call(for client: MicClient, titles: (String) -> [String]) -> Call? {
        if let app = native.first(where: { matches(client.bundle, $0.bundle) }) {
            return Call(app: app.name, bundle: client.bundle, title: titles(app.bundle).first ?? "")
        }
        guard let browser = browsers.first(where: { matches(client.bundle, $0.process) })?.browser else { return nil }
        for title in titles(browser) {
            if let meeting = webMeetings.first(where: { $0.matches(title) }) {
                return Call(app: meeting.name, bundle: browser, title: title)
            }
        }
        return nil
    }

    /// The calls among the mic users, one per app.
    public static func calls(_ clients: [MicClient], titles: (String) -> [String]) -> [Call] {
        var seen = Set<String>()
        return clients.compactMap { call(for: $0, titles: titles) }.filter { seen.insert($0.app).inserted }
    }
}

/// Turns what each poll saw into `call_started` and `call_ended`, steadily: a call starts after it was seen in
/// `startAfter` polls in a row (a quick mic check in Zoom's settings isn't a call), and ends after it was gone for
/// `endAfter` polls (muting, or a moment between two calls, isn't the end). One call at a time.
public struct CallDetector {
    public enum Change: Equatable, Sendable {
        case started(Call)
        case ended(Call)
    }

    public let startAfter: Int
    public let endAfter: Int
    public private(set) var current: Call?
    private var seen: [String: Int] = [:]
    private var missing = 0

    public init(startAfter: Int = 2, endAfter: Int = 3) {
        self.startAfter = startAfter
        self.endAfter = endAfter
    }

    public mutating func update(_ calls: [Call]) -> [Change] {
        if let call = current {
            if calls.contains(where: { $0.app == call.app }) {
                missing = 0
                return []
            }
            missing += 1
            guard missing >= endAfter else { return [] }
            current = nil
            missing = 0
            seen = [:]
            return [.ended(call)]
        }
        seen = Dictionary(uniqueKeysWithValues: calls.map { ($0.app, (seen[$0.app] ?? 0) + 1) })
        guard let call = calls.first(where: { (seen[$0.app] ?? 0) >= startAfter }) else { return [] }
        current = call
        seen = [:]
        return [.started(call)]
    }
}
