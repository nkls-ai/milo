import QtQuick
import QtQuick.Shapes
import Milo
import Milo.Controls as Controls
import Milo.Pages as Pages

// The floating Milo near the screen's corner (OverlayView.swift + OverlayPanel.swift): his speech bubble, the voice
// capsule and the meeting capsule above him, the wren in his square at the bottom right, the eye while he looks at
// the screen and a Stop button at his side. A frameless, transparent, always-on-top tool window that never takes
// focus from the app the user dictates into.
//
//     PresenceWindow { presence: shell.presence; working: shell.working }
//
// `presence` is the shell's presence object (see PreviewPresence.qml for every property it may have); `working`
// gives { active, step, point }. A click on Milo calls presence.openWindow(); dragging him moves the window.
// `inputRegion` lists the rectangles that take clicks; everything else passes through to the apps below
// (desktop/overlay.py applies it as the window's mask).
Window {
    id: window
    property var presence: null
    property var working: null

    readonly property var p: presence || ({})
    readonly property bool workingActive: !!(working && working.active)
    readonly property bool canStop: p.canStop !== undefined && p.canStop !== null ? !!p.canStop
        : p.state === "thinking" || p.state === "speaking" || !!p.helpersActive || workingActive
    readonly property bool gone: p.shown === false
    // Drowsy, idle and quiet: he sleeps unless the pointer is on him.
    readonly property bool asleep: !!p.drowsy && p.state === "idle" && !p.bubble && !noting

    // The shell's context (desktop/app.py): `store` for the meeting and the done cards, `shell` to send commands.
    // Read defensively, so previews and tests can load the window without them.
    readonly property var store_: { try { return store } catch (e) { return null } }
    readonly property var shell_: { try { return shell } catch (e) { return null } }
    // The meeting being noted (`meeting_status`), from the store, else the preview's stand-in.
    readonly property var meeting_: store_ && store_.meeting && store_.meeting.phase ? store_.meeting : (p.meeting || null)
    readonly property bool noting: !!(meeting_ && meeting_.phase)
    function send(message) { if (shell_) shell_.send(message) }

    width: 340
    height: 380
    // Placed by the shell (desktop/overlay.py: the corner of the screen you work on). Binding x to `Screen` loops,
    // since x decides the screen, and desktopAvailableWidth spans every monitor.
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus
    color: "transparent"
    visible: true
    title: "Milo"

    readonly property var inputRegion: {
        const rects = []
        // away, nothing of him takes a click
        if (window.away > 0.5) return rects
        const add = item => {
            if (!item || !item.visible || item.opacity < 0.05) return
            const r = item.mapToItem(null, 0, 0, item.width, item.height)
            rects.push(Qt.rect(Math.floor(r.x), Math.floor(r.y), Math.ceil(r.width), Math.ceil(r.height)))
        }
        // read every geometry this depends on, so the region follows them
        void [stack.y, stack.height, bubble.width, bubble.height, capsule.width, capsule.height, meeting.width,
              meeting.height, figure.x, figure.y, stop.visible, badge.visible, bubble.visible, capsule.visible,
              meeting.visible, figure.opacity]
        add(bubble); add(capsule); add(meeting); add(figure); add(stop); add(done)
        return rects
    }

    // What leaving and coming back look like (Presence.swift): a crouch and a flight off the corner, or a fade.
    property real away: gone ? 1 : 0
    Behavior on away {
        NumberAnimation {
            duration: Theme.reducedMotion ? 250 : (window.gone ? 780 : 620)
            easing.type: window.gone ? Easing.InOutQuad : Easing.OutCubic
        }
    }
    // Off the screen to the bottom right, over a little hop.
    readonly property real flightAt: Theme.reducedMotion ? 0 : Math.max(0, (away - (gone ? 0.2 : 0)) / (gone ? 0.8 : 1))
    readonly property point flightOffset: {
        const s = flightAt, u = 1 - s
        return Qt.point(2 * u * s * 30 + s * s * 140, 2 * u * s * -110 + s * s * 180)
    }

    Connections {
        target: window.presence || null
        ignoreUnknownSignals: true
        function onCelebrate() { wren.play("hop"); wren.play("wiggle") }
        function onNudge() { wren.play("perk") }
    }

    Item {
        // the window's size, not the content item's: that one only follows once the window has been shown
        width: window.width
        height: window.height

        // Whatever is still around him goes with him.
        // Stacked from the bottom up by hand, each on the right: a Column lays out a frame late while sizes spring.
        Item {
            id: stack
            anchors.right: parent.right
            anchors.rightMargin: 12 + Theme.surface.trailingInset
            anchors.bottom: figure.top
            anchors.bottomMargin: 6
            width: Math.max(bubble.width, capsule.width, meeting.width)
            height: bubble.height + capsule.height + meeting.height
            opacity: 1 - window.away
            function gap(item) { return item.visible ? 6 : 0 }

            Bubble {
                id: bubble
                height: visible ? implicitHeight : 0
                anchors.right: parent.right
                anchors.bottom: capsule.top
                anchors.bottomMargin: stack.gap(capsule)
                presence: window.presence
                recording: ["armed", "listening", "caught"].indexOf(window.p.phase) >= 0
                transcribing: window.p.phase === "transcribing"
            }
            VoiceCapsule {
                id: capsule
                height: visible ? implicitHeight : 0
                anchors.right: parent.right
                anchors.bottom: meeting.top
                anchors.bottomMargin: stack.gap(meeting)
                phase: window.p.phase || ""
                mode: window.p.mode || ""
                handsFree: !!window.p.handsFree
                partial: window.p.partial || ""
                heard: window.p.heard || ""
                level: window.p.level || 0
            }
            MeetingCapsule {
                id: meeting
                height: visible ? implicitHeight : 0
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                meeting: window.meeting_
                onPause: on => window.send({ type: "meeting_pause", on: on })
                onStop: window.send({ type: "meeting_toggle", on: false })
                onOpen: if (window.presence) window.presence.openWindow()
            }
        }

        // What he just did, out of his side: cards that fan out on hover (Milo.Pages' DoneCards, ADR 30).
        Pages.DoneCards {
            id: done
            anchors.right: figure.left
            anchors.rightMargin: -8
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 12 + 20
            opacity: 1 - window.away
            undoPoints: window.store_ && window.store_.undoPoints ? window.store_.undoPoints : []
            onCommand: message => window.send(message)
            onAction: (name, value) => { if (name === "openDone" && window.presence) window.presence.openWindow() }
            Connections {
                target: window.store_
                ignoreUnknownSignals: true
                function onActionDone(card) { done.add(card) }
            }
        }

        // Milo's square: 132 pt, 20 from the right and 12 from the bottom.
        Item {
            id: figure
            width: Theme.surface.figure
            height: Theme.surface.figure
            x: window.width - 20 - width + window.flightOffset.x
            y: window.height - 12 - height + window.flightOffset.y
            opacity: Theme.reducedMotion ? 1 - window.away : 1 - Math.min(1, Math.max(0, (window.flightAt - 0.55) / 0.33))

            Wren {
                id: wren
                anchors.centerIn: parent
                width: 120
                height: 120
                brainState: window.p.state || "idle"
                emotion: window.p.emotion || "neutral"
                asleep: window.asleep
                level: window.p.level || 0
                connected: window.p.connected !== false
                words: (window.p.partial || "").split(/\s+/).filter(w => w).length
                asking: !!window.p.question
                working: window.workingActive
                noting: window.noting
                flight: window.away > 0.01 && window.away < 0.99 && !Theme.reducedMotion
                        ? { kind: "flying", dx: 0.6, dy: 0.8 } : { kind: "perched" }
                // the middle of the screen is to his left in the corner; to his right once dragged past it
                towardCentre: window.x + figure.x + figure.width / 2 > Screen.virtualX + Screen.width / 2 ? -1 : 1
                // the pointer relative to his middle, y up
                cursor: {
                    const c = window.p.cursor
                    if (!c || c.x === undefined) return null
                    const middle = Qt.point(window.x + figure.x + figure.width / 2, window.y + figure.y + figure.height / 2 + 6)
                    return { x: c.x - middle.x, y: middle.y - c.y }
                }
            }

            // A click on him opens the window; a drag moves the panel.
            MouseArea {
                anchors.fill: parent
                property point pressedAt
                property bool dragged: false
                cursorShape: Qt.PointingHandCursor
                onPressed: mouse => { pressedAt = Qt.point(mouse.x, mouse.y); dragged = false }
                onPositionChanged: mouse => {
                    if (!dragged && Math.hypot(mouse.x - pressedAt.x, mouse.y - pressedAt.y) > 3) {
                        dragged = true
                        window.startSystemMove()
                    }
                }
                onClicked: if (!dragged && window.presence) window.presence.openWindow()
            }

            // The small eye on Milo while he looks at the screen.
            Appear {
                id: badge
                x: 0; y: 0
                shown: !!window.p.looking
                from: 0.4
                Item {
                    width: Theme.surface.badgeSize; height: Theme.surface.badgeSize
                    FloatingSurface { anchors.fill: parent; radius: width / 2 }
                    Controls.SmoothShape {
                        anchors.centerIn: parent
                        width: 13; height: 9
                        ShapePath {
                            strokeColor: "transparent"
                            fillColor: Theme.primary
                            PathSvg { path: "M0 4.5Q6.5 -3.5 13 4.5Q6.5 12.5 0 4.5Z" }
                        }
                        ShapePath {
                            strokeColor: "transparent"
                            fillColor: Theme.tint
                            PathSvg { path: "M4 4.5A2.5 2.5 0 1 0 9 4.5A2.5 2.5 0 1 0 4 4.5Z" }
                        }
                    }
                    Accessible.name: "Milo is looking at the screen"
                }
            }

            // Stop, by his wing: one click and he stops everything, helpers included.
            Appear {
                id: stop
                x: -8
                anchors.verticalCenter: parent.verticalCenter
                anchors.verticalCenterOffset: 4
                shown: window.canStop
                from: 0.4
                Item {
                    width: 28; height: 28
                    FloatingSurface { anchors.fill: parent; radius: width / 2 }
                    Controls.Icon {
                        anchors.centerIn: parent
                        name: "stop"; filled: true; size: 11; weight: "bold"; color: Theme.primary
                    }
                    MouseArea {
                        id: stopArea
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: window.presence.stop()
                    }
                    Controls.Tip { text: "Stop Milo and his helpers"; shown: stopArea.containsMouse }
                    Accessible.role: Accessible.Button
                    Accessible.name: "Stop Milo"
                }
            }
        }

        // A short hint by Milo (a key to try, why he can't hear): over him, when nothing else is.
        Appear {
            anchors.right: parent.right
            anchors.rightMargin: 12 + Theme.surface.trailingInset
            anchors.bottom: figure.top
            anchors.bottomMargin: 6
            shown: !!window.p.hint && !bubble.visible && !capsule.visible && !meeting.visible && !window.gone
            Item {
                width: hint.implicitWidth + 24
                height: hint.implicitHeight + 14
                FloatingSurface { anchors.fill: parent }
                Text {
                    id: hint
                    anchors.centerIn: parent
                    width: Math.min(implicitWidth, Theme.surface.textWidth - 24)
                    text: window.p.hint || ""
                    wrapMode: Text.WordWrap
                    color: Theme.fade(Theme.ink, 0.8)
                    font { family: Theme.fontFamily; pixelSize: 12 }
                }
            }
        }
    }
}
