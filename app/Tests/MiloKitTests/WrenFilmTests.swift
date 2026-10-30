import AppKit
import ImageIO
import Testing
import UniformTypeIdentifiers
@testable import MiloKit

/// Plays scripted scenes through the director and the springs and records them as GIFs and filmstrips,
/// to judge Milo's motion frame by frame:
/// `MILO_RENDER_DIR=/tmp/milo-wren swift test --filter WrenFilm`. `MILO_SCENES=hop,flight` picks scenes.
@Suite(.enabled(if: ProcessInfo.processInfo.environment["MILO_RENDER_DIR"] != nil))
struct WrenFilmTests {
    let dir = URL(fileURLWithPath: ProcessInfo.processInfo.environment["MILO_RENDER_DIR"] ?? "/tmp")

    struct Scene {
        var name: String
        var length: Double
        /// What the figure is told at each moment.
        var input: (Double) -> FigureInput
    }

    /// A voice level that moves like speech: syllables about 5 a second, phrases with pauses.
    static func voice(_ t: Double) -> Double {
        let syllable = max(0, sin(t * 2 * .pi * 4.7) * 0.6 + sin(t * 2 * .pi * 2.3 + 1) * 0.4)
        let phrase = (sin(t * 2 * .pi * 0.45) > -0.6) ? 1.0 : 0.1
        return min(1, syllable * phrase * 0.9)
    }

    static let scenes: [Scene] = [
        Scene(name: "idle", length: 6) { t in
            var i = FigureInput()
            i.pose.blink = (1.0..<1.12).contains(t) || (4.4..<4.52).contains(t)
            if (1.8..<2.4).contains(t) { i.pose.habit = .bob }
            if (3.0..<3.6).contains(t) { i.pose.habit = .tailFlick }
            if t > 3.8 { i.pose.gaze = CGVector(dx: -0.7, dy: 0.2) }
            return i
        },
        Scene(name: "habits", length: 5.5) { t in
            var i = FigureInput()
            if (0.3..<1.5).contains(t) { i.pose.habit = .scarfTug }
            if (1.9..<2.5).contains(t) { i.pose.habit = .ruffle }
            if (3.0..<4.2).contains(t) { i.pose.habit = .wingStretch }
            return i
        },
        Scene(name: "conversation", length: 9) { t in
            var i = FigureInput()
            if t > 0.5 && t < 3 {
                i.state = .listening
                i.level = max(0, sin(t * 9) * 0.5 + 0.3)
                i.words = Int((t - 0.5) * 2.5)
                i.pose.lean = -1
                i.pose.tilt = -4
                i.pose.gaze = CGVector(dx: -0.15, dy: -0.1)
            } else if t >= 3 && t < 4.5 {
                i.state = .thinking
                i.emotion = .thinking
                i.pose.gaze = CGVector(dx: t < 3.8 ? 0.7 : -0.7, dy: -0.75)
            } else if t >= 4.5 && t < 7.5 {
                i.state = .speaking
                i.level = voice(t - 4.5)
                i.pose.gaze = t < 5.5 ? CGVector(dx: -0.3, dy: -0.8) : .zero
            } else if t >= 7.5 {
                i.emotion = .happy
            }
            return i
        },
        Scene(name: "flight", length: 4.5) { t in
            var i = FigureInput()
            if t > 0.4 && t < 2.4 { i.flight = .flying(heading: CGVector(dx: -0.8, dy: -0.6)) }
            if t >= 2.4 { i.flight = .pointing(toward: CGVector(dx: -0.97, dy: -0.24)) }
            return i
        },
        Scene(name: "work", length: 5) { t in
            var i = FigureInput()
            if t > 0.3 {
                i.working = true
                i.flight = .pointing(toward: CGVector(dx: -0.6, dy: 0.8))
            }
            if t > 3.2 { i.emotion = .happy }
            return i
        },
        Scene(name: "asking", length: 5) { t in
            var i = FigureInput()
            i.asking = t > 0.3 && t < 4.2
            return i
        },
        Scene(name: "moods", length: 7) { t in
            var i = FigureInput()
            i.emotion = t < 0.3 ? .neutral : t < 2 ? .concerned : t < 3.7 ? .sad : t < 5.4 ? .confused : .excited
            return i
        },
        Scene(name: "sleep", length: 6) { t in
            var i = FigureInput()
            i.pose.yawn = (0.4..<1.6).contains(t)
            i.asleep = t > 0.4 && t < 4.4
            i.emotion = .neutral
            return i
        },
    ]

