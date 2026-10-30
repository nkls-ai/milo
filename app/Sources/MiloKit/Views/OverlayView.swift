import SwiftUI

/// The whole overlay: speech bubble above the character, pinned bottom-right.
public struct OverlayView: View {
    @ObservedObject var model: MiloModel

    public init(model: MiloModel) {
        self.model = model
    }

    public var body: some View {
        VStack(alignment: .trailing, spacing: 6) {
            Spacer(minLength: 0)
            BubbleView(model: model)
            LiveTranscriptView(model: model)
            CharacterView(model: model)
                .frame(width: 132, height: 132)
                .padding(.trailing, 8)
        }
        .padding(12)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomTrailing)
        .animation(.spring(response: 0.35, dampingFraction: 0.8), value: model.bubble)
        .animation(.spring(response: 0.35, dampingFraction: 0.8), value: model.state)
    }
}
