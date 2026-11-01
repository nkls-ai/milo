import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls

// Under Today and the conversations: a recipe draft and Milo's waiting question (in the conversation going on),
// then the field. Outside the sliding pages, so it stays put while they move.
ColumnLayout {
    id: dock
    readonly property bool talking: route.page === "today" || route.page === "live" || route.page === "conversation"
    readonly property bool live: route.page === "live" || (route.page === "conversation" && conversations.live)
    readonly property var drafts: store.drafts || []
    // The window's bottom corners it reaches (left, right), rounded like the paper.
    property size corners: Qt.size(0, 0)
    visible: talking
    spacing: 0

    DraftBar {
        Layout.fillWidth: true
        visible: dock.live && dock.drafts.length > 0
        draft: dock.drafts.length ? dock.drafts[dock.drafts.length - 1] : ({})
    }
    QuestionBar {
        Layout.fillWidth: true
        visible: dock.live && presence.question.id !== undefined
        question: presence.question
    }
    Composer {
        Layout.fillWidth: true
        bottomLeftRadius: dock.corners.width
        bottomRightRadius: dock.corners.height
        conversation: route.page === "conversation" && !conversations.live ? route.pageId : ""
        placeholder: route.page === "conversation" && !conversations.live ? "Continue this conversation" : "Type to Milo"
        onSent: if (route.page === "today") route.go("live")
    }
}
