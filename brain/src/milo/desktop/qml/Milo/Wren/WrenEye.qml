import QtQuick
import Milo

// One eye (WrenRig.swift's drawEye), centred on (0, 0): the dark ball with its sheen and catchlights, the lids
// painted in the body's own gradient so at rest they vanish into him, and their lines. Smiling, it cross-fades into
// a clean arch. `e` is frame(...).eyeL or eyeR from rig.mjs.
Item {
    id: root
    property var e
    readonly property var rig: Theme.rig

    Item {
        x: -15; y: -16; width: 30; height: 32
        opacity: 1 - root.e.smile
        visible: root.e.smile < 0.999
        // fade the eye as one picture, not each piece through the others
        layer.enabled: root.e.smile > 0.001
        layer.smooth: true
        layer.textureSize: Qt.size(width * 4, height * 4)

      Item {
        x: 15; y: 16
        Item {
            visible: root.e.open
            RigRadial {
                path: root.e.ball
                center: root.e.ballCenter; radius: root.e.ballRadius
                inner: root.rig.eyeHi; middle: root.rig.eye; outer: root.rig.eye; middleAt: 1
            }
            RigSoft {
                cx: root.e.sheen.x; cy: root.e.sheen.y; rx: root.e.sheen.rx; ry: root.e.sheen.ry
                color: root.rig.sheen; alpha: 0.35
            }
            RigFill { path: root.e.catchlight; fill: "white" }
            RigFill { path: root.e.second; fill: "white"; alpha: 0.85 }
            RigFill { path: root.e.glint; fill: "white"; alpha: 0.7 }
            // the shadow the upper lid casts on the eye
            RigFill { path: root.e.lidShadow; fill: root.rig.ink; alpha: 0.3 }
        }
        RigRadial { path: root.e.upper; center: root.e.bodyCenter }
        RigRadial { path: root.e.lowerLid; center: root.e.bodyCenter }
        RigLine { path: root.e.lidLine; color: root.rig.lidLine; lineWidth: root.e.lidWidth || 1; alpha: root.e.lidAlpha || 0 }
        RigLine {
            path: root.e.lowerLine; color: root.rig.lidLine
            lineWidth: root.e.lowerWidth || 1; alpha: root.e.lowerAlpha || 0
        }
      }
    }
    RigLine { path: root.e.smile > 0 ? root.e.arch : ""; color: root.rig.eye; lineWidth: 3; alpha: root.e.smile }
}
