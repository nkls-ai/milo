import QtQuick
import QtQuick.Layouts
import Milo

// A note in plain words on a marigold wash, with an optional button: "Fix it", "Restart Milo". Emits clicked().
Rectangle {
    id: callout
    property string icon: "info.circle"
    property string text
    property string button: ""
    signal clicked()

    Layout.fillWidth: true
    implicitHeight: row.implicitHeight + 20
    radius: Theme.radius.medium
    color: Tones.fade(Theme.accent, 0.09)
    Accessible.role: Accessible.StaticText
    Accessible.name: text

    RowLayout {
        id: row
        anchors.fill: parent
        anchors.margins: 10
        spacing: 10
        Icon { name: callout.icon; size: 14; color: Theme.accent }
        MiloText {
            Layout.fillWidth: true
            text: callout.text
            size: Theme.type.caption
            tone: 0.8
            wrapMode: Text.WordWrap
        }
        MiloButton {
            visible: callout.button !== ""
            text: callout.button
            kind: "secondary"
            onClicked: callout.clicked()
        }
    }
}
