import QtQuick
import QtQuick.Layouts
import QtQuick.Templates as T
import Milo

// A few choices as rows, all visible. The chosen one gets a wash and a filled dot that springs in.
// `choices` are [{value, label}]; `selected` the chosen value. Emits chosen(value).
ColumnLayout {
    id: list
    property var choices: []
    property var selected
    property string name: ""
    signal chosen(var value)

    spacing: Theme.space.xs
    Layout.fillWidth: true
    Accessible.role: Accessible.List
    Accessible.name: name

    Repeater {
        model: list.choices
        T.AbstractButton {
            id: row
            required property var modelData
            objectName: modelData.label  // tests click a choice by its words
            readonly property bool on: JSON.stringify(modelData.value) === JSON.stringify(list.selected)
            Layout.fillWidth: true
            hoverEnabled: true
            focusPolicy: Qt.StrongFocus
            horizontalPadding: 10
            verticalPadding: 7
            implicitHeight: implicitContentHeight + topPadding + bottomPadding
            Accessible.role: Accessible.RadioButton
            Accessible.name: modelData.label
            Accessible.checked: on
            Keys.onReturnPressed: clicked()
            onClicked: list.chosen(modelData.value)

            background: Rectangle {
                radius: Theme.radius.small
                color: row.on ? Tones.fade(Theme.primary, 0.12)
                              : row.hovered ? Tones.fade(Theme.ink, 0.04) : Tones.fade(Theme.ink, 0)
                Behavior on color { ColorSpring {} }
                FocusRing { shown: row.visualFocus }
            }
            contentItem: RowLayout {
                spacing: 10
                Item {
                    implicitWidth: 16
                    implicitHeight: 16
                    Rectangle {
                        anchors.fill: parent
                        radius: 8
                        color: "transparent"
                        border.width: 1.5
                        border.color: row.on ? Theme.primary : Tones.fade(Theme.ink, 0.25)
                        Behavior on border.color { ColorSpring {} }
                    }
                    Rectangle {
                        anchors.fill: parent
                        anchors.margins: 4
                        radius: width / 2
                        color: Theme.primary
                        scale: row.on ? 1 : 0.01
                        Behavior on scale { Spring {} }
                    }
                }
                MiloText {
                    Layout.fillWidth: true
                    text: row.modelData.label
                    weight: row.on ? "semibold" : "regular"
                    tone: row.on ? 1 : 0.8
                    wrapMode: Text.WordWrap
                }
            }
        }
    }
}
