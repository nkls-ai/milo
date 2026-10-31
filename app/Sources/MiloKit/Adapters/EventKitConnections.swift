import EventKit
import Foundation

/// Calendar and Reminders through EventKit, for the brain's `app_request`. The first use asks macOS for
/// access (one prompt each); after that every call is instant and never touches the screen.
public final class EventKitConnections: AppConnections {
    private lazy var store = EKEventStore()

    public init() {}

    public func handle(op: String, args: JSONValue, reply: @escaping (AppOutcome) -> Void) {
        let done: (AppOutcome) -> Void = { outcome in DispatchQueue.main.async { reply(outcome) } }
        switch op {
        case "calendar.events", "calendar.add_event", "calendar.event", "calendar.update_event", "calendar.delete_event":
            withAccess(to: .event) { [self] in
                switch op {
                case "calendar.events": done(events(args))
                case "calendar.add_event": done(addEvent(args))
                case "calendar.event": done(event(args))
                case "calendar.update_event": done(updateEvent(args))
                default: done(deleteEvent(args))
                }
            } denied: { done(.failure(Self.denied(.event))) }
        case "reminders.list":
            withAccess(to: .reminder) { [self] in listReminders(args, done) } denied: { done(.failure(Self.denied(.reminder))) }
        case "reminders.add", "reminders.complete", "reminders.delete":
            withAccess(to: .reminder) { [self] in
                switch op {
                case "reminders.add": done(addReminder(args))
                case "reminders.complete": done(completeReminder(args))
                default: done(deleteReminder(args))
                }
            } denied: { done(.failure(Self.denied(.reminder))) }
        default:
            done(.failure("Milo's app doesn't know how to do \(op)."))
        }
    }

    // MARK: Access

    private func withAccess(to type: EKEntityType, _ go: @escaping () -> Void, denied: @escaping () -> Void) {
        switch EKEventStore.authorizationStatus(for: type) {
        case .fullAccess, .authorized:
            go()
        case .notDetermined:
            let answered: (Bool, Error?) -> Void = { granted, _ in
                DispatchQueue.main.async { granted ? go() : denied() }
            }
            if type == .event {
                store.requestFullAccessToEvents(completion: answered)
            } else {
                store.requestFullAccessToReminders(completion: answered)
            }
        default:
            denied()
        }
    }

    static func denied(_ type: EKEntityType) -> String {
        type == .event
            ? "Milo isn't allowed to use your calendar. Turn it on in System Settings › Privacy & Security › Calendars."
            : "Milo isn't allowed to use your reminders. Turn it on in System Settings › Privacy & Security › Reminders."
    }

    // MARK: Calendar

    private func events(_ args: JSONValue) -> AppOutcome {
        guard let start = Self.date(args["start"]), let end = Self.date(args["end"]), end > start else {
            return .failure("start and end must be times like 2026-11-05T15:00, end after start.")
        }
        let query = (args["query"]?.string ?? "").lowercased()
        let predicate = store.predicateForEvents(withStart: start, end: end, calendars: nil)
        let found = store.events(matching: predicate)
            .filter { event in
                query.isEmpty || [event.title, event.location, event.notes]
                    .compactMap { $0?.lowercased() }.contains { $0.contains(query) }
            }
            .sorted { $0.startDate < $1.startDate }
        return .success(.array(found.prefix(200).map(Self.json)))
    }

    private func addEvent(_ args: JSONValue) -> AppOutcome {
        guard let title = Self.text(args["title"]), let start = Self.date(args["start"]) else {
            return .failure("An event needs a title and a start time.")
        }
        let end = Self.date(args["end"]) ?? start.addingTimeInterval(3600)
        guard end > start else { return .failure("The end must be after the start.") }
        let calendar: EKCalendar
        switch self.calendar(named: args["calendar"]?.string, for: .event) {
        case .success(let found): calendar = found
        case .failure(let problem): return .failure(problem.text)
        }
        let event = EKEvent(eventStore: store)
        event.title = title
        event.isAllDay = args["all_day"]?.bool ?? false
        event.startDate = start
        event.endDate = event.isAllDay ? end.addingTimeInterval(-1) : end
        event.location = Self.text(args["location"])
        event.notes = Self.text(args["notes"])
        event.calendar = calendar
        do {
            try store.save(event, span: .thisEvent, commit: true)
        } catch {
            return .failure("The calendar didn't take the event: \(error.localizedDescription)")
        }
        return .success(Self.json(event))
    }

