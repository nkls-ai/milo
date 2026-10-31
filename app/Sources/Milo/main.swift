// Composition root: the only place that names concrete adapters.
import AppKit
import MiloKit

// A write to a socket the brain just closed must not kill the app.
signal(SIGPIPE, SIG_IGN)

let environment = ProcessInfo.processInfo.environment
let paths = MiloPaths.resolve(environment: environment)
let scheduler = MainQueueScheduler()
let brainDir = UVBrainLauncher.resolveBrainDir(
    environment: environment,
    infoPlistValue: Bundle.main.object(forInfoDictionaryKey: "MiloBrainDir") as? String)

let model = MiloModel(scheduler: scheduler)
// A copy with its own MILO_HOME shares the bundle id: keep its notes apart.
let defaults = environment["MILO_HOME"].flatMap { home in
    UserDefaults(suiteName: "dev.nkls.milo.home" + home.replacingOccurrences(of: "/", with: "."))
} ?? .standard
// What macOS lets Milo do, checked before he first needs it (ADR 25), and the apps he asked about.
let access = MacAppAccess()
let controlledApps = ControlledApps(defaults: defaults)
// The music player before Calendar and Reminders: its ops need no EventKit (ADR 29).
let accessRequests = AccessRequests(source: access, apps: controlledApps,
                                    next: MediaRequests(player: SystemMediaPlayer(), next: EventKitConnections()))
let brain = UnixSocketBrainClient(socketPath: paths.socket.path)
let screen = ScreenController(
    model: model, brain: brain,
    ports: ScreenPorts(reader: SystemScreenReader(screensFolder: paths.screens),
                       hands: MacHands(screensFolder: paths.screens, places: { access.places(for: $0) }),
                       input: NSEventInputMonitor(), hotkey: CarbonHotkey(),
                       cursor: CursorOverlay(model: model), windows: MacWindowWatcher()),
    toAppKit: OverlayPanel.appKitPoint)
let controller = MiloController(
    model: model,
    brain: brain,
    launcher: UVBrainLauncher(
        configuration: .init(brainDir: brainDir, logURL: paths.brainStdoutLog, lockURL: paths.brainLock),
        scheduler: scheduler),
    inserter: PasteboardInserter(scheduler: scheduler),
    keys: NSEventKeySource(),
    context: WorkspaceContextProvider(),
    accessibility: SystemAccessibilityPermission(),
    scheduler: scheduler,
    connections: accessRequests,
    // The setup window explains Accessibility with the other permissions, so no system dialog on top of it.
    // MILO_DROWSY_AFTER (seconds) lets a test instance fall asleep sooner, to measure him asleep.
    settings: MiloController.Settings(drowsyAfter: environment["MILO_DROWSY_AFTER"].flatMap(Double.init) ?? 600,
                                      promptForAccessibility: false),
    screen: screen,
    meetings: MeetingController(model: model, brain: brain, recorder: MacMeetingRecorder(brainLock: paths.brainLock),
                                signals: MacCallSignals(), scheduler: scheduler, hotkey: CarbonHotkey()),
    pasteWatcher: PasteWatcher(reader: AXFocusedText(), words: SpellCheckWords(), scheduler: scheduler))

accessRequests.onAsking = { screen.systemAsks($0) }

// `[hands] show_window` from the brain's settings; on until the brain says otherwise.
screen.showWindow = { controller.settingsModel.value("hands", "show_window")?.bool ?? true }

// Windows and the status item are created once the app has finished launching.
var panel: OverlayPanel?
var menu: StatusMenu?
var conversation: ConversationWindow?
var workingFrame: WorkingFrame?
var workingOutline: WorkingOutline?

let lifecycle = AppLifecycle(
    onLaunch: {
        let overlay = OverlayPanel(model: model)
        overlay.placeBottomRight()
        overlay.orderFrontRegardless()
        workingFrame = WorkingFrame(model: model)
        workingOutline = WorkingOutline(model: model)
        let window = ConversationWindow(controller: controller)
        let settingsWindow = SettingsWindow(controller: controller, dictionary: paths.dictionary)
        window.onSettings = { settingsWindow.open() }
        overlay.onClick = { window.toggle() }
        model.onOpenHelper = { window.show(helper: $0) }
        let setupWindow = SetupWindow(
            setup: SetupModel(permissions: SystemPermissions(), scheduler: scheduler,
                              dictateKey: controller.bindings.dictate.displayName, defaults: defaults),
            model: model, apps: controlledApps, access: access)
        // "Fix it" under a bubble about a missing permission opens the window with a button for each.
        model.onBubbleAction = { action in
            switch action {
            case .permissions: setupWindow.open()
            case .microphone: SystemPermissions().openSettings(.microphone)
            case .callAudio: SystemPermissions().openSettings(.screenRecording)
            case .copyConsent: break  // MiloModel copies it itself
            case let .openMeeting(id): window.show(meeting: id)
            // Automation has a switch per app under Milo; Accessibility and Screen Recording have the
            // permissions window, with its drag tile and restart.
            case let .access(need, app): need == .control ? access.openSettings(need, app: app) : setupWindow.open()
            case .undo: break  // MiloModel sends it itself
            }
        }
        model.meeting.onOpen = { window.show(meeting: $0) }
        model.meeting.copy = { text in
            NSPasteboard.general.clearContents()
            NSPasteboard.general.setString(text, forType: .string)
        }
        let statusMenu = StatusMenu(controller: controller, panel: overlay, window: window, settings: settingsWindow,
                                    setup: setupWindow, paths: paths, apps: controlledApps, access: access)
        controller.onBindingsChange = {
            statusMenu.show($0)
            window.show($0)
            setupWindow.setup.dictateKey = $0.dictate.displayName
        }
        conversation = window
        panel = overlay
        menu = statusMenu
        controller.start()
        setupWindow.openIfNeeded()
    },
    onTerminate: { controller.stop() })

let app = NSApplication.shared
app.delegate = lifecycle
app.setActivationPolicy(.accessory)
app.run()
