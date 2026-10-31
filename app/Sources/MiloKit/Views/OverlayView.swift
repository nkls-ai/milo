import SwiftUI

/// The whole overlay: speech bubble above the character, pinned bottom-right.
public struct OverlayView: View {
    @ObservedObject var model: MiloModel
    @ObservedObject private var presence: Presence
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    public init(model: MiloModel) {
        self.model = model
        presence = model.presence
    }

    public var body: some View {
        VStack(alignment: .trailing, spacing: 6) {
            Spacer(minLength: 0)
            // Whatever is still around him goes with him, and is back at once when he comes back for it.
            Group {
                // A question to the user shows in the bubble, with Yes and No.
                BubbleView(model: model)
                VoiceCapsule(model: model)
                // The meeting capsule has a row of its own above Milo, and the Stop button sits at his side, so a
                // meeting and a working Milo show both, one above the other, never on top of each other.
                MeetingCapsule(meeting: model.meeting)
            }
            .opacity(gone ? 0 : 1)
            HStack(alignment: .bottom, spacing: 0) {
                VStack(alignment: .trailing, spacing: 8) {
                    // What he just did, out of his side. The panel lets clicks on a card through to it, also where
                    // the card reaches into his square (`DoneCards.area`).
                    DoneCardStack(model: model)
                    // Left of the square DraggableHostingView keeps for Milo, so a click on a bird is the bird's.
                    HelperFlock(model: model)
                        .padding(.trailing, 20)
                }
                .opacity(gone ? 0 : 1)
                Comings(presence: model.presence) { pose in
                    CharacterView(model: model, heading: pose.heading)
                        .frame(width: 132, height: 132)
                        .overlay(alignment: .topLeading) { LookingBadge(model: model) }
                        .overlay(alignment: .leading) { StopByMilo(model: model).offset(StopByMilo.offset) }
                        .offset(pose.offset)
                        .opacity(pose.opacity)
                }
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
        .animation(motion, value: model.canStop)
        .animation(.easeOut(duration: Presence.fadeTime), value: gone)
        .themed(by: model)
    }

    private var gone: Bool {
        switch presence.phase {
        case .leaving, .away: true
        case .here, .arriving: false
        }
    }

    /// Milo's own spring.
    private var motion: Animation {
        model.theme.motion.animation(reduced: reduceMotion)
    }
}

/// Milo on his way off the screen or back, a frame at a time on the presence's clock; still while he stays put.
struct Comings<Content: View>: View {
    @ObservedObject var presence: Presence
    @ViewBuilder let content: (Presence.Pose) -> Content

    var body: some View {
        TimelineView(.animation(paused: !presence.phase.moving)) { _ in
            content(presence.pose(at: presence.now()))
        }
    }
}
