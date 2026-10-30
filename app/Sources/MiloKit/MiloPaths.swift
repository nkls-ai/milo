import Foundation

/// Locations inside the ~/Milo workspace that the app uses.
public struct MiloPaths: Sendable {
    public let home: URL

    public init(home: URL) {
        self.home = home
    }

    /// `MILO_HOME` if set, else ~/Milo.
    public static func resolve(environment: [String: String],
                               userHome: URL = FileManager.default.homeDirectoryForCurrentUser) -> MiloPaths {
        if let env = environment["MILO_HOME"], !env.isEmpty { return MiloPaths(home: URL(fileURLWithPath: env)) }
        return MiloPaths(home: userHome.appendingPathComponent("Milo"))
    }

    public var socket: URL { home.appendingPathComponent("run/brain.sock") }
    /// Held by the running brain; see UVBrainLauncher.
    public var brainLock: URL { home.appendingPathComponent("run/brain.lock") }
    public var brainLog: URL { home.appendingPathComponent("logs/brain.log") }
    /// Where a brain launched by the app writes stdout and stderr.
    public var brainStdoutLog: URL { home.appendingPathComponent("logs/brain.stdout.log") }
}

extension MiloPaths {
    /// Screenshots for a look or the worker. Private, pruned to the newest few.
    public var screens: URL { home.appendingPathComponent("state/screens") }
}
