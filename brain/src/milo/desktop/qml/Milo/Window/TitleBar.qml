import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls

// The top of the frameless window: drag it to move, double-click to fill the screen. Milo's name on the left; in a
// narrow window the sidebar button, the way back and Today (the Mac's narrowBar); the window's own buttons on the right.
Item {
    id: bar
    property Window window
    property bool narrow: false
    implicitHeight: 40

    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton
        onPressed: bar.window.startSystemMove()
        onDoubleClicked: bar.window.visibility === Window.Maximized ? bar.window.showNormal() : bar.window.showMaximized()
    }

    RowLayout {
        anchors { fill: parent; leftMargin: Theme.space.l; rightMargin: Theme.space.s }
        spacing: Theme.space.xs + 2

        IconButton {
            visible: bar.narrow
            iconName: "list.bullet"
            label: "Show the conversations (Ctrl+0)"
            wash: false
            onClicked: route.toggleSidebar()
        }
        IconButton {
            visible: bar.narrow && route.page !== "today" && route.page !== "live" && route.page !== "usage"
            iconName: "chevron.right"
            rotation: 180
            label: "Back (Alt+Left)"
            wash: false
            onClicked: route.back()
        }
        MiloText {
            text: "Milo"
            size: Theme.type.callout
            weight: "bold"
            rounded: true
            tone: 0.8
        }
        ThinkingDots {
            visible: !shell.connected
            dot: 4
            color: Tones.fade(Theme.ink, 0.35)
            Layout.alignment: Qt.AlignVCenter
        }
        MiloText {
            visible: !shell.connected
            text: "Waking up…"
            size: Theme.type.caption
            tone: 0.55
        }
        Item { Layout.fillWidth: true; height: 1 }
        IconButton {
            visible: bar.narrow && route.page !== "today"
            iconName: "sun.max"
            label: "Today (Ctrl+1)"
            wash: false
            onClicked: route.go("today")
        }
        MiloButton {
            visible: presence.canStop
            kind: "danger"
            size: "small"
            text: "Stop"
            iconName: "stop"
            tip: "Stops what Milo is saying and doing"
            onClicked: shell.stopAll()
        }
        IconButton {
            iconName: "wrench"
            label: "Settings (Ctrl+,)"
            wash: false
            onClicked: route.go("settings")
        }
        WindowButton { kind: "minimize"; onClicked: bar.window.showMinimized() }
        WindowButton {
            kind: bar.window.visibility === Window.Maximized ? "restore" : "maximize"
            onClicked: bar.window.visibility === Window.Maximized ? bar.window.showNormal() : bar.window.showMaximized()
        }
        WindowButton { kind: "close"; onClicked: bar.window.close() }
    }
}
