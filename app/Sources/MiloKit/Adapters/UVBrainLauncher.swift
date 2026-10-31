import Foundation

/// Starts the Python brain with `uv run`, never a second one: the brain holds `lockURL` for its whole life,
/// and while some process holds it this waits (a brain that is shutting down) or leaves it be (one started
/// by hand). Two brains would each load the models, and on 16 GB the pair fills swap.
public final class UVBrainLauncher: BrainLauncher {
    public struct Configuration: Sendable {
        public var brainDir: URL
        /// Receives the brain's stdout and stderr.
        public var logURL: URL
        /// Paths tried in order; the first executable one wins.
        public var uvCandidates: [String]
        /// `uv run --extra` names.
        public var extras: [String]
        /// The script uv runs.
        public var command: String
        /// Prepended to PATH, since an app launched from Finder gets a bare PATH.
        public var extraPath: [String]
        /// How often to look at the lock again while another brain holds it.
        public var restartDelay: TimeInterval
        /// The brain's single-instance lock, `<workspace>/run/brain.lock`. nil: don't check.
        public var lockURL: URL?
        /// How long to wait for a brain holding the lock to go away before deciding it is staying.
        public var lockWait: TimeInterval

        public init(brainDir: URL, logURL: URL, lockURL: URL? = nil,
                    uvCandidates: [String] = Configuration.defaultUVCandidates,
                    extras: [String] = ["omnivoice", "pocket"], command: String = "milo",
                    extraPath: [String] = ["/opt/homebrew/bin", "/usr/local/bin", "\(NSHomeDirectory())/.local/bin"],
                    restartDelay: TimeInterval = 1, lockWait: TimeInterval = 30) {
            self.brainDir = brainDir
            self.logURL = logURL
            self.uvCandidates = uvCandidates
            self.extras = extras
            self.command = command
            self.extraPath = extraPath
            self.restartDelay = restartDelay
            self.lockURL = lockURL
            self.lockWait = lockWait
        }

        public static let defaultUVCandidates = [
            "\(NSHomeDirectory())/.local/bin/uv", "/opt/homebrew/bin/uv", "/usr/local/bin/uv",
        ]

        /// e.g. `run --project <brainDir> --extra omnivoice milo`
        public var arguments: [String] {
            ["run", "--project", brainDir.path] + extras.flatMap { ["--extra", $0] } + [command]
        }
    }

    public let configuration: Configuration
    private let scheduler: Scheduler
    private var process: Process?
    private var waiting: ScheduledTask?

    public init(configuration: Configuration, scheduler: Scheduler) {
        self.configuration = configuration
        self.scheduler = scheduler
    }

    /// The brain checkout: `MILO_BRAIN_DIR`, then the Info.plist `MiloBrainDir`, then `devFallback`.
    public static func resolveBrainDir(environment: [String: String], infoPlistValue: String?,
                                       devFallback: URL = devBrainDir()) -> URL {
        if let env = environment["MILO_BRAIN_DIR"], !env.isEmpty { return URL(fileURLWithPath: env) }
        if let plist = infoPlistValue, !plist.isEmpty { return URL(fileURLWithPath: plist) }
        return devFallback
    }

    /// `<repo>/brain`, found from this source file's location in `<repo>/app/Sources/...`.
    public static func devBrainDir() -> URL {
        var url = URL(fileURLWithPath: #filePath)
        while url.lastPathComponent != "Sources", url.pathComponents.count > 1 {
            url.deleteLastPathComponent()
        }
        return url.deletingLastPathComponent().deletingLastPathComponent().appendingPathComponent("brain")
    }

    public func start() {
        waiting?.cancel()
        waiting = nil
        start(triesLeft: Int((configuration.lockWait / configuration.restartDelay).rounded(.up)))
    }

    private func start(triesLeft: Int) {
        if let p = process, p.isRunning { return }
        if let lock = configuration.lockURL, Self.isLocked(lock) {
            guard triesLeft > 0 else {
                NSLog("Milo: another brain holds \(lock.path); not starting one")
                return
            }
            waiting = scheduler.after(configuration.restartDelay) { [weak self] in
                self?.waiting = nil
                self?.start(triesLeft: triesLeft - 1)
            }
            return
        }
        launch()
    }

    private func launch() {
        let fm = FileManager.default
        guard let uv = configuration.uvCandidates.first(where: fm.isExecutableFile(atPath:)) else {
            NSLog("Milo: could not find uv; install it or start the brain manually with `uv run milo`")
            return
        }
        let logURL = configuration.logURL
        try? fm.createDirectory(at: logURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        fm.createFile(atPath: logURL.path, contents: nil)
        let log = try? FileHandle(forWritingTo: logURL)
        let p = Process()
        p.executableURL = URL(fileURLWithPath: uv)
        p.arguments = configuration.arguments
        p.currentDirectoryURL = configuration.brainDir
        p.standardOutput = log
        p.standardError = log
        p.standardInput = FileHandle.nullDevice
        var env = ProcessInfo.processInfo.environment
        env["PATH"] = (configuration.extraPath + [env["PATH"] ?? "/usr/bin:/bin"]).joined(separator: ":")
        p.environment = env
        do {
            try p.run()
            process = p
        } catch {
            NSLog("Milo: failed to start brain: \(error)")
        }
    }

    public func stop() {
        waiting?.cancel()
        waiting = nil
        guard let p = process, p.isRunning else { return }
        // SIGTERM: uv passes it on to the brain, SIGINT it swallows.
        p.terminate()
        process = nil
    }

    /// The new brain starts once the old one has let go of the lock.
    public func restart() {
        stop()
        start()
    }

    /// True while a process holds the brain's lock: a brain is running or starting.
    public static func isLocked(_ url: URL) -> Bool {
        let fd = open(url.path, O_RDONLY)
        guard fd >= 0 else { return false }
        defer { close(fd) }
        guard flock(fd, LOCK_EX | LOCK_NB) == 0 else { return errno == EWOULDBLOCK }
        flock(fd, LOCK_UN)
        return false
    }
}
