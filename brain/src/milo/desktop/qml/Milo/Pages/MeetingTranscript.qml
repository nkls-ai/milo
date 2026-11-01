import QtQuick
import QtQuick.Layouts
import QtQuick.Templates as T
import Milo
import Milo.Controls
import "meeting.mjs" as Meeting

// A meeting's lines (MeetingTranscript): a name when the speaker changes, the time into the meeting, the words.
// Live, it follows new lines until the user scrolls up, then offers "Back to now" with how many came meanwhile, and
// ends with a row that says the last minute comes later.
Item {
    id: transcript
    property var lines: []
    property string phase: ""
    property string step: ""
    property bool live: false

    readonly property var names: Meeting.names(lines)
    property bool following: true
    property int unseen: 0

    Layout.fillWidth: true
    Layout.fillHeight: true

    function jump() {
        following = true
        unseen = 0
        list.glideToEnd()
    }

    onLinesChanged: {
        const arrived = lines.length - list.shown
        list.shown = lines.length
        if (!live || arrived <= 0) return
        if (following) Qt.callLater(list.glideToEnd)
        else unseen += arrived
    }

    ListView {
        id: list
        property int shown: 0
        anchors.fill: parent
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        topMargin: 14
        bottomMargin: 14
        model: transcript.lines
        T.ScrollBar.vertical: MiloScrollBar {}

        readonly property real startY: originY - topMargin
        readonly property real endY: Math.max(startY, originY + contentHeight + bottomMargin - height)
        function glideToEnd() {
            glide.to = endY
            glide.restart()
        }
        Spring { id: glide; target: list; property: "contentY"; kind: "gentle" }

        // Following, the end stays in view as lines arrive and as the view settles its size.
        onEndYChanged: if (transcript.live && transcript.following && !glide.running) contentY = endY
        Component.onCompleted: {
            shown = transcript.lines.length
            if (transcript.live) Qt.callLater(() => list.contentY = list.endY)
        }
        // Scrolled back to the end by hand: follow again.
        onContentYChanged: {
            if (!transcript.live || glide.running || !moving) return
            const atEnd = contentY >= endY - 24
            transcript.following = atEnd
            if (atEnd) transcript.unseen = 0
        }

        header: MiloText {
            x: 20
            width: list.width - 40
            visible: transcript.lines.length === 0 && !transcript.live
            height: visible ? implicitHeight + 40 : 0
            verticalAlignment: Text.AlignVCenter
            text: "No transcript for this meeting."
            tone: 0.5
        }
        delegate: MeetingLine {
            required property var modelData
            required property int index
            x: 20
            width: list.width - 40
            line: modelData
            named: index === 0 || transcript.lines[index - 1].who !== modelData.who
            tint: Tones.speaker(modelData.who, transcript.names)
        }
        footer: Item {
            width: list.width
            height: transcript.live ? lag.implicitHeight + 16 : 0
            visible: transcript.live
            RowLayout {
                id: lag
                x: 20
                y: 16
                spacing: 10
                Item {
                    implicitWidth: 44
                    implicitHeight: dots.implicitHeight
                    ThinkingDots {
                        id: dots
                        anchors.right: parent.right
                        dot: 5
                        color: Tones.fade(Theme.primary, transcript.phase === "paused" ? 0.35 : 1)
                    }
                }
                MiloText {
                    text: Meeting.lagLine(transcript.phase, transcript.step, transcript.lines.length === 0)
                    size: 12.5
                    weight: "medium"
                    rounded: true
                    tone: 0.55
                }
            }
        }
    }

    Appear {
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 10
        anchors.horizontalCenter: parent.horizontalCenter
        shown: transcript.live && !transcript.following
        MiloButton {
            objectName: "backToNow"
            text: transcript.unseen > 0 ? "Back to now · " + transcript.unseen + " new" : "Back to now"
            iconName: "arrow.down"
            size: "small"
            onClicked: transcript.jump()
        }
    }
}
