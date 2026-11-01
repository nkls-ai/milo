import QtQuick
import QtQuick.Shapes
import Milo
import "icons.mjs" as Icons

// An icon from icons.mjs, stroked like an SF Symbol at `size` points. `filled` also fills its closed shapes, for the
// Mac's ".fill" symbols. Decorative: name what it means on the control that carries it.
Item {
    id: icon
    property string name: ""
    property real size: Theme.type.body
    property color color: Theme.ink
    property string weight: "semibold"
    property bool filled: false

    implicitWidth: size
    implicitHeight: size
    Accessible.ignored: true

    SmoothShape {
        anchors.fill: parent
        visible: Icons.paths[icon.name] !== undefined
        ShapePath {
            scale: Qt.size(icon.size / 24, icon.size / 24)
            strokeColor: icon.color
            strokeWidth: Math.max(1.1, icon.size / 12 * ({ regular: 0.9, medium: 1, semibold: 1.15, bold: 1.35 }[icon.weight] || 1))
            fillColor: icon.filled ? icon.color : "transparent"
            capStyle: ShapePath.RoundCap
            joinStyle: ShapePath.RoundJoin
            PathSvg { path: Icons.paths[icon.name] || "" }
        }
    }
}
