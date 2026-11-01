import QtQuick
import QtQuick.Layouts
import QtQuick.Templates as T
import Milo
import Milo.Controls

// The field to type to Milo (InputBar): Enter sends, Shift+Enter starts a new line. Hold the microphone to talk instead,
// and the speaker says whether he reads typed answers aloud. A draft stays when it couldn't be sent.
Rectangle {
    id: composer
    property string conversation: ""  // "" for the conversation going on; an older one picks it up again
    property string placeholder: "Type to Milo"
    signal sent()

    implicitHeight: row.implicitHeight + Theme.space.m + Theme.space.l - 2
    color: Theme.tint

    function send() {
        if (shell.sendText(field.text, composer.conversation)) {
            field.text = ""
            composer.sent()
        }
    }

    Rule { anchors { left: parent.left; right: parent.right; top: parent.top } }

    Connections {
        target: shell
        function onPrefillChanged() {
            if (shell.prefill === "") return
            field.text = shell.prefill
            field.editor.cursorPosition = field.text.length
            field.editor.forceActiveFocus()
            shell.takePrefill()
        }
        function onFocusTickChanged() { field.editor.forceActiveFocus() }
    }
    Component.onCompleted: field.editor.forceActiveFocus()

    RowLayout {
        id: row
        anchors { left: parent.left; right: parent.right; top: parent.top; topMargin: Theme.space.m - 2; leftMargin: 14; rightMargin: 14 }
        spacing: Theme.space.s

        MiloField {
            id: field
            Layout.fillWidth: true
            multiline: true
            maxLines: 6
            size: 13.5
            placeholder: composer.placeholder
            onAccepted: composer.send()
        }
        HoldToTalk {}
        IconButton {
            iconName: shell.speakReplies ? "speaker.wave.2" : "speaker.slash"
            label: shell.speakReplies ? "Milo reads his answers aloud. Click to keep them silent."
                                      : "Milo answers typed messages silently. Click to hear them."
            tint: shell.speakReplies ? Theme.primary : Theme.ink
            tone: shell.speakReplies ? 1 : 0.55
            size: 30
            wash: false
            Accessible.description: shell.speakReplies ? "on" : "off"
            onClicked: shell.setSpeakReplies(!shell.speakReplies)
        }
    }

    // Press and hold to talk to Milo, like the talk key; release to send what was said.
    component HoldToTalk: T.AbstractButton {
        id: mic
        readonly property bool live: shell.recording !== ""
        implicitWidth: 34
        implicitHeight: 34
        enabled: shell.connected
        hoverEnabled: true
        focusPolicy: Qt.NoFocus
        Accessible.role: Accessible.Button
        Accessible.name: "Hold to talk to Milo"
        onPressed: shell.listen("talk")
        onReleased: shell.stopListening()
        onCanceled: shell.stopListening()
        scale: pressed ? 0.94 : live && !Theme.reducedMotion ? 1.06 : 1
        Behavior on scale { Spring { kind: "snappy" } }

        background: Rectangle {
            radius: width / 2
            color: mic.live ? Theme.talk : Tones.fade(Theme.primary, mic.hovered ? 0.16 : 0.09)
            Behavior on color { ColorSpring { kind: "snappy" } }
            Rectangle {
                anchors.centerIn: parent
                width: parent.width + 8 + 10 * presence.level
                height: width
                radius: width / 2
                color: "transparent"
                border.width: 2
                border.color: Tones.fade(Theme.talk, 0.35)
                visible: mic.live
            }
        }
        contentItem: Item {
            Icon {
                anchors.centerIn: parent
                name: "mic"
                size: 15
                color: mic.live ? Theme.primaryInk : Theme.primary
                filled: mic.live
            }
        }
        Tip { text: "Hold to talk, release to send"; shown: mic.hovered && !mic.pressed }
    }
}
