import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls

// Milo's waiting question, pinned above the field until it is answered. Only a click answers a question about money.
Rectangle {
    id: bar
    property var question: ({})
    readonly property bool money: question.money === true && !(question.choices && question.choices.length)
    implicitHeight: row.implicitHeight + 24
    color: Tones.fade(Theme.ink, 0.05)
    Accessible.role: Accessible.AlertMessage
    Accessible.name: (money ? "Milo asks about money: " : "Milo asks: ") + (question.question || "")

    Rule { anchors { left: parent.left; right: parent.right; top: parent.top } }

    RowLayout {
        id: row
        anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; leftMargin: 16; rightMargin: 16 }
        spacing: 12

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 3
            MiloText {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: bar.question.question || ""
                size: 13.5
                weight: "medium"
                rounded: true
            }
            RowLayout {
                spacing: 5
                Icon { visible: bar.money; name: "creditcard"; size: 11; color: Theme.accent }
                MiloText {
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                    text: bar.money ? "This involves money. Only a click on Yes goes ahead."
                                    : "Or hold " + shell.talkKey + " and say yes or no."
                    size: 11
                    weight: bar.money ? "medium" : "regular"
                    ink: bar.money ? Theme.accent : Theme.ink
                    tone: bar.money ? 1 : 0.55
                }
            }
        }
        AnswerButtons {
            always: bar.question.always === true
            choices: bar.question.choices || []
            onAnswered: function(choice) { presence.answer(choice) }
        }
    }
}
