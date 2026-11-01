// What each page of qml/Milo/Pages gets, does and asks for when it opens: the one place the window and the pages
// meet. Inputs are functions, bound so a page follows the view models; each is what the page's own header lists.

function nullIfEmpty(value) {
    return value && Object.keys(value).length ? value : null
}

function meetingOf(info) {
    const source = (info && info.source) || ""
    return source.startsWith("meeting:") ? source.slice(8) : ""
}

export function inputs(page, slot, vm) {
    const { conversations, store, presence, shell, setupBackend } = vm
    const shown = () => slot.pageId || conversations.current
    switch (page) {
    case "today": return {
        helpers: () => store.helpers, reminders: () => conversations.reminders,
        conversations: () => conversations.list, current: () => conversations.current,
        question: () => nullIfEmpty(presence.question), drafts: () => store.drafts, routines: () => store.routines,
        undoPoints: () => store.undoPoints, meeting: () => store.meeting, talkKey: () => shell.talkKey }
    case "usage": return { usage: () => nullIfEmpty(store.usage), connected: () => shell.connected }
    case "task": return {
        entry: () => { conversations.revision; return conversations.task(slot.pageId).entry || ({ id: slot.pageId }) },
        conversation: () => { conversations.revision; return nullIfEmpty(conversations.task(slot.pageId).conversation) },
        helper: () => store.helpers.find(h => h.id === slot.pageId) || null,
        undoPoint: () => store.undoPoints.find(p => p.id === slot.pageId) || null }
    case "meeting": return {
        meetingId: () => meetingOf(conversations.info(shown())), conversation: () => shown(),
        status: () => store.meeting, lines: () => store.meetingLines, notes: () => nullIfEmpty(store.meetingNotes),
        entries: () => { conversations.revision; return conversations.entriesOf(shown()) } }
    case "knowledge": return { facts: () => store.facts }
    case "routines": return { routines: () => store.routines, drafts: () => store.drafts, talkKey: () => shell.talkKey }
    case "settings": return {
        settings: () => store.settings, restart: () => store.settingsRestart, error: () => store.settingsError,
        connected: () => shell.connected }
    case "setup": return { setupBackend: () => setupBackend, dictateKey: () => shell.dictateKey }
    default: return {}
    }
}

// What the window asks the brain for as a page opens.
export function opening(page, id, vm) {
    switch (page) {
    case "usage": return { type: "get_usage", span: 30 }
    case "knowledge": return { type: "get_facts" }
    case "settings": return { type: "get_settings" }
    case "meeting": {
        const meeting = meetingOf(vm.conversations.info(id || vm.conversations.current))
        return meeting ? { type: "open_meeting", id: meeting } : null
    }
    default: return null
    }
}

// The named actions pages emit besides wire commands.
export function act(name, value, vm, item) {
    const { route, conversations, shell } = vm
    switch (name) {
    case "openTask": return conversations.openTask(value && value.id !== undefined ? value.id : value)
    case "openConversation": return conversations.open(value)
    case "live": return route.go("live")
    case "changeDraft": shell.changeDraft(value && value.name !== undefined ? value.name : value); return route.go("live")
    case "reveal": return shell.reveal(value)
    case "copyConsent": shell.copy(value); if (item && "copied" in item) item.copied = true; return undefined
    case "copyNotes": shell.copy(value); if (item && "copiedNotes" in item) item.copiedNotes = true; return undefined
    case "restart": return shell.restartBrain()
    case "showWords": return shell.reveal("memory/dictionary.md")
    case "openSetup": return shell.openSetup()
    case "saved": return undefined  // SetupBackend.saved restarts the brain, in Python
    case "done": return route.go("live")
    default: return undefined
    }
}
