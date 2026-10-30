import AppKit
import Foundation
import SwiftUI
import Testing
@testable import MiloKit

/// Renders the overlay (bubble, pill, helpers, badges) in every state, for every skin, light and dark:
/// `MILO_RENDER_DIR=/tmp/milo-overlay swift test --filter OverlayRender`. `MILO_SKINS=pip,kit` renders only those.
@Suite(.enabled(if: ProcessInfo.processInfo.environment["MILO_RENDER_DIR"] != nil))
@MainActor
struct OverlayRenderTests {
    let dir = URL(fileURLWithPath: ProcessInfo.processInfo.environment["MILO_RENDER_DIR"] ?? "/tmp")

    /// One moment of the overlay, set up on a fresh model.
    struct Moment {
        var name: String
        var set: (MiloModel) -> Void
    }

    static let moments: [Moment] = [
        Moment(name: "01-idle") { _ in },
        Moment(name: "02-armed") { $0.press(.talk) },
        Moment(name: "03-listening") { m in
            m.press(.talk)
            m.apply(.state(.listening))
            for v in [0.1, 0.3, 0.6, 0.45, 0.2, 0.5, 0.7] { m.apply(.level(v)) }
        },
        Moment(name: "04-listening-words") { m in
            m.apply(.state(.listening))
            m.apply(.level(0.4))
            m.apply(.partial("Can you move my dentist appointment to Thursday"))
        },
        Moment(name: "05-dictating-handsfree") { m in
            m.apply(.state(.dictating))
            m.handsFree = .dictate
            m.apply(.level(0.3))
            m.apply(.partial("Dear Anna, thanks for the photos from the weekend, they made my day"))
        },
        Moment(name: "06-got-it") { m in
            m.apply(.state(.listening))
            m.release(.talk)
        },
        Moment(name: "07-transcribing") { m in
            m.apply(.state(.transcribing))
            m.apply(.partial("Can you move my dentist appointment to Thursday"))
        },
        Moment(name: "08-thinking") { m in
            m.apply(.heard("Can you move my dentist appointment to Thursday?"))
            m.apply(.state(.thinking))
        },
        Moment(name: "09-speaking") { m in
            m.apply(.heard("Do I have anything this afternoon?"))
            m.apply(.state(.speaking))
            m.apply(.bubble("Just the dentist at four. I'll remind you at half past three."))
        },
        Moment(name: "09b-spoken") { m in
            m.apply(.heard("Do I have anything this afternoon?"))
            m.apply(.state(.speaking))
            m.apply(.bubble("Just the dentist at four."))
            m.apply(.bubble("Just the dentist at four. I'll remind you at half past three."))
            m.apply(.state(.idle))
        },
        Moment(name: "10-speaking-long") { m in
            m.apply(.state(.speaking))
            m.apply(.bubble("""
                Open the photo in Preview, then choose Tools and Adjust Size. Pick a width of about 1600 pixels and \
                keep "Scale proportionally" ticked, so nothing gets squashed. Save it under a new name so the \
                original stays as it was. If there are many photos, select them all in the sidebar first.
                """))
        },
        Moment(name: "11-confirm") { m in
            m.apply(.confirm(id: "q", question: "Send the email to Dr. Lee about moving Thursday's appointment?"))
        },
        Moment(name: "12-error") { m in
            m.show(MiloController.pasteBlocked, action: .permissions)
        },
        Moment(name: "13-status") { m in
            m.apply(.state(.thinking))
            m.apply(.status("Looking at your calendar…"))
        },
        Moment(name: "14-pasted") { m in
            m.pasted("Thanks for the photos, they made my day.")
        },
        Moment(name: "15-helpers") { m in
            m.apply(.helpers(HelperRenderTests.three))
        },
        Moment(name: "16-looking") { m in
            m.apply(.looking(true))
            m.apply(.state(.thinking))
        },
        Moment(name: "17-offline") { m in
            m.connected = false
        },
    ]

    @Test func renderEveryMoment() throws {
        _ = NSApplication.shared
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        for dark in [false, true] {
            for moment in Self.moments {
                let model = MiloModel(scheduler: ManualScheduler())
                model.connected = true
                moment.set(model)
                try render(model, name: "overlay-\(dark ? "dark" : "light")-\(moment.name)", dark: dark)
            }
        }
    }

    private func render(_ model: MiloModel, name: String, dark: Bool) throws {
        let size = OverlayPanel.size
        let view = ZStack {
            Wallpaper(dark: dark)
            OverlayView(model: model)
        }
        .frame(width: size.width, height: size.height)
        let host = NSHostingView(rootView: view)
        host.frame = NSRect(origin: .zero, size: size)
        let window = NSWindow(contentRect: host.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.appearance = NSAppearance(named: dark ? .darkAqua : .aqua)
        window.contentView = host
        host.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.35))
        let rep = try #require(host.bitmapImageRepForCachingDisplay(in: host.bounds))
        host.cacheDisplay(in: host.bounds, to: rep)
        let png = try #require(rep.representation(using: .png, properties: [:]))
        try png.write(to: dir.appendingPathComponent("\(name).png"))
    }
}
