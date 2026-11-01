import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls

// "What Milo knows" (KnowledgeView.swift): the facts Milo keeps about the user, by topic, each with Edit and Forget.
//
// Inputs
//   facts: the `facts` event's list, [{id, text, topic, since, pinned}]; null until it came ("Asking Milo…").
// Output
//   command({"type": "forget_fact", id}) and command({"type": "edit_fact", id, text}).
Item {
    id: page
    property var facts: null
    signal command(var message)

    // profile.md's headings in its order; a topic Milo doesn't know comes last, capitalised.
    readonly property var topics: [["basics", "Basics"], ["people", "People"], ["work", "Work and projects"],
                                   ["preferences", "Preferences"], ["routines", "Routines"], ["learned", "Learned"]]
    readonly property var groups: {
        const list = facts || []
        const known = topics.map(t => t[0])
        const others = [...new Set(list.map(f => f.topic))].filter(t => known.indexOf(t) < 0).sort()
        return topics.concat(others.map(t => [t, t.charAt(0).toUpperCase() + t.slice(1)]))
            .map(([topic, title]) => ({ title: title, facts: list.filter(f => f.topic === topic) }))
            .filter(g => g.facts.length > 0)
    }

    EmptyState {
        anchors.centerIn: parent
        width: Math.min(parent.width, 340)
        visible: !page.facts || page.facts.length === 0
        title: !page.facts ? "Asking Milo…" : "Milo doesn't know anything about you yet."
        detail: !page.facts ? "If this stays, Milo's brain isn't running yet."
                            : "Tell him things like “My sister is Anna” or “I don't drink coffee after 3”, and he'll remember them here."
    }

    MiloScrollView {
        anchors.fill: parent
        visible: !!page.facts && page.facts.length > 0
        leftPadding: 18
        rightPadding: 18
        topPadding: 18
        bottomPadding: 18
        maxContentWidth: 680
        spacing: 18

        MiloText {
            Layout.fillWidth: true
            text: "Milo keeps these on your computer and brings the ones that fit into your conversations. Change one, or have him forget it."
            size: Theme.type.caption
            tone: 0.6
            wrapMode: Text.WordWrap
        }
        Repeater {
            model: page.groups
            ColumnLayout {
                required property var modelData
                Layout.fillWidth: true
                spacing: 6
                RowLayout {
                    spacing: 10
                    MiloText { text: modelData.title; size: 11; weight: "semibold"; rounded: true; tone: 0.6 }
                    Rule { Layout.alignment: Qt.AlignVCenter }
                }
                Repeater {
                    model: modelData.facts
                    FactRow {
                        required property var modelData
                        fact: modelData
                        onForget: page.command({ type: "forget_fact", id: modelData.id })
                        onEdit: text => page.command({ type: "edit_fact", id: modelData.id, text: text })
                    }
                }
            }
        }
    }
}
