import QtQuick
import QtQuick.Layouts
import QtQuick.Templates as T
import Milo
import Milo.Controls

// Notes, To-dos and Transcript under the header (TabStrip). The underline slides to the chosen tab in Milo's spring.
// `tab` is "notes" | "todos" | "transcript"; emits picked(tab).
Item {
    id: strip
    property string tab: "notes"
    property int todos: 0
    signal picked(string tab)

    readonly property var tabs: [["notes", "Notes"], ["todos", "To-dos"], ["transcript", "Transcript"]]
    Layout.fillWidth: true
    implicitHeight: row.implicitHeight
    Accessible.role: Accessible.PageTabList

    Row {
        id: row
        x: 22
        spacing: 18
        Repeater {
            id: repeater
            model: strip.tabs
            T.AbstractButton {
                id: button
                required property var modelData
                readonly property bool on: strip.tab === modelData[0]
                objectName: "tab-" + modelData[0]
                hoverEnabled: true
                focusPolicy: Qt.StrongFocus
                implicitWidth: label.implicitWidth
                implicitHeight: label.implicitHeight + 8.5
                Accessible.role: Accessible.PageTab
                Accessible.name: modelData[1]
                Accessible.selected: on
                Keys.onReturnPressed: clicked()
                onClicked: strip.picked(modelData[0])
                contentItem: Item {}
                Row {
                    id: label
                    spacing: 5
                    MiloText {
                        text: button.modelData[1]
                        weight: button.on ? "semibold" : "medium"
                        rounded: true
                        tone: button.on ? 1 : button.hovered ? 0.75 : 0.55
                    }
                    Badge {
                        anchors.verticalCenter: parent.verticalCenter
                        visible: button.modelData[0] === "todos" && strip.todos > 0
                        count: strip.todos
                    }
                }
                FocusRing { shown: button.visualFocus; radius: 4 }
            }
        }
    }
    Rectangle {
        readonly property Item target: repeater.count ? repeater.itemAt(strip.tabs.findIndex(t => t[0] === strip.tab)) : null
        visible: target !== null
        x: row.x + (target ? target.x : 0)
        width: target ? target.width : 0
        y: parent.height - height
        height: 2.5
        radius: 1.25
        color: Theme.primary
        Behavior on x { Spring {} }
        Behavior on width { Spring {} }
    }
    Rule { anchors.bottom: parent.bottom; width: parent.width }
}
