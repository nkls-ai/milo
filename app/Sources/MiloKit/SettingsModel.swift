import Combine
import Foundation

/// What the Settings window shows: the brain's last `settings` report. Changes go to the brain, which saves them
/// in config.toml and answers with a new report.
public final class SettingsModel: ObservableObject {
    /// nil until the brain answered, e.g. while it starts.
    @Published public private(set) var report: SettingsReport?

    var send: ((BrainCommand) -> Void)?

    public init(report: SettingsReport? = nil) {
        self.report = report
    }

    func apply(_ new: SettingsReport) {
        // A report without rows only carries an error (the file can't be read): keep showing the last values.
        if new.settings.isEmpty, var old = report {
            old.error = new.error
            report = old
        } else {
            report = new
        }
    }

    /// Ask the brain for the settings again.
    public func refresh() {
        send?(.getSettings)
    }

    /// The value of `[section] key`, or nil if the brain didn't report it.
    public func value(_ section: String, _ key: String) -> JSONValue? {
        report?[section, key]?.value
    }

    /// Shows the new value at once and sends it; the brain's answer confirms it or puts the old one back.
    public func change(_ section: String, _ key: String, to value: JSONValue) {
        guard var report, let index = report.settings.firstIndex(where: { $0.section == section && $0.key == key }),
              report.settings[index].value != value else { return }
        report.settings[index].value = value
        report.error = ""
        self.report = report
        send?(.setSetting(section: section, key: key, value: value))
    }
}
