import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls
import "meeting.mjs" as Meeting

// The top of a meeting going on (LiveMeetingHeader): the light, the title, the time, who was heard, Pause and Stop.
Rectangle {
    id: header
    property var status: ({})
    property real elapsed: 0
    signal pause(bool on)
    signal stop()

    readonly property var speakers: status.speakers || []
    Layout.fillWidth: true
    implicitHeight: row.implicitHeight + 28
    color: "transparent"

    RowLayout {
        id: row
        anchors.fill: parent
        anchors.leftMargin: 20
        anchors.rightMargin: 20
        spacing: 12

        Rectangle {
            implicitWidth: 34
            implicitHeight: 34
            radius: 9
            color: Tones.fade(Tones.live, 0.12)
            Icon {
                anchors.centerIn: parent
                visible: header.status.phase === "writing"
                name: "pencil.line"
                size: 15
                color: Theme.primary
            }
            LiveLight {
                anchors.centerIn: parent
                visible: header.status.phase !== "writing"
                paused: header.status.phase === "paused"
            }
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 3
            MiloText {
                Layout.fillWidth: true
                text: header.status.title || "Meeting"
                size: Theme.type.headline
                weight: "bold"
                rounded: true
            }
            MiloText {
                Layout.fillWidth: true
                text: Meeting.liveLine(header.status, header.elapsed)
                size: Theme.type.caption
                weight: "medium"
                tone: 0.6
                tabular: true
            }
            Row {
                visible: header.speakers.length > 0
                spacing: 6
                Accessible.role: Accessible.StaticText
                Accessible.name: "Heard so far: " + header.speakers.join(", ")
                Repeater {
                    model: header.speakers.slice(0, 6)
                    Row {
                        required property string modelData
                        spacing: 4
                        Rectangle {
                            anchors.verticalCenter: parent.verticalCenter
                            width: 6
                            height: 6
                            radius: 3
                            color: Tones.speaker(modelData, header.speakers)
                        }
                        MiloText { text: modelData; size: 11; weight: "medium"; rounded: true; tone: 0.7 }
                    }
                }
                MiloText {
                    visible: header.speakers.length > 6
                    text: "+" + (header.speakers.length - 6)
                    size: 11
                    tone: 0.5
                }
            }
        }
        MiloButton {
            objectName: "pause"
            visible: Meeting.live(header.status)
            text: header.status.phase === "paused" ? "Go on" : "Pause"
            kind: "quiet"
            tip: header.status.phase === "paused" ? "Go on taking notes" : "Leave the next part out of the notes"
            onClicked: header.pause(header.status.phase !== "paused")
        }
        MiloButton {
            objectName: "stop"
            visible: Meeting.live(header.status)
            text: "Stop"
            kind: "primary"
            iconName: "stop"
            tip: "Stop taking notes and write them up"
            Accessible.name: "Stop taking notes"
            onClicked: header.stop()
        }
    }
    Rule { anchors.bottom: parent.bottom; width: parent.width }
}
