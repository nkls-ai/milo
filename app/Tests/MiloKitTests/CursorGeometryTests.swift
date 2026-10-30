import CoreGraphics
import Testing
@testable import MiloKit

@Suite struct CursorGeometryTests {
    @Test func aGlideStartsAndEndsWhereItShould() {
        let a = CGPoint(x: 100, y: 100), b = CGPoint(x: 700, y: 400)
        #expect(CursorGlide.point(from: a, to: b, at: 0) == a)
        let end = CursorGlide.point(from: a, to: b, at: 1)
        #expect(abs(end.x - b.x) < 0.001 && abs(end.y - b.y) < 0.001)
        #expect(CursorGlide.point(from: a, to: b, at: 2) == end, "clamped")
    }

    @Test func aGlideBowsALittleAndEasesOut() {
        let a = CGPoint(x: 0, y: 0), b = CGPoint(x: 1000, y: 0)
        let mid = CursorGlide.point(from: a, to: b, at: 0.5)
        #expect(mid.x > 500, "most of the way after half the time")
        #expect(mid.y > 0 && mid.y <= 40, "a slight curve, never more than 40 points")
    }

    @Test func shortHopsAreQuickLongOnesStayCalm() {
        #expect(CursorGlide.duration(10) == 0.18)
        #expect(CursorGlide.duration(5000) == 0.6)
        #expect(CursorGlide.duration(600) > CursorGlide.duration(100))
    }

    private let screen = CGRect(x: 0, y: 0, width: 1470, height: 920)

    @Test func pipSitsOnTheTopEdgeNearTheRightCorner() {
        let window = CGRect(x: 200, y: 200, width: 600, height: 400)
        let perch = FlightPlan.perch(onCornerOf: window, within: screen)
        #expect(perch.center == CGPoint(x: 744, y: 640))
        #expect(perch.toward.dy > 0 && perch.toward.dx < 0, "looking down and left into the window")
    }

    @Test func underTheMenuBarHeSitsOnTheRightSide() {
        let window = CGRect(x: 200, y: 200, width: 600, height: 700)
        #expect(FlightPlan.perch(onCornerOf: window, within: screen).center == CGPoint(x: 844, y: 830))
    }

    @Test func aFullScreenWindowGetsHimInsideTheCorner() {
        let perch = FlightPlan.perch(onCornerOf: screen, within: screen)
        #expect(perch.center == CGPoint(x: 1400, y: 850))
        #expect(screen.insetBy(dx: 63, dy: 63).contains(perch.center), "always fully on screen")
    }
}
