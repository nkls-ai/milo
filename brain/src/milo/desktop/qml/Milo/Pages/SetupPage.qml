import QtQuick
import QtQuick.Layouts
import QtQuick.Shapes
import Milo
import Milo.Controls

// Setting Milo up (SetupView.swift), and on Windows and Linux "Connections & models": which CLI or API he talks
// with and which does his helper jobs (it replaces desktop/setup.py's dialog). Ends with trying him out.
//
// Inputs
//   setupBackend: the SetupBackend QObject (desktop/viewmodels/setup.py), the page's only way into Python: it reads
//                 the current choice and which CLIs are installed, checks a choice and saves it. null in previews.
//   providers:    without a backend, what to show instead: {selection: {chat, helper, endpoint, model, keyRef},
//                 clis: {chat_claude: {available, detail}, ...}, configError}. Display only; nothing saves.
//   rows:         permissions to grant, [{permission, title, reason, state: "granted"|"denied"|"notAsked",
//                 optional, button}]; empty on Windows and Linux, where Milo needs none.
//   dictateKey:   the dictate key's name ("Right Ctrl").   tried: Milo heard a first dictation.
// Output
//   action("fix", permission) for a permission's button, action("saved", null) once a choice was saved (the window
//   restarts the brain; SetupBackend.saved says the same), action("done", null) for Done.
Item {
    id: page
    property QtObject setupBackend: null
    property var providers: null
    property var rows: []
    property string dictateKey: "fn"
    property bool tried: false
    signal command(var message)
    signal action(string name, var value)

    // What the backend knows, or the preview's stand-in.
    readonly property var source: setupBackend
        ? { selection: setupBackend.selection, clis: setupBackend.clis, configError: setupBackend.configError,
            needsSetup: setupBackend.needsSetup }
        : providers || { selection: {}, clis: {}, configError: "", needsSetup: true }

    // The user's choice, as typed; starts from the saved one.
    property string chat: "claude_live"
    property string helper: "codex"
    property alias endpoint: modelSource.endpoint
    property alias model: modelSource.model
    property alias keyRef: modelSource.keyRef
    property alias key: modelSource.key
    property string saveError: ""
    function load() {
        const s = source.selection || {}
        chat = s.chat || "claude_live"
        helper = s.helper || "codex"
        modelSource.load(s)
    }
    Component.onCompleted: {
        load()
        if (setupBackend) { setupBackend.detect(); modelSource.list() }
    }

    // `key` is a key the user pasted: it goes only to the backend, which saves it alone in Milo/secrets.
    readonly property var choice: ({ chat: chat, helper: helper, endpoint: endpoint, model: model, keyRef: keyRef.trim(),
                                    key: key })
    readonly property string problem: source.configError ? source.configError
                                    : saveError ? saveError
                                    : setupBackend ? setupBackend.validate(choice) : ""
    onChoiceChanged: saveError = ""

    readonly property var required: (rows || []).filter(r => !r.optional)
    readonly property var optional: (rows || []).filter(r => !!r.optional)
    readonly property bool ready: required.every(r => r.state === "granted") && !source.needsSetup

    function clis(key) { return (source.clis || {})[key] || { available: false, detail: "" } }
    function save() {
        if (!setupBackend) return
        if (setupBackend.save(choice)) {
            key = ""  // saved in its file; the field never holds it longer
            action("saved", null)
        } else saveError = setupBackend.lastError
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        MiloScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            leftPadding: 22
            rightPadding: 22
            topPadding: 22
            bottomPadding: 22
            maxContentWidth: 620
            spacing: 14

            // ---- hello
            RowLayout {
                Layout.bottomMargin: 6
                spacing: 14
                Item {
                    implicitWidth: 74
                    implicitHeight: 74
                    // A soft glow behind him.
                    SmoothShape {
                        anchors.centerIn: parent
                        width: 110
                        height: 110
                        ShapePath {
                            strokeColor: "transparent"
                            fillGradient: RadialGradient {
                                centerX: 55; centerY: 55; centerRadius: 50; focalX: 55; focalY: 55; focalRadius: 4
                                GradientStop { position: 0; color: Tones.fade(Theme.glow, 0.45) }
                                GradientStop { position: 1; color: Tones.fade(Theme.glow, 0) }
                            }
                            PathAngleArc { centerX: 55; centerY: 55; radiusX: 55; radiusY: 55; sweepAngle: 360 }
                        }
                    }
                    Wren { anchors.fill: parent; emotion: page.ready ? "excited" : "happy"; still: true }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 5
                    MiloText {
                        text: page.ready ? "All set. Thank you!" : "Hi! Let's get me ready."
                        size: 22; weight: "bold"; rounded: true
                    }
                    MiloText {
                        Layout.fillWidth: true
                        text: page.required.length > 0
                              ? "Each button takes you to the right switch in your settings. Turn me on there and come back: I'll tick it off."
                              : "Dictation runs locally. Talking and helper jobs use the provider you choose."
                        tone: 0.65
                        wrapMode: Text.WordWrap
                    }
                }
            }

            // ---- permissions, where the system has any
            Repeater { model: page.required; PermissionCard { row: modelData; onFix: page.action("fix", modelData.permission) } }
            MiloText {
                visible: page.optional.length > 0
                Layout.topMargin: 10
                Layout.leftMargin: 4
                text: "If you'd like Milo to help with these too"
                weight: "semibold"; rounded: true; tone: 0.7
            }
            Repeater { model: page.optional; PermissionCard { row: modelData; onFix: page.action("fix", modelData.permission) } }

            // ---- connections & models
            MiloText {
                Layout.topMargin: 6
                Layout.leftMargin: 4
                text: "Connections & models"
                weight: "semibold"; rounded: true; tone: 0.7
            }
            Card {
                padding: 12
                CardHeading { icon: "bubble.left.and.bubble.right"; title: "Talking"; detail: "What Milo says, and how he understands you." }
                ChoiceList {
                    objectName: "talking"
                    name: "Talking"
                    choices: [{ value: "claude_live", label: "Claude CLI" }, { value: "codex_live", label: "Codex CLI" },
                              { value: "openai_compat", label: "OpenAI-compatible API or local server" },
                              { value: "none", label: "Dictation only" }]
                        .concat(["claude_live", "codex_live", "openai_compat", "none"].indexOf(page.chat) < 0
                                ? [{ value: page.chat, label: "Current provider: " + page.chat }] : [])
                    selected: page.chat
                    onChosen: value => page.chat = value
                }
                Flow {
                    Layout.fillWidth: true
                    Layout.leftMargin: 26
                    spacing: 16
                    CliStatus { name: "Claude for talking"; status: page.clis("chat_claude") }
                    CliStatus { name: "Codex for talking"; status: page.clis("chat_codex") }
                }
                Appear {
                    Layout.fillWidth: true
                    shown: page.chat === "openai_compat"
                    visible: shown
                    ModelSource {
                        id: modelSource
                        width: parent.width
                        backend: page.setupBackend
                    }
                }
            }
            Card {
                padding: 12
                CardHeading { icon: "wrench"; title: "Helper jobs"; detail: "The real work Milo hands to a helper." }
                ChoiceList {
                    objectName: "helpers"
                    name: "Helper jobs"
                    choices: [{ value: "codex", label: "Codex CLI" }, { value: "claude", label: "Claude CLI" },
                              { value: "none", label: "Disabled" }]
                        .concat(["codex", "claude", "none"].indexOf(page.helper) < 0
                                ? [{ value: page.helper, label: "Current provider: " + page.helper }] : [])
                    selected: page.helper
                    onChosen: value => page.helper = value
                }
                Flow {
                    Layout.fillWidth: true
                    Layout.leftMargin: 26
                    spacing: 16
                    CliStatus { name: "Codex helpers"; status: page.clis("helper_codex") }
                    CliStatus { name: "Claude helpers"; status: page.clis("helper_claude") }
                }
                MiloText {
                    Layout.fillWidth: true
                    Layout.leftMargin: 26
                    visible: page.chat === "openai_compat"
                    text: "The model you talk with doesn't do helper jobs: they still run through Claude or Codex CLI. Without either, choose Disabled and Milo only talks."
                    size: Theme.type.caption; tone: 0.6; wrapMode: Text.WordWrap
                }
            }
            MiloText {
                Layout.fillWidth: true
                Layout.leftMargin: 4
                text: "Sign in to CLIs in your own terminal or browser: claude auth login or codex login.\nThis screen detects installed commands; it does not check your account."
                size: Theme.type.caption; tone: 0.6; wrapMode: Text.WordWrap
            }
            MiloText {
                Layout.fillWidth: true
                Layout.leftMargin: 4
                text: "An API key you paste here is saved alone in your Milo/secrets folder, never in config.toml, and never shown again. You can also put it in that file yourself."
                size: Theme.type.caption; tone: 0.6; wrapMode: Text.WordWrap
            }
            Callout { objectName: "problem"; visible: page.problem !== ""; icon: "exclamationmark.triangle"; text: page.problem }
            Flow {
                Layout.fillWidth: true
                spacing: 8
                MiloButton {
                    objectName: "check"
                    text: "Check installed CLIs again"
                    kind: "quiet"
                    enabled: !!page.setupBackend
                    onClicked: page.setupBackend.reload()  // keeps what the user chose and typed
                }
                MiloButton {
                    objectName: "secrets"
                    text: "Open secrets folder"
                    kind: "quiet"
                    enabled: !!page.setupBackend
                    onClicked: page.setupBackend.openSecrets()
                }
                MiloButton {
                    objectName: "save"
                    text: "Save and restart brain"
                    kind: "primary"
                    enabled: !!page.setupBackend && page.problem === ""
                    onClicked: page.save()
                }
            }

            // ---- try it
            Card {
                Layout.topMargin: 10
                padding: 12
                RowLayout {
                    spacing: 14
                    Rectangle {
                        implicitWidth: 52
                        implicitHeight: 52
                        radius: 14
                        color: Theme.tint
                        border.color: Theme.rule
                        Icon { anchors.centerIn: parent; name: "mic"; size: 22; color: Theme.primary }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 6
                        RowLayout {
                            MiloText {
                                Layout.fillWidth: true
                                text: "Try it: hold " + page.dictateKey + " and say something"
                                size: 15; weight: "semibold"; rounded: true; wrapMode: Text.WordWrap
                            }
                            CheckBadge { done: page.tried }
                        }
                        MiloText {
                            Layout.fillWidth: true
                            text: page.tried ? "I heard you. We're all set."
                                             : "I listen while you hold the key, and type your words where your cursor is when you let go."
                            size: 12.5; tone: 0.7; wrapMode: Text.WordWrap
                        }
                    }
                }
            }
        }

        // ---- the footer
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: footer.implicitHeight + 24
            color: Tones.fade(Theme.card, 0.6)
            Rule { anchors.top: parent.top; width: parent.width }
            RowLayout {
                id: footer
                anchors.fill: parent
                anchors.leftMargin: 22
                anchors.rightMargin: 22
                MiloText {
                    Layout.fillWidth: true
                    readonly property int done: page.required.filter(r => r.state === "granted").length
                    text: page.ready ? "Milo has everything he needs."
                        : page.required.length > 0 ? done + " of " + page.required.length + " done" : ""
                    size: Theme.type.caption; rounded: true; tone: 0.6
                }
                MiloButton { objectName: "done"; text: "Done"; onClicked: page.action("done", null) }
            }
        }
    }
}
