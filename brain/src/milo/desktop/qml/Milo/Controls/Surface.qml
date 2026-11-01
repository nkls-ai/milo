import QtQuick
import QtQuick.Effects
import Milo

// The paper of a card: a rounded fill, a hairline edge and a soft lift in Milo's colour (ThemedCard's background).
// The shadow falls from a twin shape under the paper, so the edge and the text on it stay crisp.
Item {
    id: surface
    property real radius: Theme.radius.card
    property color fill: Theme.card
    property color edge: Theme.rule
    property real edgeWidth: 1
    // The shadow: its strength in Theme.primary, how far it spreads and how far it drops. 0 for none.
    property real lift: 0.07
    property real liftRadius: 12
    property real liftY: 4

    Rectangle {
        id: twin
        anchors.fill: parent
        radius: surface.radius
        // Under the translucent light card, the window's own paper: the card looks the same as without a twin.
        color: Theme.tint
        visible: false
    }
    MultiEffect {
        anchors.fill: twin
        source: twin
        visible: surface.lift > 0
        shadowEnabled: true
        shadowColor: Theme.primary
        shadowOpacity: surface.lift
        blurMax: Math.max(1, surface.liftRadius * 2)
        shadowBlur: 1
        shadowVerticalOffset: surface.liftY
    }
    Rectangle {
        anchors.fill: parent
        radius: surface.radius
        color: surface.fill
        border.color: surface.edge
        border.width: surface.edgeWidth
    }
}
