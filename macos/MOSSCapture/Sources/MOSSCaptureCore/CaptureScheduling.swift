import Foundation

public final class RepeatingCaptureSchedulerAdapter: CaptureSchedulerAdapter {
    private let interval: TimeInterval

    public init(interval: TimeInterval) {
        self.interval = interval
    }

    public func schedule(
        label: String,
        operation: @escaping () -> Void
    ) -> CaptureCancellation {
        let timer = DispatchSource.makeTimerSource(queue: DispatchQueue(label: label))
        timer.schedule(deadline: .now() + interval, repeating: interval)
        timer.setEventHandler {
            operation()
        }
        timer.resume()
        return TimerCancellation(timer: timer)
    }
}

private final class TimerCancellation: CaptureCancellation {
    private let timer: DispatchSourceTimer

    init(timer: DispatchSourceTimer) {
        self.timer = timer
    }

    func cancel() {
        timer.cancel()
    }
}
