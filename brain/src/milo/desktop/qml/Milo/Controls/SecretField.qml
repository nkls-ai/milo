import QtQuick
import QtQuick.Templates as T
import Milo

// A one-line field whose text shows as dots: an API key. Nothing reads it back out but its owner, once, to save.
// Enter emits accepted().
FocusScope {
    id: field
    property alias text: input.text
    property string placeholder: ""
    signal accepted()

    implicitWidth: 200
    implicitHeight: input.implicitHeight + 14
    Accessible.role: Accessible.EditableText
    Accessible.name: placeholder
    Accessible.passwordEdit: true

    Rectangle {
        anchors.fill: parent
        radius: 9
        color: Theme.card
        border.width: 1
        border.color: input.activeFocus ? Tones.fade(Theme.primary, 0.55) : Theme.rule
        Behavior on border.color { ColorSpring { kind: "snappy" } }
    }
    TextInput {
        id: input
        anchors.fill: parent
        anchors.leftMargin: 10
        anchors.rightMargin: 10
        verticalAlignment: TextInput.AlignVCenter
        focus: true
        echoMode: TextInput.Password
        passwordMaskDelay: 0
        clip: true
        color: Theme.ink
        selectionColor: Tones.fade(Theme.primary, 0.35)
        font.family: Theme.fontFamily
        font.pixelSize: Theme.type.body
        selectByMouse: true
        inputMethodHints: Qt.ImhSensitiveData | Qt.ImhNoPredictiveText | Qt.ImhHiddenText
        onAccepted: field.accepted()
    }
    MiloText {
        anchors.fill: input
        verticalAlignment: Text.AlignVCenter
        visible: input.text === ""
        text: field.placeholder
        tone: 0.4
    }
}
