import QtQuick
import QtQuick.Templates as T
import Milo

// A thin overlay scroll bar, as on the Mac: hidden at rest, it fades in while scrolling and widens under the pointer.
T.ScrollBar {
    id: bar
    hoverEnabled: true
    policy: T.ScrollBar.AsNeeded
    minimumSize: 0.08
    padding: 2
    implicitWidth: 10
    implicitHeight: 10

    contentItem: Rectangle {
        implicitWidth: bar.hovered || bar.pressed ? 7 : 5
        radius: width / 2
        color: Tones.fade(Theme.ink, bar.pressed ? 0.45 : 0.3)
        opacity: bar.policy === T.ScrollBar.AlwaysOn || (bar.size < 1 && (bar.active || bar.hovered)) ? 1 : 0
        x: bar.width - width - bar.rightPadding
        Behavior on opacity { Spring { kind: "gentle" } }
        Behavior on implicitWidth { Spring { kind: "snappy" } }
    }
}
