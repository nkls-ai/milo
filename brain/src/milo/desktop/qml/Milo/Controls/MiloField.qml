import QtQuick
import QtQuick.Templates as T
import Milo

// A text field on card paper whose edge turns Milo's colour while you type in it. `multiline` grows with its text
// (up to `maxLines`) and takes Shift+Enter for a new line. Enter emits accepted(), Escape cancelled().
FocusScope {
    id: field
    property alias text: editor.text
    property string placeholder: ""
    property bool multiline: false
    property int maxLines: 6
    property real size: Theme.type.body
    property alias editor: editor
    signal accepted()
    signal cancelled()

    implicitWidth: 200
    implicitHeight: Math.min(editor.contentHeight, maxLines * editor.font.pixelSize * 1.35) + 2 * 6 + 2
    Accessible.role: Accessible.EditableText
    Accessible.name: placeholder

    function focusAndSelect() { editor.forceActiveFocus(); editor.selectAll() }

    Rectangle {
        anchors.fill: parent
        radius: 9
        color: Theme.card
        border.width: 1
        border.color: editor.activeFocus ? Tones.fade(Theme.primary, 0.55) : Theme.rule
        Behavior on border.color { ColorSpring { kind: "snappy" } }
    }

    Flickable {
        id: flick
        anchors.fill: parent
        anchors.leftMargin: 10
        anchors.rightMargin: 10
        anchors.topMargin: 6
        anchors.bottomMargin: 6
        contentHeight: editor.contentHeight
        clip: true
        interactive: contentHeight > height
        boundsBehavior: Flickable.StopAtBounds

        TextEdit {
            id: editor
            width: flick.width
            focus: true
            wrapMode: field.multiline ? TextEdit.Wrap : TextEdit.NoWrap
            color: Theme.ink
            selectionColor: Tones.fade(Theme.primary, 0.35)
            selectedTextColor: Theme.ink
            font.family: Theme.fontFamily
            font.pixelSize: field.size
            selectByMouse: true
            persistentSelection: false
            Accessible.name: field.placeholder
            onCursorRectangleChanged: {
                if (cursorRectangle.y < flick.contentY) flick.contentY = cursorRectangle.y
                else if (cursorRectangle.y + cursorRectangle.height > flick.contentY + flick.height)
                    flick.contentY = cursorRectangle.y + cursorRectangle.height - flick.height
            }
            Keys.onPressed: event => {
                if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter)
                        && !(field.multiline && (event.modifiers & Qt.ShiftModifier))) {
                    field.accepted()
                    event.accepted = true
                } else if (event.key === Qt.Key_Escape) {
                    field.cancelled()
                    event.accepted = true
                }
            }

            MiloText {
                anchors.fill: parent
                visible: editor.text === "" && !editor.preeditText
                text: field.placeholder
                size: field.size
                tone: 0.4
            }
        }
    }
}
