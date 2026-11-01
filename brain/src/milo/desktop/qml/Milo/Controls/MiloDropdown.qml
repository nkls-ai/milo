import QtQuick
import QtQuick.Layouts
import QtQuick.Templates as T
import Milo

// A compact pop-up picker (a menu-style Picker on the Mac): the chosen label and a chevron; a click opens the
// choices on Milo's paper. `options` are [{value, label}]; emits picked(value). Each choice is named by its label.
T.AbstractButton {
    id: picker
    property var options: []
    property var current
    property string name: ""
    signal picked(var value)

    readonly property int index: {
        for (let i = 0; i < options.length; ++i)
            if (JSON.stringify(options[i].value) === JSON.stringify(current)) return i
        return -1
    }

    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    horizontalPadding: 10
    verticalPadding: 5
    implicitWidth: implicitContentWidth + leftPadding + rightPadding
    implicitHeight: implicitContentHeight + topPadding + bottomPadding
    scale: pressed ? 0.97 : 1
    Behavior on scale { Spring { kind: "snappy" } }
    Accessible.role: Accessible.ComboBox
    Accessible.name: name
    Accessible.description: index >= 0 ? options[index].label : ""
    Keys.onReturnPressed: clicked()
    Keys.onSpacePressed: clicked()
    onClicked: menu.open()

    contentItem: Row {
        spacing: 6
        MiloText {
            anchors.verticalCenter: parent.verticalCenter
            text: picker.index >= 0 ? picker.options[picker.index].label : ""
            weight: "medium"
        }
        Icon { anchors.verticalCenter: parent.verticalCenter; name: "chevron.down"; size: 10; color: Tones.fade(Theme.ink, 0.55); weight: "bold" }
    }
    background: Rectangle {
        radius: 8
        color: Tones.fade(Theme.ink, picker.hovered ? 0.1 : 0.065)
        Behavior on color { ColorSpring { kind: "snappy" } }
        FocusRing { shown: picker.visualFocus }
    }

    T.Popup {
        id: menu
        y: picker.height + 4
        x: picker.width - implicitWidth
        padding: 5
        focus: true
        closePolicy: T.Popup.CloseOnEscape | T.Popup.CloseOnPressOutside
        implicitWidth: Math.max(picker.width, list.implicitWidth + leftPadding + rightPadding)
        implicitHeight: list.implicitHeight + topPadding + bottomPadding
        background: Surface {
            radius: Theme.radius.medium
            fill: Theme.dark ? Theme.card : Theme.tint
            lift: 0.2
            liftY: 5
        }
        contentItem: ColumnLayout {
            id: list
            spacing: 0
            Repeater {
                model: picker.options
                T.AbstractButton {
                    id: item
                    required property var modelData
                    required property int index
                    objectName: modelData.label
                    Layout.fillWidth: true
                    hoverEnabled: true
                    focusPolicy: Qt.StrongFocus
                    horizontalPadding: 10
                    verticalPadding: 6
                    implicitWidth: implicitContentWidth + leftPadding + rightPadding
                    implicitHeight: implicitContentHeight + topPadding + bottomPadding
                    Accessible.role: Accessible.MenuItem
                    Accessible.name: modelData.label
                    Keys.onReturnPressed: clicked()
                    onClicked: { menu.close(); if (index !== picker.index) picker.picked(modelData.value) }
                    background: Rectangle {
                        radius: 7
                        color: item.hovered || item.visualFocus ? Tones.fade(Theme.primary, 0.12) : "transparent"
                    }
                    contentItem: RowLayout {
                        spacing: 8
                        Icon { name: "check"; size: 11; color: Theme.primary; opacity: item.index === picker.index ? 1 : 0 }
                        MiloText { text: item.modelData.label; weight: item.index === picker.index ? "semibold" : "regular" }
                    }
                }
            }
        }
    }
}
