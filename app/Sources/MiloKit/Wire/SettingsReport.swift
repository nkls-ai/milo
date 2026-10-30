/// What the Settings window shows (`settings` in protocol/messages.json): every setting the brain lets the
/// user change, with its value and its choices.
public struct SettingsReport: Equatable, Sendable {
    public var settings: [Setting]
    /// A saved change waits for Milo to restart.
    public var restart: Bool
    /// Why the last change wasn't saved, in plain words. Empty when it was.
    public var error: String

    public init(settings: [Setting], restart: Bool = false, error: String = "") {
        self.settings = settings
        self.restart = restart
        self.error = error
    }

    /// The setting `[section] key`, if the brain reported it.
    public subscript(section: String, key: String) -> Setting? {
        settings.first { $0.section == section && $0.key == key }
    }
}

/// One key of config.toml. `options` lists the allowed values, named by `labels`; both are empty for a
/// switch or free text. `live` false: a change applies after a restart.
public struct Setting: Equatable, Sendable, Decodable, Identifiable {
    public var section: String
    public var key: String
    public var value: JSONValue
    public var options: [JSONValue]
    public var labels: [String]
    public var live: Bool

    public var id: String { "\(section).\(key)" }

    public init(section: String, key: String, value: JSONValue, options: [JSONValue] = [], labels: [String] = [],
                live: Bool = true) {
        self.section = section
        self.key = key
        self.value = value
        self.options = options
        self.labels = labels
        self.live = live
    }

    /// The options with their labels, the current value first if it isn't one of them (hand-edited).
    public var choices: [(value: JSONValue, label: String)] {
        var all = zip(options, labels).map { (value: $0, label: $1) }
        if !options.contains(value), let text = value.string { all.insert((value, text), at: 0) }
        return all
    }
}
