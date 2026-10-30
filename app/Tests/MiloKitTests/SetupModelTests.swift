import Testing
@testable import MiloKit

@Suite struct SetupModelTests {
    @Test func onlyAMissingRequiredPermissionNeedsTheWindow() {
        let permissions = FakePermissions()
        permissions.states = [.calendars: .notAsked, .automation: .unknown]
        let setup = SetupModel(permissions: permissions, scheduler: ManualScheduler())
        #expect(!setup.needsAttention, "calendars and Mail are optional")
        permissions.states[.screenRecording] = .denied
        setup.refresh()
        #expect(setup.needsAttention)
        #expect(setup.rows.map(\.permission) == Permission.allCases)
        #expect(setup.rows.allSatisfy { !$0.reason.isEmpty })
    }

    @Test func aSwitchFlippedInSystemSettingsShowsWithinASecondWhileOpen() {
        let permissions = FakePermissions()
        permissions.states = [.microphone: .denied]
        let scheduler = ManualScheduler()
        let setup = SetupModel(permissions: permissions, scheduler: scheduler)
        setup.startWatching()
        permissions.states[.microphone] = .granted
        scheduler.advance(by: 1)
        #expect(setup.rows[0].state == .granted)

        setup.stopWatching()
        #expect(scheduler.pendingCount == 0, "no checking while the window is closed")
        let checks = permissions.checks
        scheduler.advance(by: 10)
        #expect(permissions.checks == checks)
    }

    @Test func theButtonAsksTheFirstTimeAndOpensSystemSettingsAfter() {
        let permissions = FakePermissions()
        permissions.states = [.microphone: .notAsked, .accessibility: .denied]
        let setup = SetupModel(permissions: permissions, scheduler: ManualScheduler())
        setup.fix(.microphone)
        setup.fix(.accessibility)
        #expect(permissions.prompted == [.microphone])
        #expect(permissions.opened == [.accessibility])
    }

    @Test func listeningWhileOpenCompletesTheLastStep() {
        let setup = SetupModel(permissions: FakePermissions(), scheduler: ManualScheduler())
        setup.noticed(.dictating)
        #expect(!setup.tried, "only counts while the window is open")
        setup.startWatching()
        setup.noticed(.thinking)
        #expect(!setup.tried)
        setup.noticed(.dictating)
        #expect(setup.tried)
    }
}
