import Foundation
import Testing
@testable import MiloKit

/// protocol/voice_phases.json: the capsule's rules as cases, which the Windows/Linux app runs too
/// (brain/tests/desktop/test_voice_phase.py). A case that fails here and passes there means the two apps differ.
@Suite struct VoicePhaseTableTests {
    struct EarCase: Decodable {
        let kind: String
        let mode: String
    }

    struct PhaseCase: Decodable {
        let kind: String
        let mode: String?
        let handsFree: Bool?
    }

    struct Inputs: Decodable {
        let state: String?
        let ear: EarCase?
        let handsFree: String?
        let pasted: Bool?
        let connected: Bool?
        let lastMode: String?
        let answering: Bool?
    }

    struct Case: Decodable {
        let name: String
        let inputs: Inputs
        let phase: PhaseCase?

        private enum Key: String, CodingKey { case name, phase }

        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: Key.self)
            name = try c.decode(String.self, forKey: .name)
            phase = try c.decodeIfPresent(PhaseCase.self, forKey: .phase)
            inputs = try Inputs(from: decoder)
        }
    }

    struct Table: Decodable {
        let defaults: Inputs
        let cases: [Case]
    }

    private func table() throws -> Table {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()  // MiloKitTests
            .deletingLastPathComponent()  // Tests
            .deletingLastPathComponent()  // app
            .deletingLastPathComponent()  // repo
            .appendingPathComponent("protocol/voice_phases.json")
        return try JSONDecoder().decode(Table.self, from: Data(contentsOf: url))
    }

    private func mode(_ raw: String?) throws -> ListenMode {
        try #require(ListenMode(rawValue: raw ?? "talk"))
    }

    private func ear(_ e: EarCase?) throws -> Ear? {
        guard let e else { return nil }
        let m = try mode(e.mode)
        switch e.kind {
        case "armed": return .armed(m)
        case "open": return .open(m)
        case "caught": return .caught(m)
        default: Issue.record("unknown ear \(e.kind)"); return nil
        }
    }

    private func expected(_ p: PhaseCase?) throws -> VoicePhase? {
        guard let p else { return nil }
        switch p.kind {
        case "armed": return .armed(try mode(p.mode))
        case "listening": return .listening(try mode(p.mode), handsFree: p.handsFree ?? false)
        case "caught": return .caught(try mode(p.mode))
        case "transcribing": return .transcribing(try mode(p.mode))
        case "pasted": return .pasted
        case "thinking": return .thinking
        case "offline": return .offline
        default: Issue.record("unknown phase \(p.kind)"); return nil
        }
    }

    @Test func everyCaseMatches() throws {
        let t = try table()
        #expect(!t.cases.isEmpty)
        for c in t.cases {
            let i = c.inputs, d = t.defaults
            let state = try #require(MiloState(rawValue: i.state ?? d.state ?? "idle"))
            let handsFree = try (i.handsFree ?? d.handsFree).map { try mode($0) }
            let phase = VoicePhase.of(state: state, ear: try ear(i.ear ?? d.ear), handsFree: handsFree,
                                      pasted: i.pasted ?? d.pasted ?? false, connected: i.connected ?? d.connected ?? true,
                                      lastMode: try mode(i.lastMode ?? d.lastMode), answering: i.answering ?? d.answering ?? false)
            #expect(phase == (try expected(c.phase)), "\(c.name)")
        }
    }
}
