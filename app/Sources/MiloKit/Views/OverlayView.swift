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
            VoiceCapsule(model: model)
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
            // A fixed answer, so the stack never walks into the figure to align it: every frame of
            // every blink would lay out the whole drawing again.
            .alignmentGuide(HorizontalAlignment.trailing) { $0.width }
        }
        .padding(12)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomTrailing)
        .animation(motion, value: model.bubble)
        .animation(motion, value: model.state)
        // In with Milo's spring, out quickly: a tap or a ⌥-shortcut must not leave a fading light behind.
        .animation(model.voicePhase == nil ? .easeOut(duration: 0.12) : motion, value: model.voicePhase)
        .animation(motion, value: model.question)
        .animation(motion, value: model.looking)
        .animation(motion, value: model.recording)
        .themed(by: model)
    }

    /// Milo's own spring.
    private var motion: Animation {
        model.theme.motion.animation(reduced: reduceMotion)
    }
}
