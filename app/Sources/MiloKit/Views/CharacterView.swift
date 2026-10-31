import SwiftUI

/// Milo in the overlay: the wren, posed by the life layer and the app's state.
struct CharacterView: View {
    @ObservedObject var model: MiloModel
    /// Meeting notes: he holds his notepad while he takes them and while he writes them up.
    @ObservedObject var meeting: MeetingModel
    @StateObject private var life = CharacterLifeDriver()
    /// The way he flies while he leaves the screen or comes back (`Presence.Pose`); nil: as the model says.
    let heading: CGVector?

    init(model: MiloModel, heading: CGVector? = nil) {
        self.model = model
        meeting = model.meeting
        self.heading = heading
    }

    /// A real flight wins: he may come back because he has somewhere to fly.
    private var flight: Flight {
        guard let heading, !model.flight.airborne else { return model.flight }
        return .flying(heading: heading)
    }

    private var noting: Bool { model.recording || meeting.status.phase == .writing }

    private var asleep: Bool { model.drowsy && model.state == .idle && model.bubble == nil && !noting }

    /// The brain's state, except that he perks up the moment a held key opens his ears, a beat before the
    /// brain says so.
    private var state: MiloState {
        guard model.state == .idle, case let .open(mode) = model.ear else { return model.state }
        return mode == .talk ? .listening : .dictating
    }

    var body: some View {
        CharacterFigure(for: model.character, state: state, emotion: model.emotion, asleep: asleep,
                        connected: model.connected, pose: life.pose, flight: flight,
                        words: Self.words(in: model.partial), asking: model.question != nil,
                        working: model.workingWindow != nil || model.handsActive, noting: noting, size: 120,
                        live: model.live)
            .frame(width: 132, height: 132)
            .background(LifeAnchor(driver: life))
            .onAppear {
                life.start()
                life.update(state: state, asleep: asleep)
            }
            .onDisappear { life.stop() }
            .onChange(of: state) { life.update(state: state, asleep: asleep) }
            .onChange(of: asleep) { life.update(state: state, asleep: asleep) }
    }

    /// How many words the live transcript holds; each new one may earn a nod.
    static func words(in partial: String?) -> Int {
        partial?.split(whereSeparator: \.isWhitespace).count ?? 0
    }
}
