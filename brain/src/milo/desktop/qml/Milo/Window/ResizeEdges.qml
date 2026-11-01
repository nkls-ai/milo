import QtQuick

// The frameless window's edges and corners: press and drag to resize, as on a framed window.
Item {
    id: edges
    property Window window
    property real inset: 0
    readonly property real grip: Math.max(6, inset)

    component Edge: MouseArea {
        property int sides: 0
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton
        onPressed: edges.window.startSystemResize(sides)
    }

    Edge { sides: Qt.LeftEdge; cursorShape: Qt.SizeHorCursor; x: 0; y: grip; width: grip; height: parent.height - 2 * grip }
    Edge { sides: Qt.RightEdge; cursorShape: Qt.SizeHorCursor; x: parent.width - grip; y: grip; width: grip; height: parent.height - 2 * grip }
    Edge { sides: Qt.TopEdge; cursorShape: Qt.SizeVerCursor; x: grip; y: 0; width: parent.width - 2 * grip; height: Math.max(3, grip / 2) }
    Edge { sides: Qt.BottomEdge; cursorShape: Qt.SizeVerCursor; x: grip; y: parent.height - grip; width: parent.width - 2 * grip; height: grip }
    Edge { sides: Qt.TopEdge | Qt.LeftEdge; cursorShape: Qt.SizeFDiagCursor; width: grip; height: grip }
    Edge { sides: Qt.TopEdge | Qt.RightEdge; cursorShape: Qt.SizeBDiagCursor; x: parent.width - grip; width: grip; height: grip }
    Edge { sides: Qt.BottomEdge | Qt.LeftEdge; cursorShape: Qt.SizeBDiagCursor; y: parent.height - grip; width: grip; height: grip }
    Edge { sides: Qt.BottomEdge | Qt.RightEdge; cursorShape: Qt.SizeFDiagCursor; x: parent.width - grip; y: parent.height - grip; width: grip; height: grip }
}
