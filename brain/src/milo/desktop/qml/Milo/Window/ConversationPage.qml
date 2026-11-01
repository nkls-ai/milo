import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls

// One conversation (ConversationPage.swift): its title, then its lines with each task as a card. The field to go on
// with it, Milo's waiting question and a recipe draft sit under the page, in the window's dock.
Item {
    id: page
    property string conversationId: ""
    readonly property bool hasHeader: conversations.header.id !== undefined
    readonly property bool empty: entries.count === 0

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        ConversationHeader {
            Layout.fillWidth: true
            visible: page.hasHeader
            info: conversations.header
            live: conversations.live
        }

        Loader {
            Layout.fillWidth: true
            Layout.fillHeight: true
            sourceComponent: !page.empty || (conversations.live && presence.state !== "idle") ? thread
                           : conversations.live ? welcome : opening
        }
    }

    Component { id: thread; Thread {} }
    Component { id: welcome; EmptyConversation {} }
    Component {
        id: opening
        // While an older conversation's lines are on their way.
        EmptyState { busy: true; title: "Opening…" }
    }
}
