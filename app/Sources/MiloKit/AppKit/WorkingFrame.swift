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
    var theme = Theme.for(.pip)
    @State private var glow = false

    var body: some View {
        ZStack(alignment: .top) {
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .strokeBorder(LinearGradient(colors: [theme.glow, theme.accent, theme.primary],
                                             startPoint: .topLeading, endPoint: .bottomTrailing),
                              lineWidth: 5)
                .opacity(glow ? 0.85 : 0.45)
                .blur(radius: 1.5)
            Text("Milo is borrowing your mouse · move it or press esc to take over")
                .font(.system(size: 12, weight: .medium))
                .padding(.horizontal, 12)
                .padding(.vertical, 5)
                .background(Capsule().fill(.regularMaterial))
                .padding(.top, 34)
        }
        .ignoresSafeArea()
        .onAppear {
            withAnimation(.easeInOut(duration: 1.4).repeatForever(autoreverses: true)) { glow = true }
        }
    }
}
