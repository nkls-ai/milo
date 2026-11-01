import QtQuick

// One piece of the rig placed by an affine from rig.mjs ([a, b, c, d, tx, ty], CoreGraphics order). Its children
// draw in the part's own coordinates, so moving him only changes this transform, as the Mac's layers do.
Item {
    property var m: [1, 0, 0, 1, 0, 0]
    transform: Matrix4x4 {
        matrix: Qt.matrix4x4(m[0], m[2], 0, m[4],
                             m[1], m[3], 0, m[5],
                             0, 0, 1, 0,
                             0, 0, 0, 1)
    }
    visible: opacity > 0.004
}
