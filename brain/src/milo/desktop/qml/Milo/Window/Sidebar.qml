import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls

// The window's left side (ConversationsSidebar.swift): search, Today and the other pages, then the conversations by
// day, each hanging on a thread with a bead. The selected row is a card that glides to it.
Rectangle {
    id: side
    color: Theme.tint
    // The window's corner it sits in, rounded like the paper.
    property real corner: 0
    bottomLeftRadius: corner
    property Item selected: null
    readonly property bool searchingWords: conversations.search.trim() !== ""

    function focusSearch() { search.focusField() }

    // The sidebar's own faint wash over the paper.
    Rectangle { anchors.fill: parent; color: Tones.fade(Theme.ink, 0.035); bottomLeftRadius: side.corner }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        SearchField {
            id: search
            Layout.fillWidth: true
            Layout.margins: Theme.space.m
            Layout.bottomMargin: Theme.space.s
        }

        Flickable {
            id: scroller
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentHeight: list.height + Theme.space.m
            clip: true
            boundsBehavior: Flickable.StopAtBounds

            // The selection: a soft card under the selected row, gliding from row to row.
            Rectangle {
                id: selection
                x: list.x
                width: list.width
                visible: side.selected !== null && side.selected.visible
                // Read again whenever the list lays itself out, so the card stays under its row.
                y: side.selected ? side.selected.mapToItem(list, 0, 0).y + list.y + 0 * list.height : 0
                height: side.selected ? side.selected.height : 0
                radius: Theme.radius.small
                color: Theme.card
                border.width: 1
                border.color: Tones.fade(Theme.primary, 0.18)
                Behavior on y { Spring {} }
                Behavior on height { Spring {} }
            }

            Column {
                id: list
                x: Theme.space.s
                width: scroller.width - 2 * Theme.space.s

                Column {
                    width: parent.width
                    visible: !side.searchingWords
                    PageRow { page: "today"; symbol: "sun.max"; tint: Theme.accent; title: "Today"; keys: "Ctrl+1"; badge: shell.waiting }
                    PageRow { page: "usage"; symbol: "chart.bar"; title: "Usage"; keys: "Ctrl+2" }
                    PageRow { page: "knowledge"; symbol: "note.text"; title: "What Milo knows" }
                    PageRow { page: "routines"; symbol: "arrow.loop"; title: "Routines" }
                    Item { width: 1; height: Theme.space.xs + 2 }

                    MiloText {
                        visible: conversations.rows.length === 0
                        width: parent.width
                        leftPadding: 10
                        rightPadding: 10
                        topPadding: 14
                        wrapMode: Text.WordWrap
                        text: "Your conversations with Milo show up here, one for each thing you talk about."
                        size: 11.5
                        tone: 0.5
                    }

                    Repeater {
                        model: conversations.rows
                        delegate: Column {
                            id: entry
                            required property var modelData
                            width: list.width
                            SectionTitle {
                                visible: entry.modelData.first
                                text: entry.modelData.section
                            }
                            SidebarButton {
                                width: parent.width
                                selected: (route.page === "conversation" && route.pageId === entry.modelData.id)
                                          || (entry.modelData.live && route.page === "live")
                                label: entry.modelData.title
                                onSelectedChanged: if (selected) side.selected = this
                                Component.onCompleted: if (selected) side.selected = this
                                onClicked: conversations.open(entry.modelData.id)
                                contentItem: ConversationRow { row: entry.modelData; selected: parent.selected }
                            }
                        }
                    }

                    MiloButton {
                        visible: conversations.more
                        kind: "plain"
                        size: "small"
                        text: "Show older"
                        leftPadding: 30
                        topPadding: Theme.space.s
                        onClicked: conversations.older()
                    }
                }

                SearchResults {
                    width: parent.width
                    visible: side.searchingWords
                }
            }
        }

        NewConversationButton { Layout.fillWidth: true }
    }

    // Today, Usage and the other pages beside them.
    component PageRow: SidebarButton {
        id: row
        property string page
        property string symbol
        property color tint: Theme.primary
        property string title
        property string keys: ""
        property int badge: 0
        width: list.width
        selected: route.page === page
        onSelectedChanged: if (selected) side.selected = this
        Component.onCompleted: if (selected) side.selected = this
        label: badge > 0 ? title + ", " + badge + " waiting for you" : title
        onClicked: route.go(page)
        contentItem: RowLayout {
            spacing: 9
            Icon { name: row.symbol; size: 12.5; color: row.tint; filled: row.page === "today"; Layout.preferredWidth: 18; Layout.leftMargin: 8 }
            MiloText { text: row.title; size: Theme.type.body; weight: "semibold"; rounded: true; Layout.fillWidth: true }
            Badge { visible: row.badge > 0; count: row.badge }
            KeyHint { visible: row.keys !== ""; keys: row.keys; Layout.rightMargin: 8 }
        }
    }

    component SectionTitle: MiloText {
        leftPadding: 10
        topPadding: 12
        bottomPadding: 4
        size: 10
        weight: "bold"
        rounded: true
        font.capitalization: Font.AllUppercase
        font.letterSpacing: 0.8
        tone: 0.42
    }
}
