import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls
import "wire.mjs" as Wire

// Routines on a page of their own, for a sidebar entry: recipes waiting for a look first, then every routine with
// Run now and its menu. Built from DraftCard and RoutineRow, as the Mac shows them on Today and in the window.
//
// Inputs
//   routines: the `routines` event's routines; drafts: its drafts [{id, name, recipe, schedule}]
//   talkKey:  the talk key's name, for "hold Right Alt and say it"
// Output
//   command: {"type": "routine", id, action} and {"type": "routine_draft_answer", id, save}
//   action:  "changeDraft" with the draft, to put "Change …" into the conversation's field
Item {
    id: page
    property var routines: []
    property var drafts: []
    property string talkKey: "Right Alt"
    signal command(var message)
    signal action(string name, var value)

    EmptyState {
        anchors.centerIn: parent
        width: Math.min(parent.width, 360)
        visible: page.routines.length === 0 && page.drafts.length === 0
        icon: "arrow.loop"
        title: "No routines yet."
        detail: "Ask Milo to do something every week, or to remember how you do a job, and it shows up here."
    }

    MiloScrollView {
        anchors.fill: parent
        visible: page.routines.length > 0 || page.drafts.length > 0
        spacing: 12

        MiloText {
            text: "Routines"
            size: Theme.type.title - 1
            weight: "bold"
            rounded: true
        }
        Repeater {
            model: page.drafts
            DraftCard {
                required property var modelData
                draft: modelData
                talkKey: page.talkKey
                radius: Theme.radius.medium
                clip: true
                onSave: page.command(Wire.draftAnswer(modelData.id, true))
                onDrop: page.command(Wire.draftAnswer(modelData.id, false))
                onChange: page.action("changeDraft", modelData)
            }
        }
        Card {
            visible: page.routines.length > 0
            spacing: 12
            Repeater {
                model: page.routines
                RoutineRow {
                    required property var modelData
                    routine: modelData
                    onAct: action => page.command(Wire.routine(modelData.id, action))
                }
            }
        }
    }
}
