import Foundation

/// JSON lines over the brain's Unix socket. Reconnects forever; delivers callbacks on the main queue.
/// The process must ignore SIGPIPE, or a write to a socket the brain just closed kills it.
public final class UnixSocketBrainClient: BrainClient {
    public var onEvent: ((BrainEvent) -> Void)?
    public var onConnectionChange: ((Bool) -> Void)?

    private let path: String
    private let reconnectDelay: TimeInterval
    private let writeQueue = DispatchQueue(label: "milo.brain.write")
    private let encoder = JSONEncoder()
    private let decoder = JSONDecoder()
    private var fd: Int32 = -1
    private var started = false

    public init(socketPath: String, reconnectDelay: TimeInterval = 1) {
        self.path = socketPath
        self.reconnectDelay = reconnectDelay
    }

    public func probe() -> Bool {
        let sock = Self.connectUnix(path)
        guard sock >= 0 else { return false }
        close(sock)
        return true
    }

    public func start() {
        guard !started else { return }
        started = true
        let thread = Thread { [weak self] in self?.runLoop() }
        thread.name = "milo.brain.read"
        thread.start()
    }

    public func send(_ command: BrainCommand) {
        guard var data = try? encoder.encode(command) else { return }
        data.append(0x0A)
        writeQueue.async { [weak self] in
            guard let self, self.fd >= 0 else { return }
            data.withUnsafeBytes { buf in
                var offset = 0
                while offset < buf.count {
                    let n = Darwin.write(self.fd, buf.baseAddress! + offset, buf.count - offset)
                    if n <= 0 { return }
                    offset += n
                }
            }
        }
    }

    private func runLoop() {
        while true {
            let sock = Self.connectUnix(path)
            if sock < 0 {
                Thread.sleep(forTimeInterval: reconnectDelay)
                continue
            }
            writeQueue.sync { fd = sock }
            DispatchQueue.main.async { self.onConnectionChange?(true) }
            readLines(sock)
            writeQueue.sync { fd = -1 }
            close(sock)
            DispatchQueue.main.async { self.onConnectionChange?(false) }
            Thread.sleep(forTimeInterval: reconnectDelay)
        }
    }

    /// Returns a connected socket fd, or -1.
    static func connectUnix(_ path: String) -> Int32 {
        let sock = socket(AF_UNIX, SOCK_STREAM, 0)
        guard sock >= 0 else { return -1 }
        var addr = sockaddr_un()
        addr.sun_family = sa_family_t(AF_UNIX)
        let capacity = MemoryLayout.size(ofValue: addr.sun_path)
        withUnsafeMutableBytes(of: &addr.sun_path) { raw in
            path.utf8CString.withUnsafeBytes { src in
                raw.copyMemory(from: UnsafeRawBufferPointer(rebasing: src.prefix(capacity - 1)))
            }
        }
        let ok = withUnsafePointer(to: &addr) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                connect(sock, $0, socklen_t(MemoryLayout<sockaddr_un>.size))
            }
        }
        if ok != 0 {
            close(sock)
            return -1
        }
        return sock
    }

    private func readLines(_ sock: Int32) {
        var pending = Data()
        var buf = [UInt8](repeating: 0, count: 8192)
        while true {
            let n = read(sock, &buf, buf.count)
            if n <= 0 { return }
            pending.append(buf, count: n)
            while let newline = pending.firstIndex(of: 0x0A) {
                let line = pending[pending.startIndex..<newline]
                pending.removeSubrange(pending.startIndex...newline)
                // Malformed lines are dropped; unknown types arrive as .unknown.
                if let event = try? decoder.decode(BrainEvent.self, from: line) {
                    DispatchQueue.main.async { self.onEvent?(event) }
                }
            }
        }
    }
}
