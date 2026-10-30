import Foundation
import Testing
@testable import MiloKit

@Suite struct BrainLauncherTests {
    /// A fake `uv` that only records that it ran.
    private struct Setup {
        let dir: URL
        let lock: URL
        let marker: URL
        let launcher: UVBrainLauncher
        let scheduler = ManualScheduler()

        init() throws {
            dir = FileManager.default.temporaryDirectory.appendingPathComponent("milo-launcher-\(UUID().uuidString)")
            try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            lock = dir.appendingPathComponent("brain.lock")
            marker = dir.appendingPathComponent("launched")
            let uv = dir.appendingPathComponent("uv")
            try "#!/bin/sh\ntouch '\(marker.path)'\n".write(to: uv, atomically: true, encoding: .utf8)
            try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: uv.path)
            launcher = UVBrainLauncher(
                configuration: .init(brainDir: dir, logURL: dir.appendingPathComponent("out.log"), lockURL: lock,
                                     uvCandidates: [uv.path], restartDelay: 1, lockWait: 5),
                scheduler: scheduler)
        }

        /// Holds the lock the way a brain does; flock locks conflict even within one process.
        func hold() -> Int32 {
            let fd = open(lock.path, O_RDWR | O_CREAT, 0o600)
            precondition(flock(fd, LOCK_EX | LOCK_NB) == 0)
            return fd
        }

        func launched() -> Bool {
            for _ in 0..<100 where !FileManager.default.fileExists(atPath: marker.path) { usleep(20_000) }
            return FileManager.default.fileExists(atPath: marker.path)
        }
    }

    @Test func lockIsFreeWithoutAFileAndHeldWhileABrainHoldsIt() throws {
        let s = try Setup()
        #expect(!UVBrainLauncher.isLocked(s.lock))
        let fd = s.hold()
        #expect(UVBrainLauncher.isLocked(s.lock))
        close(fd)
        #expect(!UVBrainLauncher.isLocked(s.lock))
    }

    @Test func startsWhenNoBrainHoldsTheLock() throws {
        let s = try Setup()
        s.launcher.start()
        #expect(s.launched())
    }

    @Test func waitsForABrainThatIsShuttingDown() throws {
        let s = try Setup()
        let fd = s.hold()
        s.launcher.start()
        s.scheduler.advance(by: 2)
        #expect(!FileManager.default.fileExists(atPath: s.marker.path))
        close(fd)
        s.scheduler.advance(by: 1)
        #expect(s.launched())
    }

    @Test func leavesARunningBrainAloneAfterTheWait() throws {
        let s = try Setup()
        let fd = s.hold()
        defer { close(fd) }
        s.launcher.start()
        s.scheduler.advance(by: 10)
        #expect(s.scheduler.pendingCount == 0)
        usleep(100_000)
        #expect(!FileManager.default.fileExists(atPath: s.marker.path))
    }
}
