// Damped-spring maths for Spring.qml and ColorSpring.qml, the way SwiftUI's .spring(response:dampingFraction:)
// moves: a unit mass on a spring of stiffness k = (2π/response)² with damping ratio ζ = dampingFraction, released
// from rest one unit away from its target. Checked against the closed form in brain/tests/desktop/test_motion.py.

// Qt's SpringAnimation integrates in fixed 16 ms steps: v += spring·(to − x) − damping·v; x += v·STEP.
export const STEP = 0.016

function omega(response) { return 2 * Math.PI / response }

// spring and damping for Qt's SpringAnimation. Mapping k and c straight across (spring = k·STEP) is an Euler
// approximation that drifts 3-6 % off at Milo's springs; instead pick them so the step's eigenvalues equal
// e^(λ·STEP) of the real spring. From rest the steps then follow the true curve half a step (8 ms) early, within
// about 1 % (test_motion.py).
export function qtParams(response, damping) {
    const w = omega(response), z = damping
    const r = Math.exp(-z * w * STEP)
    let c = r
    if (z < 1) c = r * Math.cos(w * Math.sqrt(1 - z * z) * STEP)
    else if (z > 1) c = r * Math.cosh(w * Math.sqrt(z * z - 1) * STEP)
    const d = 1 - r * r
    return { spring: (2 - d - 2 * c) / STEP, damping: d }
}

// Reduced motion: no bounce, an ease-out that is 99 % there after `seconds`. With damping 1 the step forgets its
// velocity, so x closes a fixed share of the gap every step: an exponential ease-out.
export function reducedParams(seconds) {
    const share = 1 - Math.exp(-STEP * Math.log(100) / seconds)
    return { spring: share / STEP, damping: 1 }
}

// Progress 0 → 1 (it overshoots when ζ < 1) after t seconds.
export function value(t, response, damping) {
    const w = omega(response), z = damping
    if (z < 1) {
        const a = z * w, wd = w * Math.sqrt(1 - z * z)
        return 1 - Math.exp(-a * t) * (Math.cos(wd * t) + a / wd * Math.sin(wd * t))
    }
    if (z === 1) return 1 - (1 + w * t) * Math.exp(-w * t)
    const s = Math.sqrt(z * z - 1), r1 = -w * (z - s), r2 = -w * (z + s)
    return 1 + (r2 * Math.exp(r1 * t) - r1 * Math.exp(r2 * t)) / (r1 - r2)
}

// d(progress)/dt.
export function velocity(t, response, damping) {
    const w = omega(response), z = damping
    if (z < 1) {
        const a = z * w, wd = w * Math.sqrt(1 - z * z)
        return Math.exp(-a * t) * w * w / wd * Math.sin(wd * t)
    }
    if (z === 1) return w * w * t * Math.exp(-w * t)
    const s = Math.sqrt(z * z - 1), r1 = -w * (z - s), r2 = -w * (z + s)
    return r1 * r2 * (Math.exp(r1 * t) - Math.exp(r2 * t)) / (r1 - r2)
}

// Seconds until the spring stays within `tolerance` of its target.
export function settleTime(response, damping, tolerance = 0.001) {
    const w = omega(response), z = damping
    if (z < 1) return Math.log(1 / (tolerance * Math.sqrt(1 - z * z))) / (z * w)
    let t = 0
    while (1 - value(t, response, damping) > tolerance) t += 0.001
    return t
}

// The spring as a duration and an Easing.BezierSpline curve, for animations that can't integrate (colours).
// Each segment is the cubic Hermite piece through the true curve with its true slopes, so it follows the spring to
// about a percent. Eight segments at most: Qt 6.8 corrupts its heap freeing an easing curve of 12 or more
// (ColorSpring loaded and closed a few times in one engine crashed with 0xc0000374).
export function curve(response, damping, segments = 8) {
    segments = Math.min(segments, 8)
    const duration = settleTime(response, damping)
    const points = []
    const h = 1 / segments
    for (let i = 0; i < segments; ++i) {
        const s0 = i * h, s1 = (i + 1) * h
        const p0 = value(s0 * duration, response, damping), p1 = value(s1 * duration, response, damping)
        const m0 = velocity(s0 * duration, response, damping) * duration
        const m1 = velocity(s1 * duration, response, damping) * duration
        const last = i === segments - 1
        points.push(s0 + h / 3, p0 + m0 * h / 3, s1 - h / 3, (last ? 1 : p1) - m1 * h / 3, s1, last ? 1 : p1)
    }
    return { duration, points }
}
