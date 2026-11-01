import QtQuick
import Milo

// A small label over a section, in capitals with a little air between them: "3 STEPS", "1 FILE" (SectionLabel).
MiloText {
    font.capitalization: Font.AllUppercase
    font.letterSpacing: 0.8
    size: 10
    weight: "bold"
    rounded: true
    tone: 0.45
    Accessible.role: Accessible.Heading
}
