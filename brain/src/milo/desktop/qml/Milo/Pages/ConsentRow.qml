import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls

// "Let the others know" with the line to paste into the call's chat (ConsentRow). Emits copy().
Rectangle {
    id: consent
    property string line: ""
    property bool copied: false
    signal copy()

    Layout.fillWidth: true
    implicitHeight: row.implicitHeight + 18
    color: Tones.fade(Theme.accent, 0.07)

    RowLayout {
        id: row
        anchors.fill: parent
        anchors.leftMargin: 20
        anchors.rightMargin: 20
        spacing: 10
        Icon { name: "text.bubble"; size: 14; color: Theme.accent }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 1
            MiloText { text: "Let the others know"; size: 12; weight: "semibold"; rounded: true; tone: 0.85 }
            MiloText { Layout.fillWidth: true; text: "“" + consent.line + "”"; size: 11.5; tone: 0.6 }
        }
        MiloButton {
            objectName: "copyConsent"
            text: consent.copied ? "Copied" : "Copy for the chat"
            kind: "quiet"
            Accessible.description: "Puts the line on the clipboard, to paste into the call's chat"
            onClicked: consent.copy()
        }
    }
    Rule { anchors.bottom: parent.bottom; width: parent.width }
}
