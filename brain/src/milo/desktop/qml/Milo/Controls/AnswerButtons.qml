import QtQuick
import QtQuick.Layouts
import Milo

// Yes and No, or for a question about working in an app, Allow, Allow always and No (ADR 22). A question with
// choices of its own shows only those: its yes and no first, the rest ("Always for Zoom") smaller under them.
// Emits answered(choice) with "yes", "no", "always" or the choice's id. Only a click gets here: a question about
// money is never answered by a key or a spoken yes.
ColumnLayout {
    id: buttons
    property bool always: false
    property var choices: []
    signal answered(string choice)

    readonly property var main: (choices || []).filter(c => c.id === "yes" || c.id === "no")
    readonly property var more: (choices || []).filter(c => c.id !== "yes" && c.id !== "no")
    readonly property bool own: (choices || []).length > 0

    spacing: 7

    Flow {
        Layout.fillWidth: true
        spacing: buttons.always && !buttons.own ? 6 : 8
        Repeater {
            model: buttons.own ? buttons.main
                 : buttons.always ? [{ id: "yes", label: "Allow" }, { id: "always", label: "Allow always" }, { id: "no", label: "No" }]
                 : [{ id: "yes", label: "Yes" }, { id: "no", label: "No" }]
            MiloButton {
                required property var modelData
                objectName: "answer-" + modelData.id  // tests click an answer by its id
                text: modelData.label
                kind: modelData.id === "yes" ? "primary" : "quiet"
                size: "large"
                shape: "rounded"
                tip: modelData.id === "always" && !buttons.own
                     ? "Milo won't ask about work in this app again. Things that can't be undone, sending, buying and money still ask. Take it back in Settings."
                     : ""
                Accessible.description: modelData.id === "yes" ? (buttons.always ? "Milo goes ahead, and doesn't ask again about this work in this app until the task is done" : "Milo goes ahead")
                                      : modelData.id === "no" ? "Milo leaves it"
                                      : "Milo won't ask about work in this app again. Take it back in Settings."
                onClicked: buttons.answered(modelData.id)
            }
        }
    }
    Flow {
        Layout.fillWidth: true
        visible: buttons.more.length > 0
        spacing: 6
        Repeater {
            model: buttons.more
            MiloButton {
                required property var modelData
                objectName: "answer-" + modelData.id  // tests click an answer by its id
                text: modelData.label
                kind: "quiet"
                size: "small"
                Accessible.description: modelData.id === "always" ? "Milo won't ask again and takes notes every time"
                                      : modelData.id === "never" ? "Milo won't ask again for this app" : ""
                onClicked: buttons.answered(modelData.id)
            }
        }
    }
}
