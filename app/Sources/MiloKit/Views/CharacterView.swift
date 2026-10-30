import SwiftUI

/// Milo in the overlay: the life layer poses whichever skin `[ui] character` picked.
struct CharacterView: View {
    @ObservedObject var model: MiloModel
    @StateObject private var life = CharacterLifeDriver()

    private var asleep: Bool { model.drowsy && model.state == .idle && model.bubble == nil }

    var body: some View {
        CharacterFigure(for: model.character, state: model.state, emotion: model.emotion, asleep: asleep,
                        level: model.level, connected: model.connected, pose: life.pose, flight: model.flight,
                        words: Self.words(in: model.partial), size: 120)
            .frame(width: 132, height: 132)
            .background(LifeAnchor(driver: life))
            .onAppear {
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
