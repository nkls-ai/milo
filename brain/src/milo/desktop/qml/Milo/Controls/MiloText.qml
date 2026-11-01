import QtQuick
import Milo

// Text in Milo's fonts. `size` is the Mac's point size, `rounded` the SF Rounded face for headings, `weight` a name
// from design.json ("regular", "medium", "semibold", "bold"), `tone` the ink's opacity (.foregroundStyle(ink.opacity)).
Text {
    property real size: Theme.type.body
    property string weight: "regular"
    property bool rounded: false
    property real tone: 1
    property color ink: Theme.ink
    property bool tabular: false

    color: Qt.rgba(ink.r, ink.g, ink.b, ink.a * tone)
    font.family: rounded ? Theme.roundedFamily : Theme.fontFamily
    font.pixelSize: size
    font.weight: Theme.type.weights[weight] || Theme.type.weights.regular
    font.features: tabular ? { "tnum": 1 } : {}
    textFormat: Text.PlainText
    elide: wrapMode === Text.NoWrap ? Text.ElideRight : Text.ElideNone
    Accessible.role: Accessible.StaticText
    Accessible.name: text
}
