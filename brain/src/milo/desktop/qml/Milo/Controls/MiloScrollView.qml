import QtQuick
import QtQuick.Layouts
import QtQuick.Templates as T
import Milo

// A page that scrolls: its children stack in a column at most `maxContentWidth` wide, against the leading edge like
// the Mac's pages. A mouse wheel glides in Milo's snappy spring instead of jumping a notch at a time; a trackpad
// scrolls as the fingers move. The bar is thin, over the content, and shows only while scrolling or hovered.
Flickable {
    id: view
    default property alias content: column.data
    property real maxContentWidth: 620
    property real leftPadding: Theme.space.xl
    property real rightPadding: Theme.space.xl
    property real topPadding: 22
    property real bottomPadding: Theme.space.xl
    property alias spacing: column.spacing
    readonly property bool atEnd: contentY >= contentHeight - height - 2

    function scrollTo(y) {
        glide.to = Math.max(0, Math.min(y, contentHeight - height))
        glide.restart()
    }
    function scrollToEnd() { scrollTo(contentHeight) }

    contentWidth: width
    contentHeight: column.implicitHeight + topPadding + bottomPadding
    clip: true
    flickableDirection: Flickable.VerticalFlick
    boundsBehavior: Flickable.StopAtBounds
    pixelAligned: true
    Accessible.role: Accessible.Pane
    T.ScrollBar.vertical: MiloScrollBar {}

    // Listed by hand: the default property sends children into the column.
    flickableData: ColumnLayout {
        id: column
        x: view.leftPadding
        y: view.topPadding
        width: Math.max(0, Math.min(view.maxContentWidth, view.width - view.leftPadding - view.rightPadding))
        spacing: Theme.space.m
    }
    resources: Spring { id: glide; target: view; property: "contentY"; kind: "snappy" }
    data: Item {
        anchors.fill: parent
        WheelHandler {
            acceptedDevices: PointerDevice.Mouse
            onWheel: event => {
                view.scrollTo((glide.running ? glide.to : view.contentY) - event.angleDelta.y)
                event.accepted = true
            }
        }
    }
}
