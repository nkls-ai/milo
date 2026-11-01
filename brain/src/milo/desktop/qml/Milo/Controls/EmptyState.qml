import QtQuick
import QtQuick.Layouts
import Milo

// A calm note where a list would be: an icon (or a spinner while `busy`), a line in Milo's voice and one quiet
// sentence, inside a dashed frame when `framed` (Today's "Nothing on your plate.").
Item {
    id: empty
    property string icon
    property string title
    property string detail
    property bool framed: false
    property bool busy: false

    implicitWidth: column.implicitWidth + 48
    implicitHeight: column.implicitHeight + (framed ? 68 : 48)
    Layout.fillWidth: true
    Accessible.role: Accessible.StaticText
    Accessible.name: title + (detail ? ". " + detail : "")

    Canvas {
        anchors.fill: parent
        visible: empty.framed
        readonly property color line: Tones.fade(Theme.primary, 0.2)
        onLineChanged: requestPaint()
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        onPaint: {
            const ctx = getContext("2d")
            ctx.reset()
            ctx.strokeStyle = line
            ctx.lineWidth = 1.2
            ctx.setLineDash([5 / 1.2, 5 / 1.2])
            ctx.beginPath()
            ctx.roundedRect(0.6, 0.6, width - 1.2, height - 1.2, Theme.radius.card, Theme.radius.card)
            ctx.stroke()
        }
    }
    ColumnLayout {
        id: column
        anchors.centerIn: parent
        width: Math.min(300, parent.width - 48)
        spacing: 10
        Spinner { Layout.alignment: Qt.AlignHCenter; visible: empty.busy; size: 16 }
        Icon {
            Layout.alignment: Qt.AlignHCenter
            visible: !empty.busy && empty.icon !== ""
            name: empty.icon
            size: 22
            weight: "medium"
            color: Tones.fade(Theme.primary, 0.7)
        }
        MiloText {
            Layout.fillWidth: true
            text: empty.title
            size: 15
            weight: "semibold"
            rounded: true
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
        }
        MiloText {
            Layout.fillWidth: true
            visible: empty.detail !== ""
            text: empty.detail
            size: Theme.type.caption
            tone: 0.58
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
        }
    }
}