    /// The occurrence `args` names: the event `id` that starts at `at`, so one of a repeating series is never
    /// mistaken for the first. Without `at`, the event the id stands for.
    private func occurrence(_ args: JSONValue) -> EKEvent? {
        guard let id = Self.text(args["id"]) else { return nil }
        if let at = Self.date(args["at"]) {
            let predicate = store.predicateForEvents(withStart: at.addingTimeInterval(-60),
                                                     end: at.addingTimeInterval(86_400), calendars: nil)
            if let found = store.events(matching: predicate).first(where: {
                $0.calendarItemIdentifier == id && abs($0.startDate.timeIntervalSince(at)) < 60
            }) {
                return found
            }
        }
        return store.calendarItem(withIdentifier: id) as? EKEvent
    }

    private func event(_ args: JSONValue) -> AppOutcome {
        guard let event = occurrence(args) else { return .failure("I couldn't find that event any more.") }
        return .success(Self.json(event))
    }

    /// Moves only this occurrence: the rest of a series stays where it was.
    private func updateEvent(_ args: JSONValue) -> AppOutcome {
        guard let event = occurrence(args) else { return .failure("I couldn't find that event any more.") }
        guard event.calendar?.allowsContentModifications ?? false else {
            return .failure("That calendar can't be changed from here.")
        }
        guard let start = Self.date(args["start"]), let end = Self.date(args["end"]), end > start else {
            return .failure("start and end must be times like 2026-11-05T15:00, end after start.")
        }
        event.startDate = start
        event.endDate = end
        do {
            try store.save(event, span: .thisEvent, commit: true)
        } catch {
            return .failure("The calendar didn't take the change: \(error.localizedDescription)")
        }
        return .success(Self.json(event))
    }

    /// Deletes only this occurrence, and answers with the event as it was, so the brain can make it again.
    private func deleteEvent(_ args: JSONValue) -> AppOutcome {
        guard let event = occurrence(args) else { return .failure("I couldn't find that event any more.") }
        guard event.calendar?.allowsContentModifications ?? false else {
            return .failure("That calendar can't be changed from here.")
        }
        let was = Self.json(event)
        do {
            try store.remove(event, span: .thisEvent, commit: true)
        } catch {
            return .failure("The calendar didn't delete it: \(error.localizedDescription)")
        }
        return .success(was)
    }

    struct Problem: Error { let text: String }

    /// The named calendar or list, or the usual one when no name is given. A name that matches none is a
    /// failure naming the ones there are, so "the shopping list" never lands quietly in the usual list.
    private func calendar(named name: String?, for type: EKEntityType) -> Result<EKCalendar, Problem> {
        let writable = store.calendars(for: type).filter(\.allowsContentModifications)
        if let name = name?.trimmingCharacters(in: .whitespaces), !name.isEmpty {
            if let match = writable.first(where: { $0.title.localizedCaseInsensitiveCompare(name) == .orderedSame }) {
                return .success(match)
            }
            return .failure(Problem(text: Self.noSuch(name, type, among: writable.map(\.title))))
        }
        let fallback = type == .event ? store.defaultCalendarForNewEvents : store.defaultCalendarForNewReminders()
        guard let found = fallback ?? writable.first else {
            return .failure(Problem(text: type == .event
                ? "I couldn't find a calendar I may write to." : "I couldn't find a reminders list I may write to."))
        }
        return .success(found)
    }

    static func noSuch(_ name: String, _ type: EKEntityType, among names: [String]) -> String {
        let what = type == .event ? "calendar" : "Reminders list"
        let there = names.isEmpty ? "" : " There are: \(names.joined(separator: ", "))."
        return "There's no \(what) called “\(name)”.\(there)"
    }

    // MARK: Reminders

    private func listReminders(_ args: JSONValue, _ done: @escaping (AppOutcome) -> Void) {
        let query = (args["query"]?.string ?? "").lowercased()
        let includeDone = args["include_done"]?.bool ?? false
        let predicate = includeDone
            ? store.predicateForReminders(in: nil)
            : store.predicateForIncompleteReminders(withDueDateStarting: nil, ending: nil, calendars: nil)
        store.fetchReminders(matching: predicate) { reminders in
            let found = (reminders ?? [])
                .filter { r in query.isEmpty || [r.title, r.notes].compactMap { $0?.lowercased() }.contains { $0.contains(query) } }
                .prefix(200)
                .map(Self.json)
            done(.success(.array(Array(found))))
        }
    }

