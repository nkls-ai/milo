import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls

// The first thing a new user sees: talk first, typing second.
Item {
    ColumnLayout {
        anchors.centerIn: parent
        width: Math.min(parent.width - 48, 320)
        spacing: Theme.space.m

        Item {
            Layout.alignment: Qt.AlignHCenter
            implicitWidth: 110
            implicitHeight: 110
            Rectangle {
                anchors.fill: parent
                radius: width / 2
                gradient: Gradient {
                    orientation: Gradient.Vertical
                    GradientStop { position: 0; color: Tones.fade(Theme.glow, 0.45) }
                    GradientStop { position: 1; color: Tones.fade(Theme.glow, 0) }
                }
            }
            Wren {
                anchors.centerIn: parent
                width: 96
                height: 96
            }
        }
        MiloText {
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
            text: "Hold " + shell.talkKey + " and talk, or type here."
            size: 15
            weight: "medium"
            rounded: true
        }
        MiloText {
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
            text: "What you say, what Milo answers and what he does for you shows up here."
            size: Theme.type.caption
            tone: 0.55
        }
    }
}
