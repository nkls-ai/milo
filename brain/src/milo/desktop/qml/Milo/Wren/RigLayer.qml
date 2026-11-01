import QtQuick

// A hidden offscreen layer over `box` (figure space) for an effect to read: a shape to clip by, or content to clip.
// Children draw in figure space; the layer renders `resolution` texture pixels per unit.
Item {
    id: layer
    property rect box
    property real resolution: 2
    default property alias content: inner.data

    x: box.x; y: box.y; width: box.width; height: box.height
    visible: false
    layer.enabled: true
    layer.smooth: true
    layer.samples: 4
    layer.textureSize: Qt.size(Math.ceil(box.width * resolution), Math.ceil(box.height * resolution))

    Item { id: inner; x: -layer.box.x; y: -layer.box.y }
}
