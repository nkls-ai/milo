import QtQuick
import QtQuick.Templates as T
import Milo
import Milo.Controls

// A row in the sidebar. Its selection card is drawn once by the sidebar and glides between rows; the row itself only
// washes under the pointer.
T.AbstractButton {
    id: button
    property bool selected: false
    property string label: ""

    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    implicitWidth: implicitContentWidth
    implicitHeight: implicitContentHeight + topPadding + bottomPadding
    topPadding: 7
    bottomPadding: 7
    Accessible.role: Accessible.Button
    Accessible.name: label
    Accessible.selected: selected
    Keys.onReturnPressed: clicked()

    background: Rectangle {
        radius: Theme.radius.small
        color: Tones.fade(Theme.ink, button.hovered && !button.selected ? 0.045 : 0)
        Behavior on color { ColorSpring { kind: "snappy" } }
        FocusRing { shown: button.visualFocus }
    }
}
