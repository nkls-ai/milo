import QtQuick
import Milo
import "spring.mjs" as SpringMath

// A SwiftUI .spring(response:dampingFraction:) for any real property:
//
//     Behavior on x { Spring {} }                       // Theme.spring
//     Behavior on scale { Spring { kind: "snappy" } }   // "spring" | "gentle" | "snappy"
//     Behavior on y { Spring { response: 0.16; dampingFraction: 0.75 } }
//
// Real spring physics: retargeted halfway, it keeps its velocity like SwiftUI does instead of restarting.
// Under reduced motion it is a 0.18 s ease-out with no bounce.
SpringAnimation {
    property string kind: "spring"
    property real response: Theme[kind].response
    property real dampingFraction: Theme[kind].damping

    readonly property var params: Theme.reducedMotion ? SpringMath.reducedParams(Theme.reducedFade)
                                                      : SpringMath.qtParams(response, dampingFraction)
    spring: params.spring
    damping: params.damping
    // Qt's default 0.01 stops a 0.92 → 1 scale visibly early.
    epsilon: 0.0005
}
