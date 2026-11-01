import QtQuick
import Milo

// The beak (WrenRig.swift's drawBeak): the upper bill pointing down at the viewer, the lower bill swinging down to
// open the mouth, with a hint of tongue once it is properly open. `b` is frame(...).beak from rig.mjs.
Item {
    id: root
    property var b
    readonly property var rig: Theme.rig

    RigFill { path: root.b.lower || ""; fill: root.rig.beakHi; fillEnd: root.rig.beakLo; from: 3; to: 11 + root.b.d }
    RigFill { path: root.b.mouth || ""; fill: root.rig.mouth }
    RigFill { path: root.b.tongue || ""; fill: root.rig.tongue }
    RigFill { path: root.b.upper; fill: root.rig.beakHi; fillEnd: root.rig.beakLo; from: -4; to: 13 }
    RigLine { path: root.b.shine; color: "white"; lineWidth: 1; alpha: 0.5 }
}
