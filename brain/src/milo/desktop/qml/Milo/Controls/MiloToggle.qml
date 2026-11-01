import QtQuick
import QtQuick.Templates as T
import Milo

// A switch (`.toggleStyle(.switch)`): the knob springs across, the track fills with Milo's colour. `text` is its
// accessible name; it draws no label of its own. Emits toggled() on a user change, with `checked` already flipped.
T.Switch {
    id: sw
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    implicitWidth: 38
    implicitHeight: 22
    padding: 0
    Accessible.role: Accessible.CheckBox
    Accessible.name: text
    Accessible.checked: checked
    Keys.onReturnPressed: sw.click()  // toggles and emits clicked() and toggled(), like Space

    indicator: Rectangle {
        anchors.fill: parent
        radius: height / 2
        color: sw.checked ? Theme.primary : Tones.fade(Theme.ink, sw.hovered ? 0.2 : 0.15)
        Behavior on color { ColorSpring {} }
        FocusRing { shown: sw.visualFocus }

        Rectangle {
            id: knob
            width: parent.height - 4
            height: width
            radius: width / 2
            y: 2
            x: sw.checked ? parent.width - width - 2 : 2
            color: "#FFFFFF"
            scale: sw.pressed ? 0.92 : 1
            Behavior on x { Spring { kind: "snappy" } }
            Behavior on scale { Spring { kind: "snappy" } }
        }
    }
    contentItem: Item {}
}
