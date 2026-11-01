import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls

// Questions about the meeting so far and Milo's answers, a few ready ones to ask, and the field to ask in
// (AskAboutMeeting with the window's InputBar). The answers take at most 140 points and then scroll, the newest in
// view. A ready question goes into the field, to send or change. Emits ask(text).
Rectangle {
    id: ask
    property var entries: []
    property var suggestions: []
    signal ask(string text)

    Layout.fillWidth: true
    implicitHeight: column.implicitHeight + 12
    color: "transparent"

    function send() {
        const text = field.text.trim()
        if (text === "") return
        ask.ask(text)
        field.text = ""
    }

    Rule { anchors.top: parent.top; width: parent.width }

    ColumnLayout {
        id: column
        x: 16
        y: 10
        width: parent.width - 32
        spacing: 8

        Flickable {
            id: answers
            Layout.fillWidth: true
            visible: ask.entries.length > 0
            implicitHeight: Math.min(140, rows.implicitHeight)
            contentHeight: rows.implicitHeight
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            onContentHeightChanged: contentY = Math.max(0, contentHeight - height)
            ColumnLayout {
                id: rows
                width: answers.width
                spacing: 6
                Repeater {
                    model: ask.entries.slice(-6)
                    RowLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        spacing: 8
                        MiloText {
                            Layout.preferredWidth: 32
                            Layout.alignment: Qt.AlignTop
                            text: modelData.kind === "user" ? "You" : "Milo"
                            size: 11.5
                            weight: "semibold"
                            rounded: true
                            ink: modelData.kind === "user" ? Theme.ink : Theme.primary
                            tone: modelData.kind === "user" ? 0.55 : 1
                        }
                        MiloText {
                            Layout.fillWidth: true
                            text: modelData.text
                            tone: 0.9
                            wrapMode: Text.WordWrap
                        }
                    }
                }
            }
        }
        Flow {
            Layout.fillWidth: true
            spacing: 6
            Repeater {
                model: ask.suggestions
                MiloButton {
                    required property string modelData
                    required property int index
                    objectName: "suggestion-" + index
                    text: modelData
                    kind: "quiet"
                    size: "small"
                    onClicked: { field.text = modelData; field.editor.forceActiveFocus(); field.editor.cursorPosition = modelData.length }
                }
            }
        }
        RowLayout {
            spacing: 8
            MiloField {
                id: field
                objectName: "askField"
                Layout.fillWidth: true
                placeholder: "Ask about this meeting"
                onAccepted: ask.send()
            }
            IconButton {
                objectName: "send"
                iconName: "arrow.up"
                label: "Send"
                size: 30
                enabled: field.text.trim() !== ""
                opacity: enabled ? 1 : 0.4
                onClicked: ask.send()
            }
        }
    }
}
