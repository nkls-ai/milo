import QtQuick
import QtQuick.Layouts
import QtQuick.Templates as T
import Milo

// A "…" button that opens a short menu on Milo's paper (a borderless Menu on the Mac). `items` are
// [{value, label, danger}]; emits picked(value).
IconButton {
    id: button
    property var items: []
    signal picked(var value)

    iconName: "ellipsis"
    wash: false
    size: 22
    iconSize: 14
    onClicked: menu.open()
    Accessible.role: Accessible.ButtonMenu

    T.Popup {
        id: menu
        y: button.height + 4
        x: button.width - implicitWidth
        padding: 5
        modal: false
        focus: true
        closePolicy: T.Popup.CloseOnEscape | T.Popup.CloseOnPressOutside
        implicitWidth: Math.max(160, list.implicitWidth + leftPadding + rightPadding)
        implicitHeight: list.implicitHeight + topPadding + bottomPadding
        transformOrigin: T.Popup.TopRight
        enter: Transition { ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 1000 * Theme.reducedFade; easing.type: Easing.OutCubic }
            NumberAnimation { property: "scale"; from: Theme.reducedMotion ? 1 : 0.94; to: 1; duration: 220; easing.type: Easing.OutBack }
        } }
        exit: Transition { NumberAnimation { property: "opacity"; to: 0; duration: 1000 * Theme.reducedFade; easing.type: Easing.OutCubic } }

        background: Surface {
            radius: Theme.radius.medium
            fill: Theme.dark ? Theme.card : Theme.tint
            lift: 0.2
            liftRadius: 12
            liftY: 5
        }
        contentItem: ColumnLayout {
            id: list
            spacing: 0
            Repeater {
                model: button.items
                T.AbstractButton {
                    id: item
                    required property var modelData
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
                    onClicked: { menu.close(); button.picked(modelData.value) }
                    background: Rectangle {
                        radius: 7
                        color: item.hovered || item.visualFocus ? Tones.fade(Theme.primary, 0.12) : "transparent"
                    }
                    contentItem: MiloText {
                        text: item.modelData.label
                        ink: item.modelData.danger ? Tones.failed : Theme.ink
                    }
                }
            }
        }
    }
}
