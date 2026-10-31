import CoreGraphics
import Testing
@testable import MiloKit

@Suite struct FlightPlanTests {
    let screen = CGRect(x: 0, y: 0, width: 1440, height: 875)

    @Test func perchesRightOfTheTargetAndPointsLeft() {
        let (center, toward) = FlightPlan.perch(pointingAt: CGPoint(x: 600, y: 500), within: screen)
        #expect(center == CGPoint(x: 600 + FlightPlan.reach, y: 486))
        #expect(toward.dx < -0.95 && toward.dy < 0, "left and a little up, in view coordinates")
        #expect(abs(hypot(toward.dx, toward.dy) - 1) < 1e-9)
    }

    @Test func perchesLeftNearTheRightEdge() {
        let (center, toward) = FlightPlan.perch(pointingAt: CGPoint(x: 1400, y: 500), within: screen)
        #expect(center.x == 1400 - FlightPlan.reach)
        #expect(toward.dx > 0.95)
    }

    @Test func staysOnScreenNearTheBottom() {
        let (center, toward) = FlightPlan.perch(pointingAt: CGPoint(x: 600, y: 10), within: screen)
        #expect(center.y == FlightPlan.margin)
        #expect(toward.dy > 0, "the target is below him, so he points down")
    }

    @Test func pathStartsAndEndsAtTheEndsAndArcsUp() {
        let a = CGPoint(x: 1300, y: 80), b = CGPoint(x: 400, y: 300)
        #expect(FlightPlan.point(from: a, to: b, at: 0) == a)
        let end = FlightPlan.point(from: a, to: b, at: 1)
        #expect(abs(end.x - b.x) < 1e-9 && abs(end.y - b.y) < 1e-9)
        let middle = FlightPlan.point(from: a, to: b, at: 0.5)
        #expect(middle.y > (a.y + b.y) / 2, "the arc bows upward")
    }

    @Test func flightsTakeLongerForLongerDistancesWithinLimits() {
        #expect(FlightPlan.duration(10) == 0.55)
        #expect(FlightPlan.duration(800) > FlightPlan.duration(200))
        #expect(FlightPlan.duration(10_000) == 1.5)
    }

    @Test func convertsTopLeftScreenPointsToAppKit() {
        #expect(FlightPlan.appKit(CGPoint(x: 100, y: 75), primaryHeight: 900) == CGPoint(x: 100, y: 825))
    }

    @Test func modelStartsPerchedWithNoTarget() {
        let model = MiloModel(scheduler: ManualScheduler())
        #expect(model.flyTarget == nil && model.flight == .perched)
    }
}
