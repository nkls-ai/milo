import QtQuick
import QtQuick.Layouts
import Milo

// The `index`th card of a page floating in once `shown`: it rises 10 points and fades in, a beat after the one before
// (Today's Entrance on the Mac). Its children stack full width. With `enabled` false, or reduced motion, it is
// simply there.
Item {
    id: entrance
    default property alias content: column.data
    property int index: 0
    property bool shown: true
    property bool animated: true

    readonly property bool hidden: animated && !Theme.reducedMotion && !arrived
    property bool arrived: false

    Layout.fillWidth: true
    implicitHeight: column.implicitHeight

    Timer {
        interval: 50 * entrance.index + 1
        running: entrance.shown && !entrance.arrived
        onTriggered: entrance.arrived = true
    }

    ColumnLayout {
        id: column
        width: parent.width
        spacing: 0
        opacity: entrance.hidden ? 0 : 1
        transform: Translate { y: entrance.hidden ? 10 : 0; Behavior on y { Spring {} } }
        Behavior on opacity { Spring {} }
    }
}
