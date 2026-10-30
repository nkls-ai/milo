import SwiftUI

/// The whole overlay: speech bubble above the character, pinned bottom-right.
public struct OverlayView: View {
    @ObservedObject var model: MiloModel
    /// The Yes or No of a question in the bubble.
    var answer: (Bool) -> Void

    public init(model: MiloModel, answer: @escaping (Bool) -> Void = { _ in }) {
        self.model = model
        self.answer = answer
    }

    public var body: some View {
        VStack(alignment: .trailing, spacing: 6) {
            Spacer(minLength: 0)
            if let question = model.question {
                QuestionView(question: question, answer: answer)
            }
            BubbleView(model: model)
            LiveTranscriptView(model: model)
            CharacterView(model: model)
                .frame(width: 132, height: 132)
                .overlay(alignment: .topLeading) { LookingBadge(model: model) }
                .padding(.trailing, 8)
        }
        .padding(12)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomTrailing)
        .animation(.spring(response: 0.35, dampingFraction: 0.8), value: model.bubble)
        .animation(.spring(response: 0.35, dampingFraction: 0.8), value: model.state)
        .animation(.spring(response: 0.35, dampingFraction: 0.8), value: model.question)
        .animation(.spring(response: 0.3, dampingFraction: 0.7), value: model.looking)
    }
}
