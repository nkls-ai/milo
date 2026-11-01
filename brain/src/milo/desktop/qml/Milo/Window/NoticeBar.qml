import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls

// A notice over the page: the brain reconnecting, a key that can't be heard, a file saved. It folds away when there
// is nothing to say or the user dismisses it.
Item {
    id: bar
    readonly property bool shown: shell.notice !== ""
    implicitHeight: shown ? note.implicitHeight + 2 * Theme.space.s : 0
    height: implicitHeight
    clip: true
    Behavior on height { Spring {} }

    Callout {
        id: note
        x: Theme.space.l
        y: Theme.space.s
        width: bar.width - 2 * Theme.space.l
        opacity: bar.shown ? 1 : 0
        Behavior on opacity { Spring {} }
        text: shell.notice
        icon: shell.connected ? "info.circle" : "bolt"
        button: shell.connected ? "" : shell.canRestart ? "Restart brain" : ""
        onClicked: shell.restartBrain()
    }
    IconButton {
        visible: bar.shown && shell.connected
        anchors { right: note.right; rightMargin: 8; verticalCenter: note.verticalCenter }
        iconName: "xmark"
        label: "Dismiss"
        size: 20
        wash: false
        onClicked: shell.dismissNotice()
    }
}
