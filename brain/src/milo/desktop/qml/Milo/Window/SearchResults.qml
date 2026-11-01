import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls
import "highlight.mjs" as Highlight

// What the search found: "Looking…" while the brain looks, a kind word when nothing matched, else the hits.
Column {
    id: results
    readonly property string query: conversations.search.trim()

    RowLayout {
        visible: conversations.searching
        x: 10
        height: 34
        spacing: 8
        ThinkingDots { dot: 4; color: Theme.accent }
        MiloText { text: "Looking…"; size: Theme.type.caption; tone: 0.55 }
    }
    Column {
        visible: !conversations.searching && conversations.results.length === 0
        x: 10
        topPadding: 10
        spacing: 4
        width: parent.width - 20
        MiloText {
            width: parent.width
            wrapMode: Text.WordWrap
            text: "Nothing about “" + results.query + "”."
            size: 12.5
            weight: "medium"
            rounded: true
            tone: 0.75
        }
        MiloText {
            width: parent.width
            wrapMode: Text.WordWrap
            text: "Try other words: Milo also looks by meaning."
            size: 11.5
            tone: 0.5
        }
    }
    MiloText {
        visible: !conversations.searching && conversations.results.length > 0
        leftPadding: 10
        topPadding: 6
        bottomPadding: 4
        text: conversations.results.length === 1 ? "1 conversation" : conversations.results.length + " conversations"
        size: 10
        weight: "bold"
        rounded: true
        font.capitalization: Font.AllUppercase
        font.letterSpacing: 0.8
        tone: 0.42
    }
    Repeater {
        model: conversations.searching ? [] : conversations.results
        delegate: SidebarButton {
            id: hit
            required property var modelData
            width: results.width
            label: modelData.title
            selected: route.page === "conversation" && route.pageId === modelData.id
            onClicked: conversations.open(modelData.id)
            contentItem: Column {
                leftPadding: 10
                rightPadding: 10
                spacing: 3
                RowLayout {
                    width: hit.width - 20
                    spacing: 5
                    MiloText { Layout.fillWidth: true; text: hit.modelData.title; size: 12.5; weight: "semibold"; rounded: true }
                    MiloText { text: hit.modelData.time; size: 10.5; tabular: true; tone: 0.42 }
                }
                MiloText {
                    visible: hit.modelData.snippet !== ""
                    width: hit.width - 20
                    text: Highlight.words(hit.modelData.snippet, results.query, Theme.primary)
                    textFormat: Text.StyledText
                    wrapMode: Text.WordWrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                    size: 11.5
                    tone: 0.6
                }
            }
        }
    }
}
