import SwiftUI

/// The whole overlay: speech bubble above the character, pinned bottom-right.
public struct OverlayView: View {
    @ObservedObject var model: MiloModel
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    public init(model: MiloModel) {
        self.model = model
    }

    public var body: some View {
        VStack(alignment: .trailing, spacing: 6) {
            Spacer(minLength: 0)
            // A question to the user shows in the bubble, with Yes and No.
            BubbleView(model: model)
            LiveTranscriptView(model: model)
            CharacterView(model: model)
                .frame(width: 132, height: 132)
                .overlay(alignment: .topLeading) { LookingBadge(model: model) }
                .padding(.trailing, 8)
                // A fixed answer, so the stack never walks into the figure to align it: every frame of
                // every blink would lay out the whole drawing again.
                .alignmentGuide(HorizontalAlignment.trailing) { $0.width }
        }
        .padding(12)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomTrailing)
        .animation(motion, value: model.bubble)
        .animation(motion, value: model.state)
        .animation(motion, value: model.question)
        .animation(motion, value: model.looking)
        .themed(by: model)
    }

    /// The skin's own spring: bouncy for the dragon, crisp for Kit, floaty for Glow.
    private var motion: Animation {
        model.theme.motion.animation(reduced: reduceMotion)
    }
}
