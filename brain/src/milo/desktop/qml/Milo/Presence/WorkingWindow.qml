import QtQuick
import QtQuick.Effects
import Milo
import "voice.mjs" as Voice

// "Milo is working" (WorkingFrame.swift, WorkingOutlineView.swift, CursorOverlay.swift): while he drives the mouse and
// keys, a soft glowing frame around the screen with a tag saying how to take over, the step he is on in a small
// pill at the bottom, and his own pointer gliding to where he acts. Click-through, above everything, never focused.
//
//     WorkingWindow { working: shell.working }
//
// `working` gives { active, step, point } (point in screen coordinates); optionally `gesture` ("click" |
// "typing" | "none") and `clicks` (rises with each click, for the ripple).
Window {
    id: window
    property var working: null
    readonly property var w: working || ({})
    readonly property bool active: !!w.active

    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus
           | Qt.WindowTransparentForInput
    color: "transparent"
    title: "Milo is working"
    x: screen ? screen.virtualX : 0
    y: screen ? screen.virtualY : 0
    width: screen ? screen.width : 1280
    height: screen ? screen.height : 800
    // shown while he works, and a moment longer for the fade
    visible: active || content.opacity > 0.01

    Item {
        id: content
        // the window's size, not the content item's: that one only follows once the window has been shown
        width: window.width
        height: window.height
        opacity: window.active ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 250; easing.type: Easing.OutQuad } }

        WorkingEdge { anchors.fill: parent; radius: 14; lineWidth: 5; blur: 1.5 }

        // what he does with your screen
        Rectangle {
            id: tag
            anchors.horizontalCenter: parent.horizontalCenter
            y: 34
            width: tagText.implicitWidth + 24
            height: tagText.implicitHeight + 10
            radius: height / 2
            color: Theme.fade(Theme.primary, 0.94)
            Text {
                id: tagText
                anchors.centerIn: parent
                text: "Milo is using your mouse. Move it or press esc to take over."
                color: Theme.primaryInk
                font { family: Theme.roundedFamily; pixelSize: 12; weight: Font.DemiBold }
            }
            layer.enabled: GraphicsInfo.api !== GraphicsInfo.Software
            layer.effect: MultiEffect {
                shadowEnabled: true; shadowColor: Qt.rgba(0, 0, 0, 0.22); shadowBlur: 0.4; blurMax: 12
                shadowVerticalOffset: 1
            }
        }

        // the step he is on, a paper pill with a lavender dot that means his hands are at it
        Item {
            id: caption
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 24
            property string text: window.w.step || ""
            width: Math.min(parent.width - 48, row.implicitWidth + 22)
            height: 24
            opacity: text !== "" ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: 180; easing.type: Easing.InOutQuad } }
            Rectangle {
                anchors.fill: parent
                radius: height / 2
                color: Theme.fade(Theme.tint, 0.97)
                border.color: Theme.fade(Theme.primary, 0.35)
                border.width: 1
                layer.enabled: GraphicsInfo.api !== GraphicsInfo.Software
                layer.effect: MultiEffect {
                    shadowEnabled: true; shadowColor: Theme.fade(Theme.primary, 0.25); shadowBlur: 0.4; blurMax: 12
                    shadowVerticalOffset: 2
                }
            }
            Row {
                id: row
                anchors.centerIn: parent
                spacing: 6
                Rectangle { anchors.verticalCenter: parent.verticalCenter; width: 6; height: 6; radius: 3; color: Theme.primary }
                Text {
                    width: Math.min(implicitWidth, caption.parent.width - 90)
                    text: caption.text
                    elide: Text.ElideMiddle
                    color: Theme.ink
                    font { family: Theme.roundedFamily; pixelSize: 11; weight: Font.DemiBold }
                }
            }
            Accessible.name: "Milo: " + text
        }

        // his pointer, gliding to each place he acts
        MiloCursor {
            id: pointer
            gesture: window.w.gesture || "none"
            clicks: window.w.clicks || 0
            opacity: window.active && glide.placed ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: 250; easing.type: Easing.OutQuad } }
        }
    }

    // The glide: a short eased hop along a slight bow, quicker for short ones (CursorGlide.swift).
    QtObject {
        id: glide
        property bool placed: false
        property point start
        property point end
        property real began: 0
        property real duration: 0.3
        function to(target) {
            // the point arrives in screen coordinates; the window covers the screen from (x, y)
            const local = Qt.point(target.x - window.x, target.y - window.y)
            if (!placed) {
                const entry = Voice.glideEntry(local)
                pointer.x = entry.x; pointer.y = entry.y
                placed = true
            }
            start = Qt.point(pointer.x, pointer.y)
            end = local
            const distance = Math.hypot(end.x - start.x, end.y - start.y)
            if (distance < 1 || Theme.reducedMotion) { pointer.x = end.x; pointer.y = end.y; frames.running = false; return }
            duration = Voice.glideDuration(distance)
            began = Date.now() / 1000
            frames.running = true
        }
    }
    FrameAnimation {
        id: frames
        onTriggered: {
            const t = Math.min(1, (Date.now() / 1000 - glide.began) / glide.duration)
            const p = Voice.glidePoint(glide.start, glide.end, t)
            pointer.x = p.x; pointer.y = p.y
            if (t >= 1) running = false
        }
    }
    readonly property var target: w.point
    onTargetChanged: if (target && (target.x !== 0 || target.y !== 0)) glide.to(target)
    onActiveChanged: if (!active) glide.placed = false
}