    @Test func recordScenes() throws {
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let wanted = ProcessInfo.processInfo.environment["MILO_SCENES"]?.split(separator: ",").map(String.init) ?? []
        for scene in Self.scenes where wanted.isEmpty || wanted.contains(scene.name) {
            let frames = Self.film(scene, fps: 30)
            if ProcessInfo.processInfo.environment["MILO_DUMP"] != nil {
                for f in frames {
                    let p = f.pose
                    print(String(format: "%.2f sq %.3f lift %.1f lean %.1f fly %.2f wing %.0f/%.0f tail %.1f scarf %.1f headT %.1f headY %.1f",
                                 f.time, p.squash, p.lift, p.lean, p.fly, p.wingL, p.wingR, p.tail, p.scarf, p.headTilt, p.headY))
                }
            }
            try gif(frames.map(\.image), name: "wren-\(scene.name)")
            try strip(frames.enumerated().filter { $0.offset % 3 == 0 }.map(\.element.image), name: "wren-\(scene.name)-strip")
            // `MILO_ZOOM=2.8-3.6` also saves every frame in that span at full size, for close reading.
            if let span = ProcessInfo.processInfo.environment["MILO_ZOOM"]?.split(separator: "-").compactMap({ Double($0) }),
               span.count == 2 {
                try strip(frames.filter { $0.time >= span[0] && $0.time <= span[1] }.map(\.image),
                          name: "wren-\(scene.name)-zoom", half: false, cols: 6)
            }
        }
    }

    /// Runs a scene and draws it `fps` times a second.
    static func film(_ scene: Scene, fps: Double, points: CGFloat = 120, scale: CGFloat = 2) -> [(time: Double, pose: WrenPose, image: CGImage)] {
        var director = WrenDirector(seed: 3)
        var motion = WrenMotion()
        var frames: [(Double, WrenPose, CGImage)] = []
        let dt = 1.0 / 120
        var t = 0.0, next = 0.0
        director.direct(scene.input(0), motion: &motion, at: 0)
        motion.snap()
        while t <= scene.length {
            director.direct(scene.input(t), motion: &motion, at: t)
            motion.advance(by: dt)
            t += dt
            if t >= next {
                next += 1 / fps
                let bg = WrenColors.rgb(0xE9ECF1)
                if let image = WrenRender.image(motion.pose, points: points, scale: scale, background: bg) {
                    frames.append((t, motion.pose, image))
                }
            }
        }
        return frames
    }

    private func gif(_ images: [CGImage], name: String) throws {
        let url = dir.appendingPathComponent("\(name).gif")
        let dest = try #require(CGImageDestinationCreateWithURL(url as CFURL, UTType.gif.identifier as CFString, images.count, nil))
        CGImageDestinationSetProperties(dest, [kCGImagePropertyGIFDictionary: [kCGImagePropertyGIFLoopCount: 0]] as CFDictionary)
        for image in images {
            CGImageDestinationAddImage(dest, image, [kCGImagePropertyGIFDictionary: [kCGImagePropertyGIFDelayTime: 1.0 / 30]] as CFDictionary)
        }
        #expect(CGImageDestinationFinalize(dest))
    }

    private func strip(_ images: [CGImage], name: String, half: Bool = true, cols: Int = 10) throws {
        guard let first = images.first else { return }
        let w = first.width / (half ? 2 : 1), h = first.height / (half ? 2 : 1)
        let rows = (images.count + cols - 1) / cols
        let ctx = try #require(CGContext(data: nil, width: w * cols, height: h * rows, bitsPerComponent: 8, bytesPerRow: 0,
                                         space: CGColorSpace(name: CGColorSpace.sRGB)!,
                                         bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue))
        ctx.setFillColor(WrenColors.rgb(0xE9ECF1))
        ctx.fill(CGRect(x: 0, y: 0, width: w * cols, height: h * rows))
        ctx.interpolationQuality = .high
        for (i, image) in images.enumerated() {
            ctx.draw(image, in: CGRect(x: (i % cols) * w, y: (rows - 1 - i / cols) * h, width: w, height: h))
        }
        let image = try #require(ctx.makeImage())
        let png = try #require(NSBitmapImageRep(cgImage: image).representation(using: .png, properties: [:]))
        try png.write(to: dir.appendingPathComponent("\(name).png"))
    }
}
