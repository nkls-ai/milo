import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls
import "wire.mjs" as Wire

// Settings (SettingsView.swift): how Milo talks, how much he tells you, dictation, meetings, his keys and his voice.
// Every choice comes from the brain's `settings` report and goes back to it; nothing is stored here. A card shows
// only when the brain reported its setting.
//
// Inputs
//   settings: the `settings` event's list, [{section, key, value, options, labels, live}]; [] until it came.
//   restart:  a saved change waits for Milo to restart.   error: why the last change wasn't saved, or "".
//   connected: whether the brain is up (only changes the waiting line).
// Output
//   command({"type": "set_setting", section, key, value}) with the value's own type: a bool, an option as the
//   brain listed it (string or number), the allowed apps' list, or the meeting apps as "Zoom, Microsoft Teams".
//   action("restart"), action("showWords") for dictionary.md, action("openSetup") for Connections & models.
Item {
    id: page
    property var settings: []
    property bool restart: false
    property string error: ""
    property bool connected: true
    signal command(var message)
    signal action(string name, var value)

    function get(section, key) {
        return (settings || []).find(s => s.section === section && s.key === key) || null
    }
    function change(setting, value) { command(Wire.setSetting(setting.section, setting.key, value)) }

    // The options with their labels; a value set by hand in config.toml first, as itself.
    function choices(setting) {
        const all = setting.options.map((value, i) => ({ value: value, label: setting.labels[i] }))
        const listed = setting.options.some(o => JSON.stringify(o) === JSON.stringify(setting.value))
        if (!listed && typeof setting.value === "string") all.unshift({ value: setting.value, label: setting.value })
        return all
    }
    // [ui] hide_after_s: a hand-set time in words.
    function hideChoices(setting) {
        const all = setting.options.map((value, i) => ({ value: value, label: setting.labels[i] }))
        const seconds = setting.value
        if (setting.options.indexOf(seconds) < 0 && typeof seconds === "number")
            all.unshift({ value: seconds, label: seconds <= 0 ? "Never"
                                               : seconds % 60 === 0 ? "After " + seconds / 60 + " minutes"
                                               : "After " + seconds + " seconds" })
        return all
    }
    function apps(text) { return String(text || "").split(",").map(s => s.trim()).filter(s => s !== "") }

    EmptyState {
        anchors.centerIn: parent
        width: Math.min(parent.width, 340)
        visible: (page.settings || []).length === 0
        busy: true
        title: page.connected ? "Getting my settings…" : "I'm just waking up…"
    }

    MiloScrollView {
        id: scroll
        anchors.fill: parent
        visible: (page.settings || []).length > 0
        leftPadding: 22
        rightPadding: 22
        topPadding: 22
        bottomPadding: 22
        maxContentWidth: 640
        spacing: 14

        Callout {
            visible: page.error !== ""
            icon: "exclamationmark.bubble"
            text: page.error
        }
        Callout {
            objectName: "restart"
            visible: page.restart
            icon: "arrow.clockwise"
            text: "Some changes start working after Milo restarts."
            button: "Restart Milo"
            onClicked: page.action("restart", null)
        }

        ChoiceCard {
            setting: page.get("chat", "use")
            choices: setting ? page.choices(setting) : []
            onChosen: value => page.change(setting, value)
            icon: "bubble.left.and.bubble.right"
            title: "Who Milo talks with"
            detail: "Sign in to Claude or Codex in your terminal first. Changes need a restart. API endpoints are configured in config.toml."
        }
        ChoiceCard {
            setting: page.get("chat", "updates")
            choices: setting ? page.choices(setting) : []
            onChosen: value => page.change(setting, value)
            icon: "text.bubble"
            title: "How often Milo tells you what he's doing"
            detail: "While he works on something for you."
        }

        // [approvals] ask, and the apps the user chose Allow always for, each with Remove (ADR 22).
        Card {
            id: asking
            readonly property var ask: page.get("approvals", "ask")
            readonly property var allowed: page.get("approvals", "allowed_apps")
            readonly property bool auto: !!ask && ask.value === "auto"
            visible: !!ask
            objectName: "approvals"
            CardHeading {
                icon: asking.auto ? "bolt" : "hand.raised"
                title: "How often Milo asks before he acts"
                detail: "While he works in an app for you."
            }
            ChoiceList {
                choices: asking.ask ? page.choices(asking.ask) : []
                selected: asking.ask ? asking.ask.value : null
                onChosen: value => page.change(asking.ask, value)
            }
            MiloText {
                Layout.fillWidth: true
                Layout.leftMargin: 26
                text: asking.auto
                      ? "Milo does what you ask without checking first. He always stops for things that can't be undone, sending, buying and money. Passwords and security settings he never touches."
                      : "He always stops for things that can't be undone, sending, buying and money. Passwords and security settings he never touches."
                size: 11.5
                weight: asking.auto ? "medium" : "regular"
                ink: asking.auto ? Theme.accent : Theme.ink
                tone: asking.auto ? 1 : 0.65
                wrapMode: Text.WordWrap
            }
            ColumnLayout {
                visible: !!asking.allowed
                Layout.leftMargin: 26
                Layout.fillWidth: true
                spacing: 6
                readonly property var list: asking.allowed && asking.allowed.value && typeof asking.allowed.value === "object" ? Array.from(asking.allowed.value) : []
                MiloText { text: "Always allowed" }
                MiloText {
                    Layout.fillWidth: true
                    visible: parent.list.length === 0
                    text: "No apps yet. Choose Allow always when Milo asks, and the app shows here."
                    size: 11
                    tone: 0.65
                    wrapMode: Text.WordWrap
                }
                Repeater {
                    model: parent.list
                    RowLayout {
                        required property var modelData
                        required property int index
                        readonly property string name: modelData.name || modelData.bundle || "?"
                        objectName: "allowed-" + name
                        Layout.fillWidth: true
                        Icon { name: "checkmark.seal"; size: 14; color: Theme.primary }
                        MiloText { Layout.fillWidth: true; text: parent.name }
                        MiloButton {
                            objectName: "remove"
                            text: "Remove"
                            kind: "quiet"
                            size: "small"
                            shape: "rounded"
                            Accessible.description: "Milo asks again before he works in this app"
                            onClicked: page.change(asking.allowed, Array.from(asking.allowed.value).filter((_, i) => i !== index))
                        }
                    }
                }
            }
        }

        Card {
            id: dictation
            readonly property var stream: page.get("dictation", "stream")
            readonly property var learn: page.get("dictation", "learn")
            visible: !!stream
            CardHeading { icon: "mic"; title: "Dictation"; detail: "When your words appear." }
            ChoiceList {
                choices: dictation.stream ? page.choices(dictation.stream) : []
                selected: dictation.stream ? dictation.stream.value : null
                onChosen: value => page.change(dictation.stream, value)
            }
            SettingSwitch {
                objectName: "learn"
                visible: !!dictation.learn
                Layout.topMargin: 4
                title: "Learn from your fixes"
                detail: "Fix a word he pasted, and he spells it your way next time."
                on: !dictation.learn || dictation.learn.value !== false
                onChanged: on => page.change(dictation.learn, on)
            }
            MiloButton {
                objectName: "showWords"
                visible: !!dictation.learn
                text: "Show the words"
                kind: "plain"
                size: "small"
                onClicked: page.action("showWords", null)
            }
        }

        Card {
            id: meetings
            readonly property var auto: page.get("meetings", "auto")
            visible: !!auto
            CardHeading {
                icon: "person.2"
                title: "Meeting notes"
                detail: "When a call starts in Zoom, Teams, FaceTime and the like."
            }
            ChoiceList {
                choices: meetings.auto ? page.choices(meetings.auto) : []
                selected: meetings.auto ? meetings.auto.value : null
                onChosen: value => page.change(meetings.auto, value)
            }
            Repeater {
                // The apps chosen with "Always for Zoom" or "Never for Zoom" on Milo's question, each removable.
                model: [["always", "Takes notes without asking in"], ["never", "Never asks in"]]
                ColumnLayout {
                    id: group
                    required property var modelData
                    readonly property var setting: page.get("meetings", modelData[0])
                    readonly property var list: setting ? page.apps(setting.value) : []
                    objectName: "meetings-" + modelData[0]
                    visible: list.length > 0
                    Layout.leftMargin: 26
                    Layout.fillWidth: true
                    spacing: 6
                    MiloText { text: modelData[1]; size: Theme.type.caption; tone: 0.65 }
                    Flow {
                        Layout.fillWidth: true
                        spacing: 6
                        Repeater {
                            model: group.list
                            AppChip {
                                required property var modelData
                                objectName: "chip-" + modelData
                                name: modelData
                                onRemove: page.change(group.setting, group.list.filter(a => a !== modelData).join(", "))
                            }
                        }
                    }
                }
            }
        }

        Card {
            id: keys
            readonly property var rows: [["dictate_key", "Hold to dictate"], ["talk_key", "Hold to talk to Milo"],
                                         ["whats_this_key", "Ask “What's this?”"], ["meeting_key", "Start or stop meeting notes"]]
                .map(([key, title]) => ({ setting: page.get("ui", key), title: title })).filter(r => !!r.setting)
            visible: rows.length > 0
            CardHeading { icon: "keyboard"; title: "Keys" }
            Repeater {
                model: keys.rows
                RowLayout {
                    required property var modelData
                    objectName: "key-" + modelData.setting.key
                    Layout.leftMargin: 26
                    Layout.fillWidth: true
                    MiloText { Layout.fillWidth: true; text: modelData.title }
                    MiloDropdown {
                        objectName: "picker"
                        name: modelData.title
                        options: page.choices(modelData.setting)
                        current: modelData.setting.value
                        onPicked: value => page.change(modelData.setting, value)
                    }
                }
            }
        }

        Card {
            id: voiceCard
            readonly property var voice: page.get("ui", "voice")
            visible: !!voice
            SettingSwitch {
                objectName: "voice"
                icon: voiceCard.voice && voiceCard.voice.value === false ? "speaker.slash" : "speaker.wave.2"
                title: "Milo says his answers out loud"
                detail: "Off: answers show in his bubble only."
                on: !voiceCard.voice || voiceCard.voice.value !== false
                onChanged: on => page.change(voiceCard.voice, on)
            }
        }

        Card {
            id: leaving
            readonly property var stay: page.get("ui", "hide_after_s")
            visible: !!stay
            CardHeading {
                icon: "bird"
                title: "When Milo leaves the screen"
                detail: "If nothing is going on. He comes back when you press a key or he has something for you."
            }
            ChoiceList {
                choices: leaving.stay ? page.hideChoices(leaving.stay) : []
                selected: leaving.stay ? leaving.stay.value : null
                onChosen: value => page.change(leaving.stay, value)
            }
        }

        Card {
            id: showCard
            readonly property var show: page.get("hands", "show_window")
            visible: !!show
            SettingSwitch {
                objectName: "showWindow"
                icon: "macwindow"
                title: "Show me the window Milo works in"
                detail: "Brings it to the front when he starts. Off: he works behind your windows."
                on: !showCard.show || showCard.show.value !== false
                onChanged: on => page.change(showCard.show, on)
            }
        }

        // Windows and Linux choose the talking and helper providers on the setup page, not here.
        Card {
            RowLayout {
                spacing: 12
                CardHeading {
                    icon: "plug"
                    title: "Connections & models"
                    detail: "Which Claude, Codex or API Milo talks and works with."
                }
                MiloButton {
                    objectName: "openSetup"
                    text: "Change…"
                    kind: "secondary"
                    onClicked: page.action("openSetup", null)
                }
            }
        }
    }
}
