import QtQuick
import Milo
import "pages.mjs" as Pages

// One of PageHost's two slots: loads a page, slides it in, and slides it out again when the next one comes.
// The pages are dumb (wire-shaped data in, wire commands and named actions out): this binds each input a page
// declares from the view models (pages.mjs says which), sends its commands to the brain and carries out its actions.
Item {
    id: slot
    property string page: ""
    property string pageId: ""
    property bool leaving: false
    readonly property real travel: Theme.reducedMotion ? 0 : 28
    opacity: 0
    visible: opacity > 0.01
    enabled: loader.active && opacity > 0.5
    z: leaving ? 0 : 1

    function source(name) {
        if (name === "conversation") return Qt.resolvedUrl("ConversationPage.qml")
        const url = pages.url(name)
        return url !== "" ? url : Qt.resolvedUrl("PagePlaceholder.qml")
    }

    function enter(name, id, forward) {
        motion.enabled = false
        leaving = false
        page = name
        pageId = id
        loader.source = source(name)
        loader.active = true
        x = forward ? travel : -travel
        opacity = 0
        motion.enabled = true
        x = 0
        opacity = 1
    }

    function leave(forward) {
        if (!loader.active) return
        leaving = true
        x = forward ? -travel / 2 : travel / 2
        opacity = 0
    }

    onOpacityChanged: if (leaving && opacity < 0.01) loader.active = false

    Behavior on x { id: motion; Spring {} }
    Behavior on opacity { enabled: motion.enabled; Spring {} }

    Loader {
        id: loader
        anchors.fill: parent
        active: false
        onLoaded: {
            const item = loader.item
            const sources = Pages.inputs(slot.page, slot, { conversations, store, presence, shell, setupBackend })
            for (const name in sources)
                if (name in item) item[name] = Qt.binding(sources[name])
            if (item.command) item.command.connect(shell.send)
            if (item.action) item.action.connect((name, value) => Pages.act(name, value, { route, conversations, shell }, item))
            const opening = Pages.opening(slot.page, slot.pageId, { conversations })
            if (opening) shell.send(opening)
        }
    }
}
