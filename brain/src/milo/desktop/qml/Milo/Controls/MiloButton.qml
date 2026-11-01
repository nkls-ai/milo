import QtQuick
import QtQuick.Templates as T
import Milo

// Milo's button: gives a little under the finger in his spring, washes on hover, and shows a ring with keyboard focus.
//
// kind:  "primary"   filled in Milo's colour (PillButtonStyle, PageButtonStyle prominent)
//        "secondary" Milo's colour on a light wash of it (PillButtonStyle(prominent: false))
//        "quiet"     ink on a faint wash (PageButtonStyle, QuietChoiceStyle, AnswerButtonStyle's No)
//        "outline"   Milo's colour in a thin frame (Run now)
//        "danger"    the failed colour in a thin frame (Stop)
//        "plain"     words only, like a link (Stop all, Show the words)
// size:  "small" | "regular" | "large" (the answer buttons: a little bigger, at least 64 wide)
// shape: "capsule" | "rounded"
T.AbstractButton {
    id: button
    property string kind: "primary"
    property string size: "regular"
    property string shape: kind === "outline" || kind === "danger" ? "rounded" : "capsule"
    property string iconName: ""
    property bool iconOnly: false
    property string tip: ""
    property color tint: kind === "danger" ? Tones.failed : Theme.primary

    readonly property bool filled: kind === "primary"
    readonly property real fontSize: size === "small" ? 11.5 : size === "large" ? 13.5 : Theme.type.body
    readonly property color ink: filled ? Theme.primaryInk
                               : kind === "quiet" ? Tones.fade(Theme.ink, enabled ? 0.85 : 0.5)
                               : tint
    readonly property color wash: filled ? tint
                                : kind === "secondary" ? Tones.fade(tint, hovered ? 0.18 : 0.12)
                                : kind === "quiet" ? Tones.fade(Theme.ink, hovered && enabled ? 0.11 : 0.065)
                                : kind === "plain" ? "transparent"
                                : Tones.fade(tint, hovered ? 0.08 : 0)

    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    opacity: enabled ? 1 : 0.5
    implicitWidth: Math.max(size === "large" && !iconOnly ? 64 : 0, implicitContentWidth + leftPadding + rightPadding)
    implicitHeight: implicitContentHeight + topPadding + bottomPadding
    horizontalPadding: kind === "plain" ? 0 : iconOnly ? (size === "small" ? 6 : 8)
                     : size === "small" ? 9 : size === "large" ? 10 : 14
    verticalPadding: kind === "plain" ? 0 : size === "small" ? 4 : 7
    scale: pressed ? 0.95 : 1
    Behavior on scale { Spring { kind: "snappy" } }

    Accessible.role: Accessible.Button
    Accessible.name: text
    Accessible.description: tip
    Keys.onReturnPressed: clicked()
    Keys.onEnterPressed: clicked()

    contentItem: Item {
        implicitWidth: row.implicitWidth
        implicitHeight: row.implicitHeight
        Row {
            id: row
            // Centred in the larger minimum width of an answer button.
            anchors.centerIn: parent
            spacing: 5
            Icon {
                anchors.verticalCenter: parent.verticalCenter
                visible: button.iconName !== ""
                name: button.iconName
                size: button.fontSize - 1
                color: button.ink
                weight: "bold"
            }
            MiloText {
                anchors.verticalCenter: parent.verticalCenter
                visible: !button.iconOnly
                text: button.text
                size: button.fontSize
                weight: button.kind === "quiet" && button.size === "small" ? "medium" : "semibold"
                rounded: true
                ink: button.ink
            }
        }
    }

    background: Rectangle {
        radius: button.shape === "capsule" ? height / 2 : (button.size === "large" ? 9 : 8)
        color: button.wash
        border.width: button.kind === "outline" || button.kind === "danger" ? 1 : 0
        border.color: Tones.fade(button.tint, 0.6)
        Behavior on color { ColorSpring { kind: "snappy" } }

        FocusRing { shown: button.visualFocus }
    }

    Tip { text: button.tip; shown: button.hovered && button.tip !== "" }
}
