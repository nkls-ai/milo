import QtQuick
import Milo
import "rig.mjs" as Rig

// Milo drawn at one pose (WrenRig.swift + WrenView.swift's layer tree), framed like the Mac's 120 pt figure: his
// middle centred, his feet near the bottom, scaled to fit the item. Each part is a GPU shape placed by a transform,
// so moving him changes transforms and a part's outline is rebuilt only when its shape changes.
//
//     WrenRig { width: 120; height: 120; pose: motion.pose }
//
// `breath` (0 none) and `breathPeriod` breathe him about his feet on Qt's clock, between pose changes.
Item {
    id: root
    // A pose from pose.mjs (rest(), or a Motion's pose).
    property var pose
    // Helper size and smaller: fewer fine lines, a bolder silhouette.
    property bool small: width < 60
    property real breath: 0
    property real breathPeriod: 3.6

    readonly property var f: Rig.frame(pose, small)
    readonly property var rig: Theme.rig
    readonly property real k: Math.min(width, height) / Rig.VIEW.size
    // Texture pixels per figure unit for the parts that need a layer (the clipped body).
    readonly property real resolution: Math.max(1, k * (Window.window ? Window.window.devicePixelRatio : 1) * 1.5)
    readonly property var wing: Rig.foldedWing(-1, 42)
    readonly property var wingR: Rig.foldedWing(1, 42)
    readonly property var openL: Rig.openWing(-1, 0.72)
    readonly property var openR: Rig.openWing(1, 0.72)
    readonly property var pad: Rig.notepad()
    readonly property var pencil: Rig.pencil()

    // The parts are plain GPU triangles (Qt 6.8's curve renderer drops shapes whose outline changes while it
    // animates); the rig is antialiased as a whole by drawing it into a multisampled layer. Qt's software renderer
    // smooths shapes by itself.
    layer.enabled: GraphicsInfo.api !== GraphicsInfo.Software
    layer.samples: 4
    layer.smooth: true

    // Figure space onto the item: the 120 pt framing, scaled and centred.
    Item {
        id: stage
        x: (root.width - Rig.VIEW.size * root.k) / 2 - Rig.VIEW.x * root.k
        y: (root.height - Rig.VIEW.size * root.k) / 2 - Rig.VIEW.y * root.k
        transform: Scale { xScale: root.k; yScale: root.k }

        // Ground shadow: shrinks and fades as he rises.
        RigPart {
            m: root.f.shadow.m
            opacity: root.f.shadow.opacity
            RigSoft { rx: 46; ry: 7.5; color: root.rig.ground; alpha: 0.24 }
        }

        Item {
            id: breathing
            transform: Scale {
                id: breathScale
                origin.x: 100; origin.y: Rig.GROUND
            }

            RigPart {
                id: body
                m: root.f.bodyM

                RigLine {
                    z: 0
                    path: root.f.feet.path; color: root.rig.feet; lineWidth: root.f.feet.width
                    alpha: root.f.feet.opacity
                }
                RigPart {
                    z: 1
                    m: root.f.tail.m
                    RigFill { path: root.f.tail.path; fill: root.rig.tail; fillEnd: root.rig.tailLo; from: root.f.tail.top; to: 0 }
                    RigLine { visible: !root.small; path: root.f.tail.bars; color: root.rig.tailBar; lineWidth: 1.7; alpha: 0.5 }
                    RigLine { visible: !root.small; path: root.f.tail.shine; color: "white"; lineWidth: 1; alpha: 0.25 }
                }
                FoldedWing { z: 4; part: root.f.foldL; shape: root.wing }
                OpenWing { z: root.f.openL.z; part: root.f.openL; shape: root.openL }
                FoldedWing { z: 4; part: root.f.foldR; shape: root.wingR }
                OpenWing { z: root.f.openR.z; part: root.f.openR; shape: root.openR }

                WrenBody { z: 3; body: root.f.body; small: root.small; resolution: root.resolution }

                // The scarf's loose end, swinging from the knot, and the knot over it
                RigPart {
                    z: 5
                    m: root.f.scarfEnd.m
                    RigFill {
                        path: root.f.scarfEnd.path
                        fill: root.rig.scarfHi; fillEnd: root.rig.scarfLo; from: 0; to: root.f.scarfEnd.bottom
                    }
                    RigLine { path: "M-6 0L6 0"; color: root.rig.shade; lineWidth: 2; alpha: 0.18; cap: "flat" }
                    RigLine { visible: !root.small; path: root.f.scarfEnd.ribs; color: root.rig.scarfRib; lineWidth: 1; alpha: 0.5 }
                    RigLine { visible: !root.small; path: root.f.scarfEnd.fringe; color: root.rig.scarfLo; lineWidth: 1.5 }
                }
                RigPart {
                    z: 6
                    m: root.f.knot.m
                    RigFill {
                        path: "M-6.5 0A6.5 5.5 0 1 0 6.5 0A6.5 5.5 0 1 0 -6.5 0Z"
                        fill: root.rig.scarfHi; fillEnd: root.rig.scarfLo; from: -5.5; to: 5.5
                    }
                    RigLine { path: "M-4 -0.8Q0 1.6 4 -0.8"; color: root.rig.scarfLo; lineWidth: 1.2; alpha: 0.7 }
                }

                // Crest: rooted in his crown, turning with his head.
                RigPart {
                    z: 2
                    m: root.f.crest.m
                    RigFill { path: root.f.crest.path; fill: root.rig.crestLo; fillEnd: root.rig.crestHi; from: -40; to: -4 }
                    RigLine { path: root.f.crest.shine; color: "white"; lineWidth: 1; alpha: 0.35 }
                }

                // Face: tilts with his head.
                RigPart {
                    z: 7
                    m: root.f.faceM
                    Repeater {
                        model: root.f.blush.spots
                        RigSoft {
                            required property var modelData
                            cx: modelData.x; cy: modelData.y; rx: modelData.rx; ry: modelData.ry
                            color: root.rig.blush; alpha: 0.7 * root.f.blush.opacity
                        }
                    }
                    RigPart { m: root.f.eyeL.m; WrenEye { e: root.f.eyeL } }
                    RigPart { m: root.f.eyeR.m; WrenEye { e: root.f.eyeR } }
                    Brow { brow: root.f.browL }
                    Brow { brow: root.f.browR }
                    RigPart { m: root.f.beak.m; WrenBeak { b: root.f.beak } }
                }

                // Meeting notes: the notepad held up in front of his belly, and the pencil writing on it.
                RigPart {
                    z: 8
                    visible: root.f.pad.shown && opacity > 0.004
                    m: root.f.pad.m || Rig.IDENTITY
                    opacity: root.f.pad.opacity
                    // a soft drop under the paper
                    RigFill { y: 1.5; path: root.pad.paper; fill: root.rig.shade; alpha: 0.16 }
                    RigFill { y: 0.8; path: root.pad.paper; fill: root.rig.shade; alpha: 0.12 }
                    RigFill { path: root.pad.paper; fill: root.rig.paperHi; fillEnd: root.rig.paperLo; from: -14; to: 16 }
                    RigFill { path: root.pad.cover; fill: root.rig.wingHi; fillEnd: root.rig.wingLo; from: -14; to: -8 }
                    RigLine { path: root.pad.paper; color: root.rig.paperLine; lineWidth: 1; alpha: 0.6 }
                    Item {
                        visible: !root.small
                        RigLine { path: root.pad.lines; color: root.rig.paperLine; lineWidth: 0.8; alpha: 0.7 }
                        RigLine { path: root.pad.words; color: root.rig.writing; lineWidth: 0.9; alpha: 0.75 }
                        RigLine { path: root.pad.rings; color: root.rig.paperHi; lineWidth: 1.1 }
                    }
                }
                RigPart {
                    z: 9
                    visible: root.f.pad.shown && opacity > 0.004
                    m: root.f.pencil ? root.f.pencil.m : Rig.IDENTITY
                    opacity: root.f.pencil ? root.f.pencil.opacity : 0
                    RigFill { path: root.pencil.shaft; fill: root.rig.pencil; fillEnd: root.rig.pencilLo; from: -24; to: -6 }
                    RigLine { visible: !root.small; path: root.pencil.facet; color: root.rig.pencilLo; lineWidth: 0.8; alpha: 0.6 }
                    RigFill { path: root.pencil.wood; fill: root.rig.wood }
                    RigFill { path: root.pencil.lead; fill: root.rig.lead }
                    RigFill { path: root.pencil.ferrule; fill: root.rig.ferrule }
                    RigFill { path: root.pencil.eraser; fill: root.rig.eraser }
                }
            }
        }
    }

    // A slow breath about his feet: out, then held a moment taller, on Qt's clock (the Mac's Core Animation breath).
    SequentialAnimation {
        running: root.breath > 0 && root.visible
        loops: Animation.Infinite
        onRunningChanged: if (!running) { breathScale.xScale = 1; breathScale.yScale = 1 }
        ParallelAnimation {
            NumberAnimation {
                target: breathScale; property: "xScale"; easing.type: Easing.InOutQuad
                from: 1 + root.breath * 0.3; to: 1 - root.breath * 0.3; duration: root.breathPeriod * 420
            }
            NumberAnimation {
                target: breathScale; property: "yScale"; easing.type: Easing.InOutQuad
                from: 1 - root.breath * 0.4; to: 1 + root.breath; duration: root.breathPeriod * 420
            }
        }
        ParallelAnimation {
            NumberAnimation {
                target: breathScale; property: "xScale"; easing.type: Easing.InOutQuad
                from: 1 - root.breath * 0.3; to: 1 + root.breath * 0.3; duration: root.breathPeriod * 580
            }
            NumberAnimation {
                target: breathScale; property: "yScale"; easing.type: Easing.InOutQuad
                from: 1 + root.breath; to: 1 - root.breath * 0.4; duration: root.breathPeriod * 580
            }
        }
    }

    component FoldedWing: RigPart {
        property var part
        property var shape
        m: part.m
        opacity: part.opacity
        RigFill { path: shape.path; fill: root.rig.wingHi; fillEnd: root.rig.wingLo; from: shape.top; to: shape.bottom }
        RigLine { visible: !root.small; path: shape.bars; color: root.rig.wingBar; lineWidth: 1.3; alpha: 0.4 }
    }

    component OpenWing: RigPart {
        property var part
        property var shape
        m: part.m
        opacity: part.opacity
        RigFill { path: shape.path; fill: root.rig.wingHi; fillEnd: root.rig.wingLo; from: shape.top; to: shape.bottom }
        RigLine { visible: !root.small; path: shape.bars; color: root.rig.wingBar; lineWidth: 1.2; alpha: 0.45 }
        RigLine { visible: !root.small; path: shape.edge; color: "white"; lineWidth: 1.2; alpha: 0.3 }
    }

    component Brow: RigPart {
        property var brow
        z: brow.z
        m: brow.m
        RigLine { path: brow.path; color: root.rig.brow; lineWidth: brow.width; alpha: brow.alpha }
    }
}
