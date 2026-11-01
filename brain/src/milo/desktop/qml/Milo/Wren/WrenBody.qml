import QtQuick
import QtQuick.Effects
import Milo

// His body (WrenRig.swift's drawBody): the lavender ball, his belly, the light on his crown, the scarf's band with
// its shadow, all cut to his outline in rig.mjs; a rim of light on the side away from the key light; then the cheek
// tufts that poke out of him. Figure space. On Qt's software renderer (no effects) the band's shadow is sharp and the
// rim light is left out.
Item {
    id: root
    // frame(...).body from rig.mjs
    property var body
    property bool small
    // Texture pixels per figure unit for the rim light's layers.
    property real resolution: 2

    readonly property var rig: Theme.rig
    readonly property bool effects: GraphicsInfo.api !== GraphicsInfo.Software
    readonly property rect box: Qt.rect(30, 58, 140, 134)

    RigRadial { path: root.body.path; center: root.body.light }
    RigFill { path: root.body.belly; fill: root.rig.bellyHi; fillEnd: root.rig.bellyLo; from: 124; to: 186 }
    RigSoft {
        cx: 100; cy: 190; rx: 78; ry: 30
        path: root.body.occlusion; color: root.rig.shade; alpha: 0.26
    }
    RigSoft {
        cx: root.body.keyLight[0]; cy: root.body.keyLight[1]; rx: 24; ry: 12; rotation: -24
        path: root.body.keyLightPath; color: "white"; alpha: 0.36
    }
    // soft feather ticks around his crown, so his head isn't a bare ball
    RigLine { path: root.body.fluff; color: root.rig.fluff; lineWidth: 1.1; alpha: 0.32 }

    // the scarf band, with the soft shadow it casts on him
    RigFill {
        id: bandShadow
        path: root.body.bandShadow
        fill: root.rig.shade; alpha: root.effects ? 0.3 : 0.16
        layer.enabled: root.effects
        layer.effect: MultiEffect { blurEnabled: true; blur: 0.5; blurMax: 8 }
        width: root.box.x + root.box.width; height: root.box.y + root.box.height
    }
    RigFill {
        path: root.body.band
        fill: root.rig.scarfHi; fillEnd: root.rig.scarfLo; from: root.body.scarfY - 4; to: root.body.scarfY + 12
    }
    RigLine { path: root.body.ribs; color: root.rig.scarfRib; lineWidth: 1; alpha: 0.4 }
    RigLine { path: root.body.edge; color: root.rig.scarfEdge; lineWidth: 1.4; alpha: 0.7 }

    // rim light: his outline in light, except where the body shifted toward the light and blurred covers it
    Loader {
        active: root.effects
        sourceComponent: Item {
            RigLayer {
                id: rim
                box: root.box
                resolution: root.resolution
                RigFill { path: root.body.path; fill: root.rig.rim; alpha: 0.55 }
            }
            RigLayer {
                id: shifted
                box: root.box
                resolution: root.resolution
                RigFill { x: -5; y: 3.5; path: root.body.path; fill: "black" }
            }
            MultiEffect {
                id: shiftedBlur
                x: root.box.x; y: root.box.y; width: root.box.width; height: root.box.height
                source: shifted
                blurEnabled: true
                blur: 1
                blurMax: Math.round(3 * root.resolution)
                autoPaddingEnabled: false
                visible: false
                layer.enabled: true
            }
            MultiEffect {
                x: root.box.x; y: root.box.y; width: root.box.width; height: root.box.height
                source: rim
                maskEnabled: true
                maskInverted: true
                maskSource: shiftedBlur
                maskThresholdMin: 0.5
                maskSpreadAtMin: 1
            }
        }
    }

    // fluffy cheeks: two little feather points poking out at each side of his face, in his own colours
    RigRadial { path: root.body.tufts; center: root.body.light }
}
