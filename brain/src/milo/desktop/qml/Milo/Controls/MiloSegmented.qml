import QtQuick
import QtQuick.Templates as T
import Milo

// A segmented picker (`.pickerStyle(.segmented)`): the chosen segment's card slides under the words in a spring.
// `options` are [{value, label}]; `current` is the chosen value. Emits picked(value) when the user chooses another;
// the owner updates `current`. Arrow keys move the choice.
FocusScope {
    id: picker
    property var options: []
    property var current
    property string name: ""
    signal picked(var value)

    readonly property int index: {
        for (let i = 0; i < options.length; ++i) if (options[i].value === current) return i
        return -1
    }

    implicitWidth: row.implicitWidth + 4
    implicitHeight: row.implicitHeight + 4
    activeFocusOnTab: true
    Accessible.role: Accessible.PageTabList
    Accessible.name: name
    Keys.onLeftPressed: if (index > 0) picked(options[index - 1].value)
    Keys.onRightPressed: if (index < options.length - 1) picked(options[index + 1].value)

    Rectangle {
        anchors.fill: parent
        radius: 9
        color: Tones.fade(Theme.ink, 0.07)
        FocusRing { shown: picker.activeFocus }
    }
    Rectangle {
        id: slider
        readonly property Item target: picker.index >= 0 ? repeater.itemAt(picker.index) : null
        visible: target !== null
        x: target ? target.x + 2 : 2
        y: 2
        width: target ? target.width : 0
        height: parent.height - 4
        radius: 7
        color: Theme.dark ? Tones.fade(Theme.ink, 0.16) : Theme.card
        border.color: Theme.rule
        Behavior on x { Spring {} }
        Behavior on width { Spring {} }
    }
    Row {
        id: row
        x: 2
        y: 2
        Repeater {
            id: repeater
            model: picker.options
            T.AbstractButton {
                id: segment
                required property var modelData
                required property int index
                objectName: modelData.label  // tests click a segment by its words
                readonly property bool on: index === picker.index
                hoverEnabled: true
                focusPolicy: Qt.NoFocus
                horizontalPadding: 12
                verticalPadding: 4
                implicitWidth: implicitContentWidth + leftPadding + rightPadding
                implicitHeight: implicitContentHeight + topPadding + bottomPadding
                Accessible.role: Accessible.PageTab
                Accessible.name: modelData.label
                Accessible.selected: on
                onClicked: if (!on) picker.picked(modelData.value)
                contentItem: MiloText {
                    text: segment.modelData.label
                    size: 12
                    weight: segment.on ? "semibold" : "medium"
                    tone: segment.on ? 1 : segment.hovered ? 0.8 : 0.65
                    horizontalAlignment: Text.AlignHCenter
                }
            }
        }
    }
}
