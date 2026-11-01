import QtQuick
import Milo

// The page beside the sidebar, sliding in from the side it lies on: deeper pages from the right, back from the left
// (ConversationView.pages). Two slots take turns, so the page leaving glides out while the next one comes in.
Item {
    id: host
    clip: true
    property int turn: 0

    // A conversation that holds a meeting's notes shows the meeting's page instead.
    function pageFor(kind, id) {
        if (kind === "live" || kind === "conversation") {
            const info = (conversations.list || []).find(c => c.id === (kind === "live" ? conversations.current : id))
            return info && info.kind === "meeting" && pages.url("meeting") !== "" ? "meeting" : "conversation"
        }
        return kind
    }

    function swap() {
        const incoming = turn % 2 ? second : first
        const outgoing = turn % 2 ? first : second
        turn += 1
        outgoing.leave(route.forward)
        incoming.enter(pageFor(route.page, route.pageId), route.pageId, route.forward)
    }

    Connections {
        target: route
        function onMoved() { host.swap() }
    }
    Component.onCompleted: swap()

    PageSlot { id: first; width: host.width; height: host.height }
    PageSlot { id: second; width: host.width; height: host.height }
}
