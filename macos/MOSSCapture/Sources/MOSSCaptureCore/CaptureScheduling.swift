import Foundation

public enum CapturePumpContract {
    /// Domain contract: one publish pass every 0.5 s.
    ///
    /// That is exactly the period of one canonical wire frame, so each lane offers the pump one
    /// frame per tick and the steady-state request rate is two POSTs per second per lane — a rate
    /// the audio grid fixes, not the audio device's callback size. Ticking faster would only add
    /// empty passes; ticking slower would make a lane carry more than one frame per tick and
    /// lengthen the time captured audio waits before it is even attempted.
    public static let interval: TimeInterval = 0.5

    /// A frame attempt and its following heartbeat run serially on the pump queue. Bound each one
    /// to one second so a dead network releases that queue within two seconds and native callback
    /// buffers can move into the outbox's fifteen-second retention window. The F2 five-second
    /// interruption measured the previous 60-second URLRequest default filling the native queue
    /// before the request returned.
    public static let requestTimeoutSeconds: TimeInterval = 1.0
}

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
