import Foundation
import Testing
@testable import MiloKit

@Suite struct ScriptOutputTests {
    /// M8: a script that logs more than a pipe holds used to hang until the 30 s stop, because stdout was read to
    /// the end before stderr was read at all.
    @Test func aChildThatFillsStderrFinishesWithBothOutputs() throws {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/sh")
        process.arguments = ["-c", "cat >/dev/null; head -c 300000 /dev/zero | tr '\\\\0' x >&2; echo done"]
        let input = Pipe(), output = Pipe(), errors = Pipe()
        process.standardInput = input
        process.standardOutput = output
        process.standardError = errors
        try process.run()
        DispatchQueue.global().asyncAfter(deadline: .now() + 10) { if process.isRunning { process.terminate() } }
        let started = Date()
        let (out, err) = MacHands.collect(process, input: Data("log".utf8), output: output, errors: errors)
        #expect(Date().timeIntervalSince(started) < 5, "no deadlock")
        #expect(process.terminationReason == .exit)
        #expect(String(decoding: out, as: UTF8.self) == "done\n")
        #expect(err.count == 300_000)
    }
}
