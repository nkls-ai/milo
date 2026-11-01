import QtQuick
import Milo
import "spring.mjs" as SpringMath

// A spring for colours, which Qt can't integrate: the same curve as Spring, baked into a Bezier easing.
//
//     Behavior on color { ColorSpring {} }   // Theme.gentle, as the Mac uses for colour changes
//
// Unlike Spring it restarts from rest when retargeted mid-way; colours rarely notice.
ColorAnimation {
    property string kind: "gentle"
    property real response: Theme[kind].response
    property real dampingFraction: Theme[kind].damping

    readonly property var curve: SpringMath.curve(response, dampingFraction)
    duration: 1000 * (Theme.reducedMotion ? Theme.reducedFade : curve.duration)
    easing.type: Theme.reducedMotion ? Easing.OutCubic : Easing.BezierSpline
    easing.bezierCurve: curve.points
}
