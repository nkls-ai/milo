import AppKit
import Combine
import SwiftUI

/// The soft "Milo is working" frame around every screen while the worker acts. Clicks pass through it,
/// and screenshots leave it out.
public final class WorkingFrame {
    private var windows: [NSWindow] = []
    private var subscription: AnyCancellable?
    private var restyle: AnyCancellable?
    private var theme = Theme.for(.pip)

    public init(model: MiloModel) {
        // Only while Milo borrows the real mouse or keyboard: then any touch stops him, so the whole screen
        // says so. Background work shows the per-window outline instead (WorkingOutline).
        subscription = model.$handsBorrowed.removeDuplicates().receive(on: DispatchQueue.main).sink { [weak self] on in
            on ? self?.show() : self?.hide()
        }
        restyle = model.$character.removeDuplicates().sink { [weak self] in
            guard let self else { return }
            theme = Theme.for($0)
            if !windows.isEmpty { show() }  // showing: draw it again in the new colours
        }
    }

    private func show() {
        hide()
        for screen in NSScreen.screens {
            let window = NSWindow(contentRect: screen.frame, styleMask: [.borderless], backing: .buffered, defer: false)
            window.isOpaque = false
            window.backgroundColor = .clear
            window.hasShadow = false
            window.ignoresMouseEvents = true
            window.level = .statusBar
            window.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary, .ignoresCycle]
            window.contentView = NSHostingView(rootView: WorkingFrameView(theme: theme))
            window.setFrame(screen.frame, display: true)
            window.orderFrontRegardless()
            windows.append(window)
        }
    }

    private func hide() {
        windows.forEach { $0.orderOut(nil) }
        windows.removeAll()
    }
}

struct WorkingFrameView: View {
    static let label = "Milo is using your mouse. Move it or press esc to take over."
    var theme = Theme.for(.pip)

    var body: some View {
        ZStack(alignment: .top) {
            WorkingEdge(theme: theme, radius: 14, width: 5, blur: 1.5)
            WorkingTag(text: Self.label, theme: theme)
                .padding(.top, 34)
        }
        .ignoresSafeArea()
    }
}
