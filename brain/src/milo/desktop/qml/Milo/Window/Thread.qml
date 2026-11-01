import QtQuick
import QtQuick.Templates as T
import Milo
import Milo.Controls

// The conversation's lines (TranscriptList). New words glide into view in Milo's spring while the reader is at the
// bottom; once they scroll back to read, the thread stays where they are until they come back down.
ListView {
    id: list
    model: entries
    clip: true
    leftMargin: 18
    rightMargin: 18
    topMargin: 14
    bottomMargin: 10
    boundsBehavior: Flickable.StopAtBounds
    pixelAligned: true
    reuseItems: true
    cacheBuffer: 800
    T.ScrollBar.vertical: MiloScrollBar {}

    property bool following: true
    readonly property real end: Math.max(originY - topMargin, originY + contentHeight + bottomMargin - height)

    // Set only around the thread's own moves, so the reader's scrolling never springs.
    property bool gliding: false
    function follow() {
        if (!following || contentY === end) return
        gliding = true
        contentY = end
        gliding = false
    }
    Behavior on contentY { id: glide; enabled: list.gliding; Spring { kind: "snappy" } }

    // Only the reader's own scrolling (a drag, a flick, the wheel) decides whether the thread follows: at the bottom
    // it does, scrolled back it doesn't. The view's own adjustments as rows lay out don't count.
    onMovementStarted: following = false
    onMovementEnded: following = contentY >= end - 4
    // Later, once `end` has caught up with the new height.
    onContentHeightChanged: Qt.callLater(follow)
    onHeightChanged: Qt.callLater(follow)
    Component.onCompleted: positionViewAtEnd()
    Connections {
        target: entries
        function onGrew() { Qt.callLater(list.follow) }
        function onConversationChanged() { list.following = true; list.positionViewAtEnd() }
    }

    delegate: EntryRow {
        width: list.width - list.leftMargin - list.rightMargin
    }

    footer: PendingRow {
        width: list.width - list.leftMargin - list.rightMargin
        text: shell.pending
        listening: shell.state === "listening"
        topPadding: list.count > 0 && shell.pending !== "" ? 14 : 0
    }
}
