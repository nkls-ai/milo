import QtQuick
import Milo

// Shows and hides its children like SwiftUI's .transition(.scale(scale: from).combined(with: .opacity)):
//
//     Appear { shown: presence.bubble !== ""; Bubble { ... } }
//     Appear { shown: done; from: 0.5; kind: "snappy"; Tick {} }
//
// Sized by its children and scaled about its centre. Hidden, it is invisible (no input, no drawing). Under reduced
// motion it only fades.
Item {
    id: root
    property bool shown: true
    property real from: 0.92
    property string kind: "spring"

    implicitWidth: childrenRect.width
    implicitHeight: childrenRect.height
    opacity: shown ? 1 : 0
    scale: shown || Theme.reducedMotion ? 1 : from
    visible: opacity > 0.002

    Behavior on opacity { Spring { kind: root.kind } }
    Behavior on scale { Spring { kind: root.kind } }
}
