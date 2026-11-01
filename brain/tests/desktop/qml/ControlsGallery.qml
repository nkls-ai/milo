import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls

// Every control once, light and dark: scripts/preview-pages.py renders it, tests load it without warnings.

MiloScrollView {
    id: page
    signal command(var message)
    Card {
        CardHeading { icon: "mic"; title: "Dictation"; detail: "When your words appear." }
        ChoiceList { choices: [{value: "off", label: "When you let go"}, {value: "preview", label: "Show the words as you speak"}]; selected: "preview" }
        Callout { icon: "arrow.clockwise"; text: "Some changes start working after Milo restarts."; button: "Restart Milo" }
    }
    RowLayout {
        spacing: 8
        MiloButton { text: "Done"; kind: "primary" }
        MiloButton { text: "Close"; kind: "secondary" }
        MiloButton { text: "Copy notes"; kind: "quiet"; iconName: "doc.on.doc" }
        MiloButton { text: "Run now"; kind: "outline"; size: "small" }
        MiloButton { text: "Stop"; kind: "danger"; size: "small" }
        MiloButton { text: "Stop all"; kind: "plain"; size: "small"; tint: Tones.failed }
    }
    RowLayout {
        spacing: 10
        UndoButton { point: ({id: "a", title: "Excel red", state: "ready"}) }
        UndoButton { point: ({id: "a", title: "Excel red", state: "undoing"}) }
        UndoButton { point: ({id: "a", title: "Excel red", state: "undone"}) }
        UndoButton { round: true; point: ({id: "a", title: "Excel red", state: "ready"}) }
        MiloToggle { checked: true; text: "Voice" }
        MiloToggle { checked: false; text: "Voice" }
        Pill { text: "Working on it"; tint: Tones.running }
        Pill { text: "Max"; filled: true }
        Badge { count: 2 }
        IconButton { iconName: "pause.circle"; label: "Pause" }
        PopMenu { items: [{value: "delete", label: "Delete", danger: true}] }
    }
    RowLayout {
        spacing: 10
        StatusSeal { status: "running" }
        StatusSeal { status: "running"; needsYou: true }
        StatusSeal { status: "done" }
        StatusSeal { status: "failed" }
        Bead { status: "running" }
        Bead { status: "done" }
        Bead { status: "failed" }
        CheckBadge { done: false }
        CheckBadge { done: true }
        LiveLight {}
        LiveLight { paused: true }
        ThinkingDots {}
        Spinner {}
        ProgressLine { Layout.preferredWidth: 120; progress: 0.4 }
    }
    MiloSegmented { options: [{value: 7, label: "7 days"}, {value: 30, label: "30 days"}, {value: 90, label: "90 days"}]; current: 30 }
    MiloField { Layout.fillWidth: true; placeholder: "What Milo should know" }
    MiloField { Layout.fillWidth: true; text: "Anna is the user's sister."; multiline: true }
    SectionHeader { text: "3 steps" }
    TitledCard { title: "Reminders"; icon: "bell"; tint: Theme.primary
        MiloText { text: "Leave for the dentist" }
    }
    AnswerButtons { always: true }
    AnswerButtons { choices: [{id: "yes", label: "Take notes"}, {id: "no", label: "Not this time"}, {id: "always", label: "Always for Zoom"}] }
    EmptyState { framed: true; icon: "leaf"; title: "Nothing on your plate."; detail: "Hold Right Alt and talk to Milo, or type below." }
    Rule {}
    Flow { Layout.fillWidth: true; spacing: 6; Repeater { model: ["check","xmark","bell","sparkles","leaf","hand.raised","checkmark.seal","person.2","note.text","pencil","terminal","magnifyingglass","globe","macwindow","wrench","bubble.left","folder","mic","keyboard","speaker.wave.2","bolt","clock","calendar","envelope","music.note","phone","sun.max","square.stack","bird","waveform","flame","lock","laptop","chart.bar","text.cursor","arrow.uturn.backward","ellipsis","exclamationmark.triangle"]; Icon { required property string modelData; name: modelData; size: 16; color: Theme.primary } } }
}
