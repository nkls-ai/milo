import Combine
import Foundation

/// What the Usage page shows: the brain's last `usage` report for the range the user picked.
public final class UsageModel: ObservableObject {
    /// The ranges the page offers, in days.
    public static let spans = [7, 30, 90]

    /// nil until the brain answered.
    @Published public private(set) var report: UsageReport?
    /// The range shown, in days. Changing it asks the brain again.
    @Published public private(set) var span = 30
    /// The brain was asked and hasn't answered for this range yet.
    @Published public private(set) var loading = false

    var send: ((BrainCommand) -> Void)?

    public init(report: UsageReport? = nil) {
        self.report = report
        if let report { span = report.span }
    }

    func apply(_ new: UsageReport) {
        guard new.span == span else { return }  // an answer for a range the user already left
        report = new
        loading = false
    }

    /// Ask the brain for the numbers again, e.g. when the page opens. Reads two local files; no model call.
    public func refresh() {
        guard let send else { return }
        loading = true
        send(.getUsage(span: span))
    }

    public func show(span: Int) {
        guard span != self.span else { return }
        self.span = span
        refresh()
    }
}
