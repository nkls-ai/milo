import AppKit
import ScreenCaptureKit
import UniformTypeIdentifiers

/// Screenshots through ScreenCaptureKit, downscaled and saved as private PNGs under ~/Milo/state/screens.
/// Milo's own windows (the character, the "working" frame) are left out of every picture.
final class ScreenShots {
    struct Shot {
        let url: URL
        /// Size of the PNG in pixels.
        let width: Int
        let height: Int
        /// What it shows, in global points with the origin top-left.
        let frame: CGRect

        /// A pixel of the PNG as a global point.
        func point(x: Double, y: Double) -> CGPoint {
            CGPoint(x: frame.minX + x * frame.width / Double(width), y: frame.minY + y * frame.height / Double(height))
        }
    }

    enum Failure: Error {
        case noPermission, nothingToCapture, failed(String)

        var message: String {
            switch self {
            case .noPermission:
                "I can't take screenshots yet. Turn on Screen Recording for Milo in System Settings › Privacy & Security › Screen & System Audio Recording, then quit and reopen Milo."
            case .nothingToCapture: "There is no window to take a picture of."
            case let .failed(why): "The screenshot didn't work: \(why)"
            }
        }
    }

    static let longSide = 1400.0
    let folder: URL
    let keep: Int
    private var askedForPermission = false

    init(folder: URL, keep: Int = 30) {
        self.folder = folder
        self.keep = keep
    }

    /// Asks macOS for Screen Recording once per launch; later calls only check.
    func permitted() -> Bool {
        if CGPreflightScreenCaptureAccess() { return true }
        if !askedForPermission {
            askedForPermission = true
            CGRequestScreenCaptureAccess()
        }
        return false
    }

    /// The app's window closest to `near` (its Accessibility frame), else its largest one.
    func window(pid: pid_t, near: CGRect?) async throws -> Shot {
        guard permitted() else { throw Failure.noPermission }
        let content = try await shareable()
        let windows = content.windows.filter { $0.owningApplication?.processID == pid && $0.windowLayer == 0 && $0.isOnScreen }
        let window = near.flatMap { target in
            windows.min { distance($0.frame, target) < distance($1.frame, target) }
        } ?? windows.max { $0.frame.width * $0.frame.height < $1.frame.width * $1.frame.height }
        guard let window else { throw Failure.nothingToCapture }
        return try await capture(SCContentFilter(desktopIndependentWindow: window), frame: window.frame, prefix: "look")
    }

    /// The display showing `point` (or the main one), without Milo's windows.
    func display(containing point: CGPoint?) async throws -> Shot {
        guard permitted() else { throw Failure.noPermission }
        let content = try await shareable()
        let display = point.flatMap { p in content.displays.first { $0.frame.contains(p) } } ?? content.displays.first
        guard let display else { throw Failure.nothingToCapture }
        let mine = content.windows.filter { $0.owningApplication?.processID == getpid() }
        return try await capture(SCContentFilter(display: display, excludingWindows: mine), frame: display.frame,
                                 prefix: "screen")
    }

    private func shareable() async throws -> SCShareableContent {
        do {
            return try await SCShareableContent.excludingDesktopWindows(true, onScreenWindowsOnly: true)
        } catch {
            throw CGPreflightScreenCaptureAccess() ? Failure.failed(error.localizedDescription) : Failure.noPermission
        }
    }

    private func capture(_ filter: SCContentFilter, frame: CGRect, prefix: String) async throws -> Shot {
        let scale = min(Double(filter.pointPixelScale), Self.longSide / max(frame.width, frame.height, 1))
        let config = SCStreamConfiguration()
        config.width = max(1, Int((frame.width * scale).rounded()))
        config.height = max(1, Int((frame.height * scale).rounded()))
        config.showsCursor = false
        config.scalesToFit = true
        let image: CGImage
        do {
            image = try await SCScreenshotManager.captureImage(contentFilter: filter, configuration: config)
        } catch {
            throw Failure.failed(error.localizedDescription)
        }
        let url = try save(image, prefix: prefix)
        prune()
        return Shot(url: url, width: image.width, height: image.height, frame: frame)
    }

    private func save(_ image: CGImage, prefix: String) throws -> URL {
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true,
                                                attributes: [.posixPermissions: 0o700])
        let data = NSMutableData()
        guard let destination = CGImageDestinationCreateWithData(data, UTType.png.identifier as CFString, 1, nil) else {
            throw Failure.failed("could not encode the picture")
        }
        CGImageDestinationAddImage(destination, image, nil)
        guard CGImageDestinationFinalize(destination) else { throw Failure.failed("could not encode the picture") }
        let stamp = Int(Date().timeIntervalSince1970 * 1000)
        let url = folder.appendingPathComponent("\(prefix)-\(stamp).png")
        guard FileManager.default.createFile(atPath: url.path, contents: data as Data,
                                             attributes: [.posixPermissions: 0o600]) else {
            throw Failure.failed("could not save the picture")
        }
        return url
    }

    /// Keeps the newest `keep` pictures.
    func prune() {
        let files = (try? FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: nil)) ?? []
        let pngs = files.filter { $0.pathExtension == "png" }.sorted { $0.lastPathComponent > $1.lastPathComponent }
        for old in pngs.dropFirst(keep) { try? FileManager.default.removeItem(at: old) }
    }

    private func distance(_ a: CGRect, _ b: CGRect) -> Double {
        abs(a.minX - b.minX) + abs(a.minY - b.minY) + abs(a.width - b.width) + abs(a.height - b.height)
    }
}
