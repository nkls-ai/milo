import Foundation

/// Writes one track of a meeting as 16-bit mono WAV files of `chunkSeconds` each: `<track>-0001.wav`, … The
/// header goes in first and gets its sizes when the chunk is full, so a crash costs at most the header's sizes,
/// which the brain doesn't need (it reads every chunk to its end). Samples are on disk before anyone else sees
/// them: that is how a meeting survives a crash of the brain or the app.
///
/// Not thread-safe: the recorder calls it from one serial queue.
public final class ChunkWriter {
    public struct Finished: Equatable, Sendable {
        public var index: Int
        public var path: String
        public var start: Double
        public var seconds: Double
    }

    public let track: String
    public let sampleRate: Int
    public let chunkSeconds: Double
    /// Samples written so far, silence included: the track's position in meeting time.
    public private(set) var position = 0
    /// Called for every chunk once it is complete and on disk.
    public var onChunk: ((Finished) -> Void)?

    private let dir: URL
    private var file: FileHandle?
    private var index = 0
    private var inChunk = 0
    private var samplesPerChunk: Int { Int(Double(sampleRate) * chunkSeconds) }

    /// A gap longer than this between where the track is and where new samples say they start is filled with
    /// silence. Shorter differences are clock jitter and ignored.
    public static let gapTolerance = 0.25

    public init(dir: URL, track: String, sampleRate: Int = 16_000, chunkSeconds: Double = 30) {
        self.dir = dir
        self.track = track
        self.sampleRate = sampleRate
        self.chunkSeconds = chunkSeconds
    }

    /// Appends samples (-1...1) that start `time` seconds into the meeting, nil for right after the last ones.
    /// When samples went missing (the device changed, the app was busy) the gap becomes silence, so every chunk
    /// keeps its place in meeting time and the speakers' times stay right.
    public func append(_ samples: [Float], at time: Double? = nil) throws {
        if let time {
            let gap = time - Double(position) / Double(sampleRate)
            if gap > Self.gapTolerance { try write(silence: Int(gap * Double(sampleRate))) }
        }
        var rest = samples[...]
        while !rest.isEmpty {
            try openIfNeeded()
            let take = min(rest.count, samplesPerChunk - inChunk)
            try writeSamples(rest.prefix(take))
            rest = rest.dropFirst(take)
            if inChunk == samplesPerChunk { try close() }
        }
    }

    /// Closes the chunk being written and reports it, however short.
    public func finish() throws {
        try close()
    }

    private func write(silence count: Int) throws {
        var left = count
        let block = [Float](repeating: 0, count: min(count, sampleRate))
        while left > 0 {
            let n = min(left, block.count)
            try append(Array(block.prefix(n)))
            left -= n
        }
    }

    private func openIfNeeded() throws {
        guard file == nil else { return }
        // Other people's voices: readable by the user alone.
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true,
                                                attributes: [.posixPermissions: 0o700])
        index += 1
        inChunk = 0
        let url = path(index)
        FileManager.default.createFile(atPath: url.path, contents: Self.header(dataBytes: 0, sampleRate: sampleRate),
                                       attributes: [.posixPermissions: 0o600])
        let handle = try FileHandle(forWritingTo: url)
        try handle.seekToEnd()
        file = handle
    }

    private func writeSamples(_ samples: ArraySlice<Float>) throws {
        guard let file else { return }
        var data = Data(count: samples.count * 2)
        data.withUnsafeMutableBytes { raw in
            let out = raw.bindMemory(to: Int16.self)
            for (i, s) in samples.enumerated() {
                out[i] = Int16(max(-1, min(1, s)) * 32767).littleEndian
            }
        }
        try file.write(contentsOf: data)
        inChunk += samples.count
        position += samples.count
    }

    private func close() throws {
        guard let file else { return }
        self.file = nil
        let bytes = inChunk * 2
        try file.seek(toOffset: 0)
        try file.write(contentsOf: Self.header(dataBytes: bytes, sampleRate: sampleRate))
        try file.synchronize()
        try file.close()
        let start = Double((index - 1) * samplesPerChunk) / Double(sampleRate)
        onChunk?(Finished(index: index, path: path(index).path, start: start,
                          seconds: Double(inChunk) / Double(sampleRate)))
    }

    private func path(_ index: Int) -> URL {
        dir.appendingPathComponent(String(format: "%@-%04d.wav", track, index))
    }

    /// A 44-byte PCM WAV header: mono, 16-bit.
    static func header(dataBytes: Int, sampleRate: Int) -> Data {
        var data = Data()
        func u32(_ v: Int) { withUnsafeBytes(of: UInt32(v).littleEndian) { data.append(contentsOf: $0) } }
        func u16(_ v: Int) { withUnsafeBytes(of: UInt16(v).littleEndian) { data.append(contentsOf: $0) } }
        data.append(contentsOf: Array("RIFF".utf8)); u32(36 + dataBytes)
        data.append(contentsOf: Array("WAVE".utf8))
        data.append(contentsOf: Array("fmt ".utf8)); u32(16); u16(1); u16(1); u32(sampleRate); u32(sampleRate * 2)
        u16(2); u16(16)
        data.append(contentsOf: Array("data".utf8)); u32(dataBytes)
        return data
    }
}
