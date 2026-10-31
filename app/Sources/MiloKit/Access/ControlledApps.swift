import Combine
import Foundation

/// The apps Milo asked the system about, and what it said: the short list in the menu bar and the permissions
/// window. Read-only: the switches live in System Settings. Kept in UserDefaults, since macOS lets no app read the
/// list back.
public final class ControlledApps: ObservableObject {
    public struct Entry: Equatable, Codable, Sendable, Identifiable {
        public var app: AccessApp
        public var allowed: Bool
        public var id: String { app.bundle.isEmpty ? app.name : app.bundle }
    }

    @Published public private(set) var entries: [Entry]
    private let defaults: UserDefaults
    static let key = "MiloControlledApps"

    public init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        entries = (defaults.data(forKey: Self.key)).flatMap { try? JSONDecoder().decode([Entry].self, from: $0) } ?? []
    }

    /// The system's latest answer about an app. Only a yes or a no counts; the list stays in name order.
    public func note(_ answer: AccessAnswer) {
        guard let app = answer.app, answer.state == .yes || answer.state == .no else { return }
        let entry = Entry(app: app, allowed: answer.state == .yes)
        var next = entries.filter { !Self.same($0.app, app) }
        next.append(entry)
        next.sort { $0.app.label.localizedCaseInsensitiveCompare($1.app.label) == .orderedAscending }
        guard next != entries else { return }
        entries = next
        if let data = try? JSONEncoder().encode(next) { defaults.set(data, forKey: Self.key) }
    }

    /// Asks again about every app on the list, without asking the user or starting anything. Off the main
    /// thread; answers arrive on the main queue.
    public func refresh(from source: AccessSource) {
        let apps = entries.map(\.app)
        DispatchQueue.global(qos: .utility).async { [weak self] in
            let answers = apps.map { source.check(.control, app: $0, launch: false) }
            DispatchQueue.main.async { answers.forEach { self?.note($0) } }
        }
    }

    static func same(_ a: AccessApp, _ b: AccessApp) -> Bool {
        if !a.bundle.isEmpty && !b.bundle.isEmpty { return a.bundle.lowercased() == b.bundle.lowercased() }
        return a.name.lowercased() == b.name.lowercased()
    }
}
