import QtQuick

// What the keys do in the Milo window (ConversationView.shortcuts), with Ctrl where the Mac has Cmd.
Item {
    id: keys
    signal search()

    Shortcut { sequence: "Ctrl+1"; onActivated: route.go("today") }
    Shortcut { sequence: "Ctrl+2"; onActivated: route.go("usage") }
    Shortcut { sequence: "Ctrl+N"; onActivated: conversations.newConversation() }
    Shortcut { sequence: "Ctrl+F"; onActivated: { route.setSidebarShown(true); keys.search() } }
    Shortcut { sequences: ["Ctrl+[", "Alt+Left"]; onActivated: route.back() }
    Shortcut { sequence: "Ctrl+Alt+Up"; onActivated: conversations.step(-1) }
    Shortcut { sequence: "Ctrl+Alt+Down"; onActivated: conversations.step(1) }
    Shortcut { sequence: "Ctrl+L"; onActivated: shell.focusComposer() }
    Shortcut { sequence: "Ctrl+0"; onActivated: route.toggleSidebar() }
    Shortcut { sequence: "Ctrl+,"; onActivated: route.go("settings") }
    Shortcut {
        sequence: "Esc"
        onActivated: {
            if (conversations.search !== "") conversations.setSearch("")
            else if (route.sidebarShown) route.setSidebarShown(false)
            else if (route.page === "task") route.back()
        }
    }
}
