// The dot by Milo's lines in the colour of his mood (WindowColors.mood on the Mac).
export function color(emotion, theme) {
    switch (emotion) {
    case "happy": return theme.think
    case "excited": return theme.accent
    case "thinking": return theme.speak
    case "concerned": case "confused": return theme.talk
    case "sad": return Qt.rgba(theme.primary.r, theme.primary.g, theme.primary.b, 0.6)
    case "sleepy": return theme.glow
    default: return theme.primary
    }
}
