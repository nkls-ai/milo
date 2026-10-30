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
let brain = UnixSocketBrainClient(socketPath: paths.socket.path)
let screen = ScreenController(
    model: model, brain: brain,
    ports: ScreenPorts(reader: SystemScreenReader(screensFolder: paths.screens),
                       hands: MacHands(screensFolder: paths.screens),
                       input: NSEventInputMonitor(), hotkey: CarbonHotkey()),
    toAppKit: FlyFallback.appKitPoint)
let controller = MiloController(
    model: model,
    brain: brain,
    launcher: UVBrainLauncher(
        configuration: .init(brainDir: brainDir, logURL: paths.brainStdoutLog), scheduler: scheduler),
    inserter: PasteboardInserter(scheduler: scheduler),
    keys: NSEventKeySource(),
    context: WorkspaceContextProvider(),
    accessibility: SystemAccessibilityPermission(),
    scheduler: scheduler,
    screen: screen)

// Windows and the status item are created once the app has finished launching.
var panel: OverlayPanel?
var menu: StatusMenu?
var conversation: ConversationWindow?
var workingFrame: WorkingFrame?
var flyFallback: FlyFallback?

let lifecycle = AppLifecycle(
    onLaunch: {
        let overlay = OverlayPanel(model: model, answer: { screen.answer(yes: $0) })
        overlay.placeBottomRight()
        overlay.orderFrontRegardless()
        workingFrame = WorkingFrame(model: model)
        // Stands in until the character flies on his own; remove this line when it does.
        flyFallback = FlyFallback(model: model, panel: overlay)
        let window = ConversationWindow(controller: controller)
        overlay.onClick = { window.toggle() }
        let statusMenu = StatusMenu(controller: controller, panel: overlay, window: window, paths: paths)
        controller.onBindingsChange = { statusMenu.show($0); window.show($0) }
        conversation = window
        panel = overlay
        menu = statusMenu
        controller.start()
    },
    onTerminate: { controller.stop() })

let app = NSApplication.shared
app.delegate = lifecycle
app.setActivationPolicy(.accessory)
app.run()
