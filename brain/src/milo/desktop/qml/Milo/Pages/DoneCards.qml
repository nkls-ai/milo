import QtQuick
import QtQuick.Layouts
import QtQuick.Templates as T
import Milo
import Milo.Controls
import "doneText.mjs" as DoneText
import "format.mjs" as Format
import "wire.mjs" as Wire

// The cards beside Milo for what he just did (DoneCardStack and DoneCards). They lie as a small deck, newest in front;
// with the pointer on them they fan out upwards so each can be clicked. A new one springs out of Milo's side and
// stays `stay` seconds, longer while the pointer is on the deck; one that ran out tucks back into him. At most three
// show; a new one pushes out the oldest. Under reduced motion they fade.
//
// Inputs
//   add(event):  call with each `action_done` event ({kind, title, detail, when, app, undo, lang})
//   undoPoints:  the `undo_points` event's points, for each card's Undo state
//   items:       action_done events shown at once and kept (previews); `still` draws them without motion or timers
//   fanOut:      fanned out as if hovered (previews)
//   now:         the clock (a Date, or "2026-11-01T10:00")
// Output
//   command({"type": "undo_task", id}) from a card's Undo
//   action("openDone", event): open the item where it lives (DonePlace on the Mac); the card goes
// The overlay that holds it lets clicks through outside `childrenRect`.
Item {
    id: deck
    property var undoPoints: []
    property var items: []
    property bool still: false
    property bool fanOut: false
    property var now: new Date()
    signal command(var message)
    signal action(string name, var value)

    readonly property var clock: typeof now === "string" ? Format.parse(now) : now
    readonly property real cardWidth: 172
    readonly property real cardHeight: 56
    // How far each card behind peeks out above the one in front, and the gap between them fanned out.
    readonly property real peek: 7
    readonly property real gap: 6
    readonly property int most: 3
    readonly property int stay: 4000
    readonly property int afterHover: 1500
    // A still deck (previews) ignores the pointer, which the offscreen platform parks over it.
    readonly property bool open: hover.hovered && !still || fanOut
    property int next: 0

    function add(event) {
        cards.append({ key: ++next, payload: JSON.stringify(event), since: Date.now(), leaving: false })
        let shown = 0
        for (let i = cards.count - 1; i >= 0; --i) if (!cards.get(i).leaving && ++shown > most) dismiss(cards.get(i).key)
    }
    function dismiss(key) {
        for (let i = 0; i < cards.count; ++i) if (cards.get(i).key === key) cards.setProperty(i, "leaving", true)
    }
    function remove(key) {
        for (let i = 0; i < cards.count; ++i) if (cards.get(i).key === key) { cards.remove(i); return }
    }
    function point(event) {
        return undoPoints.find(p => p.id === event.undo) || { id: event.undo, title: event.title, state: "ready" }
    }
    Component.onCompleted: items.forEach(event => add(event))

    ListModel { id: cards }

    readonly property int shown: {
        let n = 0
        for (let i = 0; i < cards.count; ++i) if (!cards.get(i).leaving) ++n
        return n
    }
    implicitWidth: cardWidth
    implicitHeight: shown === 0 ? 0 : cardHeight + (shown - 1) * (open ? cardHeight + gap : peek)
    Behavior on implicitHeight { Spring {} }

    HoverHandler { id: hover }

    Repeater {
        model: cards
        Item {
            id: slot
            required property int index
            required property int key
            required property string payload
            required property real since
            required property bool leaving
            readonly property var event: JSON.parse(payload)
            objectName: "card-" + key
            readonly property int depth: {
                let d = 0
                for (let i = index + 1; i < cards.count; ++i) if (!cards.get(i).leaving) ++d
                return d
            }
            readonly property bool face: deck.open || depth === 0
            property bool landed: deck.still || Theme.reducedMotion

            width: deck.cardWidth
            height: deck.cardHeight
            z: index
            transformOrigin: Item.Bottom
            x: leaving && !Theme.reducedMotion ? 90 : landed ? 0 : 110
            y: deck.height - height - depth * (deck.open ? deck.cardHeight + deck.gap : deck.peek)
               + (leaving && !Theme.reducedMotion ? 10 : landed ? 0 : 18)
            scale: (leaving && !Theme.reducedMotion ? 0.35 : landed ? 1 : 0.3) * (deck.open ? 1 : 1 - 0.05 * depth)
            opacity: leaving || !landed ? 0 : 1
            enabled: !leaving && face
            Behavior on x { enabled: !deck.still; Spring {} }
            Behavior on y { enabled: !deck.still; Spring {} }
            Behavior on scale { enabled: !deck.still; Spring {} }
            Behavior on opacity { enabled: !deck.still; Spring {} }

            Component.onCompleted: landed = true
            Timer {
                // Held while the pointer is on the deck, then a little longer once it leaves.
                interval: deck.stay
                running: !deck.still && !slot.leaving
                onTriggered: {
                    if (deck.open) { interval = deck.afterHover; restart() }
                    else deck.dismiss(slot.key)
                }
            }
            Timer { interval: 450; running: slot.leaving; onTriggered: deck.remove(slot.key) }

            T.AbstractButton {
                id: card
                objectName: "done-" + slot.key
                anchors.fill: parent
                hoverEnabled: true
                focusPolicy: Qt.StrongFocus
                scale: pressed ? 0.96 : 1
                Behavior on scale { Spring { kind: "snappy" } }
                Accessible.role: Accessible.Button
                Accessible.name: DoneText.spoken(slot.event, deck.clock)
                Accessible.description: DoneText.opens(slot.event)
                Keys.onReturnPressed: clicked()
                onClicked: { deck.action("openDone", slot.event); deck.dismiss(slot.key) }

                background: Surface {
                    radius: 14
                    fill: Tones.fade(Theme.tint, 0.97)
                    lift: 0.2
                    liftRadius: 12
                    liftY: 5
                    FocusRing { shown: card.visualFocus; radius: 16 }
                }
                contentItem: RowLayout {
                    opacity: slot.face ? 1 : 0
                    spacing: 8
                    DoneGlyph {
                        Layout.leftMargin: 8
                        action: slot.event
                        since: new Date(slot.since)
                        now: deck.clock
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.rightMargin: slot.event.undo ? 8 + 24 + 4 : 10
                        spacing: 1
                        MiloText {
                            Layout.fillWidth: true
                            text: slot.event.title || DoneText.line(slot.event, deck.clock)
                            size: 12.5
                            weight: "semibold"
                            rounded: true
                        }
                        MiloText {
                            Layout.fillWidth: true
                            text: DoneText.line(slot.event, deck.clock)
                            size: 10.5
                            weight: "medium"
                            rounded: true
                            tone: 0.6
                        }
                    }
                }
                Tip { text: DoneText.opens(slot.event); shown: card.hovered }
            }
            DrawnCheck {
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.rightMargin: -5
                anchors.topMargin: -5
                still: deck.still
                opacity: slot.face ? 1 : 0
            }
            // On top of the card's button, so a click on it is its own.
            UndoButton {
                objectName: "undo"
                anchors.right: parent.right
                anchors.rightMargin: 8
                anchors.verticalCenter: parent.verticalCenter
                visible: !!slot.event.undo && slot.face
                round: true
                point: deck.point(slot.event)
                onUndo: pointId => deck.command(Wire.undoTask(pointId))
            }
        }
    }
}
