import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls

// Whether a CLI was found on this computer: "Claude for talking: Installed", with why in the tooltip. Only the
// command is looked for, never the account (providers.detect_cli).
RowLayout {
    id: row
    property string name
    property var status: ({})
    readonly property bool found: !!status && !!status.available

    spacing: 6
    Accessible.role: Accessible.StaticText
    Accessible.name: name + ": " + (found ? "Installed" : "Not found")

    Icon { name: row.found ? "checkmark.circle" : "minus.circle"; size: 13; color: row.found ? Tones.done : Tones.fade(Theme.ink, 0.45) }
    MiloText { text: row.name; size: Theme.type.caption; tone: 0.75 }
    MiloText {
        text: row.found ? "Installed" : "Not found"
        size: Theme.type.caption
        weight: "semibold"
        rounded: true
        ink: row.found ? Tones.done : Theme.ink
        tone: row.found ? 1 : 0.5
    }
    HoverHandler { id: hover }
    Tip { text: row.status ? row.status.detail || "" : ""; shown: hover.hovered }
}
