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
            // A question to the user shows in the bubble, with Yes and No.
            BubbleView(model: model)
            LiveTranscriptView(model: model)
            HStack(alignment: .bottom, spacing: 0) {
                // Left of the square DraggableHostingView keeps for Milo, so a click on a bird is the bird's.
                HelperFlock(model: model)
                    .padding(.trailing, 20)
                CharacterView(model: model)
                    .frame(width: 132, height: 132)
                    .overlay(alignment: .topLeading) { LookingBadge(model: model) }
                    .overlay(alignment: .topTrailing) { RecordingBadge(model: model) }
                    .padding(.trailing, 8)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomTrailing)
        .animation(.spring(response: 0.35, dampingFraction: 0.8), value: model.bubble)
        .animation(.spring(response: 0.35, dampingFraction: 0.8), value: model.state)
        .animation(.spring(response: 0.35, dampingFraction: 0.8), value: model.question)
        .animation(.spring(response: 0.3, dampingFraction: 0.7), value: model.looking)
        .animation(.spring(response: 0.3, dampingFraction: 0.7), value: model.recording)
    }
}
