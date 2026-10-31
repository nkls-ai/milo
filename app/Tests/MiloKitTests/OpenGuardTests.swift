import Foundation
import Testing
@testable import MiloKit

/// Opening at once (ADR 28): web pages and documents open, anything that would run code doesn't.
@Suite struct OpenGuardTests {
    @Test func onlyWebPagesOpenAsAddresses() {
        #expect(OpenGuard.refuses(url: "https://www.youtube.com") == nil)
        #expect(OpenGuard.refuses(url: "http://localhost:8080/x") == nil)
        for bad in ["shortcuts://run-shortcut?name=Wipe", "file:///etc/passwd", "javascript:alert(1)",
                    "x-apple.systempreferences:com.apple.preference.security", "https://", "youtube.com"] {
            #expect(OpenGuard.refuses(url: bad) != nil, "\(bad)")
        }
    }

    @Test func documentsAndFoldersOpen() {
        #expect(OpenGuard.refuses(path: "/Users/you/Downloads", isDirectory: true, types: ["public.folder"],
                                  executable: false) == nil)
        #expect(OpenGuard.refuses(path: "/Users/you/Budget.xlsx", isDirectory: false,
                                  types: ["org.openxmlformats.spreadsheetml.sheet", "public.data"], executable: false) == nil)
        #expect(OpenGuard.refuses(path: "/Volumes/USB/Report.pdf", isDirectory: false,
                                  types: ["com.adobe.pdf", "public.data"], executable: true) == nil,
                "a PDF with the executable bit (from a USB stick) is still a PDF")
    }

    @Test func whatWouldRunCodeIsRefused() {
        #expect(OpenGuard.refuses(path: "/Users/you/Downloads/Installer.app", isDirectory: true,
                                  types: ["com.apple.application-bundle"], executable: true) != nil)
        #expect(OpenGuard.refuses(path: "/Users/you/Downloads/run.command", isDirectory: false,
                                  types: ["com.apple.terminal.shell-script"], executable: false) != nil)
        #expect(OpenGuard.refuses(path: "/Users/you/Downloads/setup.pkg", isDirectory: false, types: [],
                                  executable: false) != nil)
        #expect(OpenGuard.refuses(path: "/Users/you/Downloads/tool", isDirectory: false, types: ["public.data"],
                                  executable: true) != nil, "a bare program")
        #expect(OpenGuard.refuses(path: "/Users/you/x.fileloc", isDirectory: false, types: [], executable: false) != nil)
        #expect(OpenGuard.refuses(path: "/Users/you/Tool.plugin", isDirectory: true,
                                  types: ["com.apple.plugin", "com.apple.bundle", "com.apple.package"],
                                  executable: false) != nil, "a bundle is a folder that runs code")
        #expect(OpenGuard.refuses(path: "/Users/you/Renamed", isDirectory: true,
                                  types: ["com.apple.application-bundle", "com.apple.bundle"], executable: false) != nil,
                "an app without .app in its name")
    }

    @Test func internetLocationsDontSmuggleAnAddressPastTheSchemeCheck() {
        for name in ["Wipe.webloc", "x.inetloc", "x.url", "x.mailloc"] {
            #expect(OpenGuard.refuses(path: "/Users/you/Downloads/\(name)", isDirectory: false, types: [],
                                      executable: false) != nil, "\(name)")
        }
        #expect(OpenGuard.refuses(path: "/Users/you/Downloads/link", isDirectory: false,
                                  types: ["com.apple.web-internet-location"], executable: false) != nil)
    }

    @Test func aDocumentPackageIsntABundle() {
        #expect(OpenGuard.refuses(path: "/Users/you/Letter.pages", isDirectory: true,
                                  types: ["com.apple.iwork.pages.sffpages", "com.apple.package", "public.directory"],
                                  executable: false) == nil)
    }

    @Test func waitingStopsAtTheFirstYesOrAtTheLimit() {
        var calls = 0
        #expect(OpenGuard.wait(timeout: 1, poll: 0.001) { calls += 1; return calls == 3 })
        #expect(calls == 3)
        let start = Date()
        #expect(!OpenGuard.wait(timeout: 0.05, poll: 0.01) { false })
        #expect(Date().timeIntervalSince(start) < 0.5)
    }

    /// The talker's <open> is meant to be instant (ADR 28): it never waits behind a helper's script on the hands
    /// queue. Here a refused address (it never reaches Launch Services) answers while a 1 s script still runs.
    @Test func anOpenDoesntWaitBehindAScript() async {
        let hands = MacHands(screensFolder: FileManager.default.temporaryDirectory)
        let started = Date()
        let script = Task { await withCheckedContinuation { done in
            hands.perform("run_applescript", args: ["script": .string("delay 1")]) { _ in done.resume() }
        } }
        try? await Task.sleep(for: .milliseconds(100))  // the script is on its queue
        let opened: Result<[String: JSONValue], HandsFailure> = await withCheckedContinuation { done in
            hands.perform("open_url", args: ["url": .string("shortcuts://run-shortcut?name=x")]) { done.resume(returning: $0) }
        }
        #expect(Date().timeIntervalSince(started) < 0.8, "answered while the script still ran")
        if case .success = opened { Issue.record("another scheme must never open") }
        await script.value
    }

    @Test func openingAndFocusingNeedNoAccessibility() {
        for tool in ["open_url", "open_file", "focus_app"] {
            #expect(!MacHands.needsAccessibility(tool, [:]))
        }
    }
}
