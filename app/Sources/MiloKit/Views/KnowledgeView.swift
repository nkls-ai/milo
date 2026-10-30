import SwiftUI

/// "What Milo knows": the facts Milo keeps about the user, by topic, each with Edit and Forget.
public struct KnowledgeView: View {
    @ObservedObject var knowledge: KnowledgeModel
    let forget: (_ id: String) -> Void
    let edit: (_ id: String, _ text: String) -> Void

    public init(knowledge: KnowledgeModel, forget: @escaping (_ id: String) -> Void,
                edit: @escaping (_ id: String, _ text: String) -> Void) {
        self.knowledge = knowledge
        self.forget = forget
        self.edit = edit
    }

    public var body: some View {
        Group {
            if !knowledge.loaded {
                KnowledgeNote(title: "Asking Milo…", text: "If this stays, Milo's brain isn't running yet.")
            } else if knowledge.facts.isEmpty {
                KnowledgeNote(title: "Milo doesn't know anything about you yet.",
                              text: "Tell him things like “My sister is Anna” or “I don't drink coffee after 3”, and he'll remember them here.")
            } else {
                ScrollView {
                    VStack(alignment: .leading, spacing: 18) {
                        Text("Milo keeps these on your Mac and brings the ones that fit into your conversations. Change one, or have him forget it.")
                            .font(.system(size: 12))
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                        ForEach(knowledge.groups) { group in
                            VStack(alignment: .leading, spacing: 6) {
                                TopicHeading(title: group.title)
                                ForEach(group.facts) { fact in
                                    FactRow(fact: fact, forget: { forget(fact.id) }, edit: { edit(fact.id, $0) })
                                }
                            }
                        }
                    }
                    .padding(18)
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(WindowColors.paper)
    }
}

private struct KnowledgeNote: View {
    let title: String
    let text: String

    var body: some View {
        VStack(spacing: 10) {
            Text(title)
                .font(.system(size: 15, weight: .medium, design: .rounded))
                .multilineTextAlignment(.center)
            Text(text)
                .font(.system(size: 12))
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 280)
        }
        .padding(24)
    }
}

private struct TopicHeading: View {
    let title: String

    var body: some View {
        HStack(spacing: 10) {
            Text(title)
                .font(.system(size: 11, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
            Rectangle().fill(WindowColors.rule).frame(height: 1)
        }
    }
}

/// One fact. Edit turns it into a field; Forget asks once more.
struct FactRow: View {
    let fact: MemoryFact
    let forget: () -> Void
    let edit: (String) -> Void

    @State private var draft: String?
    @State private var askingToForget = false
    @State private var hovering = false
    @FocusState private var focused: Bool

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            if let text = draft {
                TextField("What Milo should know", text: Binding(get: { text }, set: { draft = $0 }), axis: .vertical)
                    .textFieldStyle(.plain)
                    .font(.system(size: 13))
                    .focused($focused)
                    .onSubmit(save)
                    .onExitCommand { draft = nil }
                    .padding(.horizontal, 8)
                    .padding(.vertical, 5)
                    .background(RoundedRectangle(cornerRadius: 7, style: .continuous).fill(WindowColors.field))
                    .overlay(RoundedRectangle(cornerRadius: 7, style: .continuous)
                        .strokeBorder(WindowColors.accent.opacity(0.55), lineWidth: 1))
                Button("Save", action: save).keyboardShortcut(.defaultAction)
                Button("Cancel") { draft = nil }
            } else {
                VStack(alignment: .leading, spacing: 2) {
                    Text(fact.text)
                        .font(.system(size: 13))
                        .textSelection(.enabled)
                        .fixedSize(horizontal: false, vertical: true)
                    if fact.pinned {
                        Text("Always in mind")
                            .font(.system(size: 10.5, weight: .medium))
                            .foregroundStyle(WindowColors.accent)
                            .help("Milo has this in mind in every conversation.")
                    }
                }
                Spacer(minLength: 8)
                HStack(spacing: 10) {
                    Button("Edit") {
                        draft = fact.text
                        focused = true
                    }
                    Button("Forget") { askingToForget = true }
                }
                .buttonStyle(.borderless)
                .font(.system(size: 11.5))
                .opacity(hovering || askingToForget ? 1 : 0.35)
            }
        }
        .padding(.vertical, 6)
        .padding(.horizontal, 10)
        .background(RoundedRectangle(cornerRadius: 9, style: .continuous).fill(WindowColors.inset))
        .onHover { hovering = $0 }
        .confirmationDialog("Should Milo forget this?", isPresented: $askingToForget) {
            Button("Forget", role: .destructive, action: forget)
            Button("Keep it", role: .cancel) {}
        } message: {
            Text(fact.text)
        }
    }

    private func save() {
        guard let text = draft else { return }
        draft = nil
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if !trimmed.isEmpty && trimmed != fact.text { edit(trimmed) }
    }
}
