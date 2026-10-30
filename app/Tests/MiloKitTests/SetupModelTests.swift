import Foundation
import Testing
@testable import MiloKit

/// A setup model on fakes, with its own empty defaults so runs don't share what was seen granted.
private func makeSetup(_ states: [Permission: PermissionState] = [:], scheduler: ManualScheduler = ManualScheduler())
    -> (SetupModel, FakePermissions, UserDefaults) {
    let permissions = FakePermissions()
    permissions.states = states
    let name = "SetupModelTests-\(UUID().uuidString)"
    let defaults = UserDefaults(suiteName: name)!
    defaults.removePersistentDomain(forName: name)
    return (SetupModel(permissions: permissions, scheduler: scheduler, defaults: defaults), permissions, defaults)
}

@Suite struct SetupModelTests {
    @Test func onlyAMissingRequiredPermissionNeedsTheWindow() {
        let (setup, permissions, _) = makeSetup([.calendars: .notAsked, .automation: .unknown])
        #expect(!setup.needsAttention, "calendars and Mail are optional")
        permissions.states[.screenRecording] = .denied
        setup.refresh()
        #expect(setup.needsAttention)
        #expect(setup.rows.map(\.permission) == Permission.allCases)
        #expect(setup.rows.allSatisfy { !$0.reason.isEmpty })
    }

    @Test func aSwitchFlippedInSystemSettingsShowsWithinASecondWhileOpen() {
        let scheduler = ManualScheduler()
        let (setup, permissions, _) = makeSetup([.microphone: .denied], scheduler: scheduler)
        setup.startWatching()
        #expect(setup.watching)
        permissions.states[.microphone] = .granted
        scheduler.advance(by: 1)
        #expect(setup.state(of: .microphone) == .granted)

        setup.stopWatching()
        #expect(!setup.watching && scheduler.pendingCount == 0, "no checking while the window is closed")
        let checks = permissions.checks
        scheduler.advance(by: 10)
        #expect(permissions.checks == checks)
    }

    @Test func aFirstQuestionIsMacOSsOwnDialogAndNothingElse() {
        let (setup, permissions, _) = makeSetup([.microphone: .notAsked, .calendars: .notAsked])
        setup.fix(.microphone)
        setup.fix(.calendars)
        #expect(permissions.calls == ["register microphone", "register calendars"])
        #expect(setup.helper == nil)
    }

    @Test func miloIsInTheListBeforeSystemSettingsOpens() {
        let (setup, permissions, _) = makeSetup([.accessibility: .denied, .microphone: .denied])
        setup.fix(.accessibility)
        setup.fix(.microphone)
        #expect(permissions.calls == ["register accessibility", "open accessibility",
                                      "register microphone", "open microphone"])
        #expect(setup.helper == .accessibility, "the last draggable page opened shows the tile to drag in")
    }

    @Test func theDragHelperShowsForListsThatTakeADropAndLeavesOnceGranted() {
        let (setup, permissions, _) = makeSetup([.screenRecording: .denied, .automation: .denied])
        setup.startWatching()
        setup.fix(.automation)
        #expect(setup.helper == nil, "the Automation page has no list to drop into")
        setup.fix(.screenRecording)
        #expect(setup.helper == .screenRecording)
        permissions.states[.screenRecording] = .granted
        setup.refresh()
        #expect(setup.helper == nil)
    }

    @Test func screenRecordingSaysWhenMiloMustRestart() {
        let (setup, permissions, _) = makeSetup([.screenRecording: .denied])
        #expect(!setup.restartForScreen)
        setup.fix(.screenRecording)
        #expect(setup.restartForScreen)
        var restarts = 0
        setup.restart = { restarts += 1 }
        setup.restart?()
        #expect(restarts == 1)
        permissions.states[.screenRecording] = .granted
        setup.refresh()
        #expect(!setup.restartForScreen)
    }

    @Test func aPermissionStillOffAWhileAfterSystemSettingsOpenedOffersFixIt() {
        let scheduler = ManualScheduler()
        let (setup, permissions, _) = makeSetup([.accessibility: .denied], scheduler: scheduler)
        setup.startWatching()
        setup.fix(.accessibility)
        scheduler.advance(by: SetupModel.patience - 1)
        #expect(setup.stuck.isEmpty, "give the user time to find the switch")
        scheduler.advance(by: 1)
        #expect(setup.stuck == [.accessibility])

        setup.repair(.accessibility)
        #expect(Array(permissions.calls.suffix(3)) == ["reset accessibility", "register accessibility",
                                                       "open accessibility"])
        #expect(setup.stuck.isEmpty)
        permissions.states[.accessibility] = .granted
        scheduler.advance(by: SetupModel.patience)
        #expect(setup.stuck.isEmpty)
    }

    @Test func aPermissionThatWasOnAndNoLongerCountsIsStaleAtOnce() {
        let (setup, permissions, defaults) = makeSetup([:])
        #expect(defaults.stringArray(forKey: SetupModel.grantedKey)?.contains("accessibility") == true)
        permissions.states[.accessibility] = .denied  // e.g. Milo was rebuilt and re-signed
        permissions.states[.microphone] = .denied
        let again = SetupModel(permissions: permissions, scheduler: ManualScheduler(), defaults: defaults)
        #expect(again.stuck == [.accessibility], "only entries a reset can fix")
        _ = setup
    }

    @Test func fixItOnlyResetsMilosOwnResettableEntries() {
        let (setup, permissions, _) = makeSetup([.microphone: .denied])
        setup.repair(.microphone)
        #expect(permissions.resets.isEmpty && permissions.opened.isEmpty)
    }

    @Test func listeningWhileOpenCompletesTheLastStep() {
        let (setup, _, _) = makeSetup()
        setup.noticed(.dictating)
        #expect(!setup.tried, "only counts while the window is open")
        setup.startWatching()
        setup.noticed(.thinking)
        #expect(!setup.tried)
        setup.noticed(.dictating)
        #expect(setup.tried)
    }
}
