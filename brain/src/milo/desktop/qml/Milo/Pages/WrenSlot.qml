import QtQuick
import Milo

// Where Milo's figure stands on a page (the header of Today, a helper in a row): the Wren itself, `size` square.
// `mood` is the Mac's emotion for the figure ("happy", "excited", "thinking"), `asleep` a queued helper's doze.
// `live` lets him blink and look about; still, he holds the pose the mood settles into.
Item {
    id: slot
    property real size: 58
    property string mood: "happy"
    property bool asleep: false
    property bool live: true

    implicitWidth: size
    implicitHeight: size
    Accessible.ignored: true

    Wren {
        anchors.centerIn: parent
        width: slot.size
        height: slot.size
        still: !slot.live
        // working helpers think; the rest wear the mood on their face
        brainState: slot.mood === "thinking" ? "thinking" : "idle"
        emotion: slot.mood === "thinking" ? "neutral" : slot.mood
        asleep: slot.asleep
    }
}
