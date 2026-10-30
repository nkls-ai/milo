import AppKit
import Combine
import SwiftUI

/// The Settings window. Opened from the menu bar and from the Milo window; closing only hides it.
public final class SettingsWindow: NSWindow {
    private let controller: MiloController
    private var restyle: AnyCancellable?

    /// `dictionary`: the file "Show the words" opens.
    public init(controller: MiloController, dictionary: URL? = nil) {
        self.controller = controller
        super.init(contentRect: NSRect(x: 0, y: 0, width: 500, height: 640),
                   styleMask: [.titled, .closable, .resizable, .miniaturizable, .fullSizeContentView], backing: .buffered, defer: true)
        title = "Milo Settings"
        titlebarAppearsTransparent = true
        isReleasedWhenClosed = false
        contentView = NSHostingView(rootView: SettingsView(
            settings: controller.settingsModel, model: controller.model,
            restart: { [weak controller] in controller?.restartBrain() },
            showWords: dictionary.map { url in { StatusMenu.openText(url) } })
            .themed(by: controller.model))
        restyle = controller.model.$character.sink { [weak self] in self?.backgroundColor = Theme.for($0).appKit.tint }
        if !setFrameUsingName(Self.frameName) { center() }
        setFrameAutosaveName(Self.frameName)
    }

    private static let frameName = "MiloSettingsWindow"

    public func open() {
        controller.settingsModel.refresh()
        // An accessory app has to activate itself to bring its window to the front.
        NSApp.activate(ignoringOtherApps: true)
        makeKeyAndOrderFront(nil)
    }
}
