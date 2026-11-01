import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls
import "wire.mjs" as Wire

// Milo's question with big, plain buttons (QuestionView in BubbleView.swift), as a card in the window. A question about
// money says so at the top, and only a click on Yes answers it (ADR 23): no key here answers anything, past Enter on
// a button the user moved focus to.
//
// Inputs
//   question: a `confirm` event, {id, question, always, money, choices?: [{id, label}]}.
// Output
//   command({"type": "confirm_answer", id, yes, always, choice}), built by wire.mjs's confirmAnswer.
Card {
    id: card
    property var question: ({})
    signal command(var message)

    readonly property bool money: !!question.money
    readonly property bool own: !!question.choices && question.choices.length > 0
    // Under a money question, in the bubble, the window and Today.
    readonly property string moneyNote: "Only a click on Yes counts for this, not a spoken yes."

    padding: 14
    spacing: 8
    objectName: "confirm-" + question.id
    Accessible.role: Accessible.Grouping
    Accessible.name: (money ? "Milo asks about money: " : "Milo asks: ") + (question.question || "")

    RowLayout {
        spacing: 5
        Icon {
            name: card.money ? "creditcard" : card.own ? "questionmark.bubble" : "hand.raised"
            size: 11
            weight: "bold"
            color: Theme.accent
        }
        MiloText {
            text: card.money ? "This involves money" : card.own ? "Up to you" : "Okay to go ahead?"
            size: 10.5
            weight: "semibold"
            rounded: true
            ink: Theme.accent
        }
    }
    TextEdit {
        Layout.fillWidth: true
        text: card.question.question || ""
        readOnly: true
        selectByMouse: true
        wrapMode: TextEdit.Wrap
        font.family: Theme.fontFamily
        font.pixelSize: 13  // 13.5 on the Mac; pixel sizes are whole
        font.weight: Theme.type.weights.medium
        color: Theme.ink
        selectionColor: Tones.fade(Theme.primary, 0.35)
    }
    MiloText {
        Layout.fillWidth: true
        visible: card.money
        text: card.moneyNote
        size: 11
        tone: 0.65
        wrapMode: Text.WordWrap
    }
    AnswerButtons {
        objectName: "answers"
        Layout.fillWidth: true
        Layout.topMargin: 2
        always: !!card.question.always
        choices: card.question.choices || []
        onAnswered: choice => card.command(Wire.confirmAnswer(card.question, choice))
    }
}