    private func addReminder(_ args: JSONValue) -> AppOutcome {
        guard let title = Self.text(args["title"]) else { return .failure("A reminder needs a title.") }
        let list: EKCalendar
        switch calendar(named: args["list"]?.string, for: .reminder) {
        case .success(let found): list = found
        case .failure(let problem): return .failure(problem.text)
        }
        let reminder = EKReminder(eventStore: store)
        reminder.title = title
        reminder.notes = Self.text(args["notes"])
        reminder.calendar = list
        if let due = Self.date(args["due"]) {
            reminder.dueDateComponents = Calendar.current.dateComponents(
                [.year, .month, .day, .hour, .minute], from: due)
            reminder.addAlarm(EKAlarm(absoluteDate: due))
        }
        do {
            try store.save(reminder, commit: true)
        } catch {
            return .failure("Reminders didn't take it: \(error.localizedDescription)")
        }
        return .success(Self.json(reminder))
    }

    private func completeReminder(_ args: JSONValue) -> AppOutcome {
        guard let id = Self.text(args["id"]), let reminder = store.calendarItem(withIdentifier: id) as? EKReminder else {
            return .failure("I couldn't find that reminder.")
        }
        reminder.isCompleted = true
        do {
            try store.save(reminder, commit: true)
        } catch {
            return .failure("Reminders didn't take it: \(error.localizedDescription)")
        }
        return .success(Self.json(reminder))
    }

    private func deleteReminder(_ args: JSONValue) -> AppOutcome {
        guard let id = Self.text(args["id"]), let reminder = store.calendarItem(withIdentifier: id) as? EKReminder else {
            return .failure("I couldn't find that reminder.")
        }
        let was = Self.json(reminder)
        do {
            try store.remove(reminder, commit: true)
        } catch {
            return .failure("Reminders didn't delete it: \(error.localizedDescription)")
        }
        return .success(was)
    }

    // MARK: JSON

    static func json(_ event: EKEvent) -> JSONValue {
        .object([
            "id": .string(event.calendarItemIdentifier),
            "title": .string(event.title ?? ""),
            "start": .string(format(event.startDate)),
            "end": .string(format(event.endDate)),
            "all_day": .bool(event.isAllDay),
            "location": .string(event.location ?? ""),
            "notes": .string(event.notes ?? ""),
            "calendar": .string(event.calendar?.title ?? ""),
            "recurring": .bool(event.hasRecurrenceRules),
            // Written by someone else: a subscribed or read-only calendar, or someone else organizes it. The brain
            // marks such titles as other people's text (ADR 0029).
            "shared": .bool(shared(event.calendar) || (event.organizer.map { !$0.isCurrentUser } ?? false)),
            // The others invited, by name (or address), without the user: meeting notes name voices with them.
            "attendees": .array((event.attendees ?? []).filter { !$0.isCurrentUser }
                .map { .string($0.name ?? $0.url.absoluteString.replacingOccurrences(of: "mailto:", with: "")) }),
        ])
    }

    static func json(_ reminder: EKReminder) -> JSONValue {
        let due = reminder.dueDateComponents.flatMap { Calendar.current.date(from: $0) }
        return .object([
            "id": .string(reminder.calendarItemIdentifier),
            "title": .string(reminder.title ?? ""),
            "due": .string(due.map(format) ?? ""),
            "notes": .string(reminder.notes ?? ""),
            "list": .string(reminder.calendar?.title ?? ""),
            "done": .bool(reminder.isCompleted),
            "shared": .bool(shared(reminder.calendar)),
        ])
    }

    /// A calendar or list whose items the user may not have written: subscribed, or one they can't change.
    static func shared(_ calendar: EKCalendar?) -> Bool {
        guard let calendar else { return false }
        return calendar.isSubscribed || calendar.type == .subscription || !calendar.allowsContentModifications
    }

    /// Local time as the brain writes it: "2026-11-05T15:00", seconds optional.
    static func date(_ value: JSONValue?) -> Date? {
        guard let text = value?.string, !text.isEmpty else { return nil }
        return readers.lazy.compactMap { $0.date(from: text) }.first
    }

    static func format(_ date: Date) -> String {
        minutes.string(from: date)
    }

    /// Made once: a DateFormatter is costly to make and safe to share between threads. The zone follows the Mac's.
    private static let minutes = formatter("yyyy-MM-dd'T'HH:mm")
    private static let readers = [formatter("yyyy-MM-dd'T'HH:mm:ss"), minutes, formatter("yyyy-MM-dd")]

    private static func formatter(_ pattern: String) -> DateFormatter {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = .autoupdatingCurrent
        f.dateFormat = pattern
        return f
    }

    private static func text(_ value: JSONValue?) -> String? {
        guard let text = value?.string?.trimmingCharacters(in: .whitespacesAndNewlines), !text.isEmpty else { return nil }
        return text
    }
}
