// Dates, times and numbers as the Mac's pages write them (DayGroups, TodayView.due, MeetingModel.clock, …). The brain
// sends local times without a zone, "2026-10-30T09:12:03" or "2026-10-30T09:12"; `now` is passed in so previews and
// tests are stable.

const SHORT = 1  // Locale.ShortFormat

// "2026-10-30T09:12" (or a date alone) as a local Date; null for "" or anything else.
export function parse(text) {
    const m = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?/.exec(String(text || ""))
    if (!m) return null
    return new Date(+m[1], +m[2] - 1, +m[3], +(m[4] || 0), +(m[5] || 0), +(m[6] || 0))
}

export function sameDay(a, b) {
    return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate()
}

function addDays(date, days) {
    const d = new Date(date.getFullYear(), date.getMonth(), date.getDate())
    d.setDate(d.getDate() + days)
    return d
}

// "9:12" or "09:12", in the user's locale.
export function time(date) { return Qt.formatTime(date, Qt.locale().timeFormat(SHORT)) }

// "Today", "Yesterday", "This week", then "October" (or "October 2025" in another year).
export function heading(date, now) {
    if (sameDay(date, now)) return "Today"
    if (sameDay(date, addDays(now, -1))) return "Yesterday"
    if (date >= addDays(now, -6) && date < now) return "This week"
    return Qt.formatDate(date, date.getFullYear() === now.getFullYear() ? "MMMM" : "MMMM yyyy")
}

// The short time on a row: "9:12" today, "Yesterday", "Tue" this week, "28 Oct" before.
export function rowTime(date, now) {
    switch (heading(date, now)) {
    case "Today": return time(date)
    case "Yesterday": return "Yesterday"
    case "This week": return Qt.formatDate(date, "ddd")
    default: return Qt.formatDate(date, "d MMM")
    }
}

// A reminder's time: "15:30" today, "Tmrw 09:00" otherwise.
export function due(date, now) { return sameDay(date, now) ? time(date) : "Tmrw " + time(date) }

// "Thursday 30 October".
export function longDay(date) { return Qt.formatDate(date, "dddd d MMMM") }

// "Thu 30 Oct, 14:00".
export function shortDayTime(date) { return Qt.formatDate(date, "ddd d MMM") + ", " + time(date) }

// "Today at 9:12", "Yesterday at 9:12", "Thursday 30 October at 9:12".
export function at(date, now) {
    const day = heading(date, now)
    return (day === "Today" || day === "Yesterday" ? day : longDay(date)) + " at " + time(date)
}

// "12:34" or "1:02:03" into a meeting.
export function clock(seconds) {
    const s = Math.max(0, Math.floor(seconds || 0))
    const h = Math.floor(s / 3600), m = Math.floor(s / 60) % 60, rest = s % 60
    const two = n => (n < 10 ? "0" : "") + n
    return h > 0 ? h + ":" + two(m) + ":" + two(rest) : m + ":" + two(rest)
}

// "32 min", "1 h 05 min", or "under a minute".
export function length(seconds) {
    const minutes = Math.round((seconds || 0) / 60)
    if (minutes < 1) return "under a minute"
    if (minutes < 60) return minutes + " min"
    return Math.floor(minutes / 60) + " h " + (minutes % 60 < 10 ? "0" : "") + (minutes % 60) + " min"
}

// 1,234 as "1,234"; 12,300 as "12.3K"; 3,400,000 as "3.4M".
export function compact(n) {
    n = n || 0
    if (n < 10000) return Number(n).toLocaleString(Qt.locale(), "f", 0)
    const [value, unit] = n >= 1e9 ? [n / 1e9, "B"] : n >= 1e6 ? [n / 1e6, "M"] : [n / 1e3, "K"]
    return (Math.round(value * 10) / 10) + unit
}

// "Anna", "Anna and Ben", "Anna, Ben and Carla".
export function list(names) {
    if (names.length < 2) return names.join("")
    return names.slice(0, -1).join(", ") + " and " + names[names.length - 1]
}
