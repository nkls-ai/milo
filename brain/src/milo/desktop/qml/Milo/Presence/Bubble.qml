import QtQuick
import Milo
import Milo.Controls as Controls

// Milo's speech bubble (BubbleView.swift): his answer with the words in step with his voice, a question waiting for
// Yes or No, or a note with a button that fixes what it is about. It steps aside while the user records, and grows
// out of the corner its tail points from.
Item {
    id: bubble
    property var presence: null
    // The capsule is recording: the bubble steps aside.
    property bool recording: false
    property bool transcribing: false

    // The `confirm` event as sent ({id, question, money, always, choices}); an empty map when none waits.
    readonly property var question: presence && presence.question && presence.question.question ? presence.question : null
    readonly property string text: presence ? presence.bubble : ""
    readonly property string kind: recording ? "" : question ? "question" : transcribing || text === "" ? "" : "message"
    // What it shows, kept while it goes away.
    property string showing: kind

    implicitWidth: surface.width
    implicitHeight: surface.height
    transformOrigin: Item.BottomRight
    opacity: kind !== "" ? 1 : 0
    scale: kind !== "" || Theme.reducedMotion ? 1 : 0.6
    visible: opacity > 0.002
    onKindChanged: if (kind !== "") showing = kind
    onVisibleChanged: if (!visible) showing = kind
    Behavior on opacity { Spring {} }
    Behavior on scale { Spring {} }

    // The words, paced to his voice: the shell keeps the cut (presentation/speech_reveal.py, SpeechReveal on the Mac)
    // as presence.reveal {shown, fresh, alpha}; without it the whole text shows.
    readonly property var cut: presence && presence.reveal && kind === "message" ? presence.reveal
                                                                                : ({ shown: shownText.length, fresh: 0, alpha: 1 })
    // What it says, kept while it goes away.
    property string shownText: text
    onTextChanged: if (text !== "") shownText = text

    function html(s) { return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\n/g, "<br>") }
    function hex(c, a) {
        const v = x => ("0" + Math.round(x * 255).toString(16)).slice(-2)
        return "#" + v(a) + v(c.r) + v(c.g) + v(c.b)
    }
    // The whole piece laid out from the start; words not said yet are only transparent, so lines never reflow.
    readonly property string paced: {
        const c = cut, t = shownText
        const fresh = c.shown + c.fresh
        return html(t.slice(0, c.shown))
            + "<font color='" + hex(Theme.ink, c.alpha) + "'>" + html(t.slice(c.shown, fresh)) + "</font>"
            + "<font color='#00000000'>" + html(t.slice(fresh)) + "</font>"
    }

    Item {
        id: surface
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        width: Math.ceil(content.width + 28)
        height: Math.ceil(content.height + 20 + Theme.surface.bubbleTail)
        Behavior on width { enabled: bubble.opacity > 0.9; Spring {} }
        Behavior on height { enabled: bubble.opacity > 0.9; Spring {} }

        FloatingSurface { anchors.fill: parent; kind: "bubble" }

        Column {
            id: content
            x: 14
            y: 10
            spacing: bubble.showing === "question" ? 8 : 6
            width: Math.min(Theme.surface.textWidth, Math.max(heard.implicitWidth, words.implicitWidth,
                                                               ask.implicitWidth, money.implicitWidth, 120))

            // A message: what the user asked, small, then Milo's words, then the button if there is one.
            Text {
                id: heard
                visible: bubble.showing === "message" && bubble.presence && bubble.presence.heard !== ""
                width: Math.min(implicitWidth, Theme.surface.textWidth)
                text: bubble.presence ? "“" + bubble.presence.heard + "”" : ""
                color: Theme.fade(Theme.ink, 0.55)
                wrapMode: Text.WordWrap; maximumLineCount: 2; elide: Text.ElideRight
                font { family: Theme.fontFamily; pixelSize: 11 }
            }
            Flickable {
                id: scroller
                visible: bubble.showing === "message"
                width: content.width
                // longer answers scroll, kept at their newest words
                height: Math.min(words.height, 200)
                contentHeight: words.height
                clip: words.height > 200
                interactive: words.height > 200
                contentY: Math.max(0, contentHeight - height)
                Text {
                    id: words
                    width: Math.min(implicitWidth, Theme.surface.textWidth)
                    text: bubble.paced
                    textFormat: Text.StyledText
                    wrapMode: Text.WordWrap
                    lineHeight: 1.12
                    color: Theme.ink
                    font { family: Theme.fontFamily; pixelSize: 13 }
                    Accessible.name: bubble.shownText
                }
            }
            Controls.MiloButton {
                visible: bubble.showing === "message" && !!bubbleAction.title
                readonly property var bubbleAction: bubble.presence && bubble.presence.bubbleAction ? bubble.presence.bubbleAction : ({})
                // Undo sits under what Milo says about the task, quieter than a button that fixes something.
                kind: bubbleAction.icon ? "quiet" : "primary"
                size: "large"
                shape: "rounded"
                text: bubbleAction.title || ""
                iconName: bubbleAction.icon || ""
                tip: bubbleAction.hint || ""
                onClicked: bubble.presence.performBubbleAction()
            }

            // A question: what it is about, the question, the money note, the answers.
            Row {
                visible: bubble.showing === "question"
                spacing: 5
                readonly property var q: bubble.question || {}
                Controls.Icon {
                    anchors.verticalCenter: parent.verticalCenter
                    name: parent.q.money ? "creditcard" : (parent.q.choices || []).length ? "questionmark.bubble" : "hand.raised"
                    filled: true; size: 10.5; color: Theme.accent; weight: "bold"
                }
                Text {
                    text: parent.q.money ? "This involves money" : (parent.q.choices || []).length ? "Up to you" : "Okay to go ahead?"
                    color: Theme.accent
                    font { family: Theme.roundedFamily; pixelSize: 10; weight: Font.DemiBold }
                }
            }
            Text {
                id: ask
                visible: bubble.showing === "question"
                width: Math.min(implicitWidth, Theme.surface.textWidth)
                text: bubble.question ? bubble.question.question : ""
                wrapMode: Text.WordWrap; maximumLineCount: 8
                color: Theme.ink
                font { family: Theme.fontFamily; pixelSize: 13; weight: Font.Medium }
            }
            Text {
                id: money
                visible: bubble.showing === "question" && !!(bubble.question && bubble.question.money)
                width: Math.min(implicitWidth, Theme.surface.textWidth)
                text: "Only a click on Yes counts for this, not a spoken yes."
                wrapMode: Text.WordWrap
                color: Theme.fade(Theme.ink, 0.65)
                font { family: Theme.fontFamily; pixelSize: 11 }
            }
            Controls.AnswerButtons {
                visible: bubble.showing === "question"
                width: content.width
                always: !!(bubble.question && bubble.question.always)
                choices: bubble.question && bubble.question.choices ? bubble.question.choices : []
                onAnswered: choice => bubble.presence.answer(choice)
            }
        }
    }
}
