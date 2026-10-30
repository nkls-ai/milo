import SwiftUI

/// Milo in the overlay: the life layer poses whichever skin `[ui] character` picked.
struct CharacterView: View {
    @ObservedObject var model: MiloModel
    /// The level drives his mouth and ears; it changes too often to live on the model.
    @ObservedObject private var live: LiveLevel
    @StateObject private var life: CharacterLifeDriver
    /// A still figure (a helper's small bird): no blinking, no cursor following, no float. It redraws
    /// only when the model changes.
    let still: Bool

    init(model: MiloModel, still: Bool = false) {
        self.model = model
        live = model.live
        self.still = still
        _life = StateObject(wrappedValue: CharacterLifeDriver(onScreen: !still))
    }

    private var asleep: Bool { model.drowsy && model.state == .idle && model.bubble == nil }

    var body: some View {
        CharacterFigure(for: model.character, state: model.state, emotion: model.emotion, asleep: asleep,
                        level: live.level, connected: model.connected, pose: life.pose, flight: model.flight,
                        words: Self.words(in: model.partial), size: 120)
            .frame(width: 132, height: 132)
            .background(LifeAnchor(driver: life))
            .onAppear {
                guard !still else { return }
                life.start()
                life.update(state: model.state, asleep: asleep)
            }
            .onDisappear { life.stop() }
            .onChange(of: model.state) { life.update(state: model.state, asleep: asleep) }
            .onChange(of: asleep) { life.update(state: model.state, asleep: asleep) }
    }

    /// How many words the live transcript holds; each new one may earn a nod.
    static func words(in partial: String?) -> Int {
        partial?.split(whereSeparator: \.isWhitespace).count ?? 0
    }
}
