// The snippet with the words searched for in Milo's colour (SearchRow.highlighted), escaped for StyledText.
function escape(text) {
    return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
}

export function words(text, query, color) {
    const terms = query.toLowerCase().split(/\s+/).filter(w => w.length > 1)
        .map(w => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    if (!terms.length) return escape(text)
    const pattern = new RegExp("(" + terms.join("|") + ")", "gi")
    return text.split(pattern).map((part, i) => i % 2
        ? "<b><font color=\"" + color + "\">" + escape(part) + "</font></b>" : escape(part)).join("")
}
