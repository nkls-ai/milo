import QtQuick
import QtQuick.Window
import Milo
import Milo.Controls

// The Milo window (ConversationView.swift): the conversations down the side, and Today, a conversation, a task or
// one of the other pages beside them. Frameless, on Milo's own paper with rounded corners; closing only hides it.
// Context: shell, route, conversations, entries, presence, store, pages (see milo/desktop/controller.py).
Window {
    id: root
    width: 980
    height: 660
    minimumWidth: 320
    minimumHeight: 300
    title: "Milo"
    color: "transparent"
    flags: Qt.Window | Qt.FramelessWindowHint

    readonly property bool maximized: visibility === Window.Maximized || visibility === Window.FullScreen
    // Room for the soft shadow round the paper; none when the window fills the screen.
    readonly property real inset: maximized ? 0 : Theme.space.s + 2
    readonly property bool narrow: paper.width < 600
    readonly property real sidebarWidth: 236

    onClosing: function(close) { close.accepted = false; root.hide() }

    Surface {
        id: paper
        anchors.fill: parent
        anchors.margins: root.inset
        radius: root.maximized ? 0 : Theme.radius.window
        fill: Theme.tint
        lift: root.maximized ? 0 : 0.16
        liftRadius: root.inset
        liftY: 3
    }

    Item {
        id: content
        anchors.fill: paper
        // Nothing here clips to the paper's rounded corners (a layer mask costs a whole-window texture every
        // frame): the few surfaces that reach a corner round it themselves.
        TitleBar {
            id: bar
            anchors { left: parent.left; right: parent.right; top: parent.top }
            window: root
            narrow: root.narrow
        }

        Row {
            id: body
            anchors { left: parent.left; right: parent.right; top: bar.bottom; bottom: parent.bottom }

            Sidebar {
                id: side
                corner: paper.radius
                visible: !root.narrow
                width: root.sidebarWidth
                height: body.height
            }
            Rectangle {
                visible: !root.narrow
                width: 1
                height: body.height
                color: Theme.rule
            }
            Column {
                width: body.width - (root.narrow ? 0 : root.sidebarWidth + 1)
                height: body.height

                NoticeBar { id: notice; width: parent.width }
                KeptDictation { id: kept; width: parent.width }
                PageHost {
                    width: parent.width
                    height: parent.height - notice.height - kept.height - dock.height
                }
                Dock {
                    id: dock
                    corners: Qt.size(root.narrow ? paper.radius : 0, paper.radius)
                    width: parent.width
                    height: visible ? implicitHeight : 0
                }
            }
        }

        // A narrow window: the sidebar slides over the page.
        Rectangle {
            anchors { fill: body }
            color: "#000000"
            opacity: root.narrow && route.sidebarShown ? 0.18 : 0
            visible: opacity > 0
            Behavior on opacity { Spring {} }
            MouseArea { anchors.fill: parent; onClicked: route.setSidebarShown(false) }
        }
        Sidebar {
            id: narrowSide
            corner: paper.radius
            visible: root.narrow
            width: root.sidebarWidth
            height: body.height
            y: body.y
            x: route.sidebarShown ? 0 : -width - 20
            Behavior on x { Spring {} }
        }
    }

    ResizeEdges { anchors.fill: parent; window: root; enabled: !root.maximized; inset: root.inset }

    Shortcuts { onSearch: root.narrow ? narrowSide.focusSearch() : side.focusSearch() }
}
