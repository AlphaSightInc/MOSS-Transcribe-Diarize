import Foundation

public final class FakeCaptureSourceAdapter: CaptureSourceAdapter {
    private var queuedFrames: [CaptureFrame]
    private var observedFrames: [CaptureFrame]
    private var started = false

    public init(frames: [CaptureFrame]) {
        self.queuedFrames = frames
        self.observedFrames = frames
    }

    public func enqueue(frames: [CaptureFrame]) {
        queuedFrames.append(contentsOf: frames)
        observedFrames.append(contentsOf: frames)
    }

    public func start(configuration: CaptureConfiguration) throws {
        started = true
    }

    public func pendingFrames() throws -> [CaptureFrame] {
        guard started else {
            return []
        }
        let frames = queuedFrames
        queuedFrames.removeAll()
        return frames
    }

    public func status() -> [CaptureLaneStatus] {
        CaptureLane.allCases.map { lane in
            let laneFrames = observedFrames.filter { $0.lane == lane }
            let last = laneFrames.last
            return CaptureLaneStatus(
                lane: lane,
                sequence: last?.sequence ?? 0,
                deviceEpoch: last?.deviceEpoch ?? 0,
                state: started ? "capturing" : "stopped"
            )
        }
    }

    public func stop(deadline: Date) throws {
        started = false
    }
}

public final class FakeCaptureTransportAdapter: CaptureTransportAdapter {
    public private(set) var publishedFrames: [CaptureFrame] = []
    public private(set) var sessionIDs: [String] = []

    public init() {}

    public func publish(frame: CaptureFrame, configuration: CaptureConfiguration) throws {
        publishedFrames.append(frame)
        sessionIDs.append(configuration.sessionID)
    }
}

public final class FakeCaptureKeyStoreAdapter: CaptureKeyStoreAdapter {
    private let secret: String?

    public init(secret: String? = "local-control-secret") {
        self.secret = secret
    }

    public func loadControlSecret() throws -> String? {
        secret
    }
}

public final class FakeCaptureClockAdapter: CaptureClockAdapter {
    private var ticks: [UInt64]
    private let fixedNow: Date

    public init(ticks: [UInt64] = [1], now: Date = Date(timeIntervalSince1970: 0)) {
        self.ticks = ticks
        self.fixedNow = now
    }

    public func now() -> Date {
        fixedNow
    }

    public func monotonicNanoseconds() -> UInt64 {
        if ticks.isEmpty {
            return 0
        }
        return ticks.removeFirst()
    }
}

public final class FakeCaptureSchedulerAdapter: CaptureSchedulerAdapter {
    public private(set) var labels: [String] = []
    private var operations: [() -> Void] = []

    public init() {}

    public func schedule(label: String, operation: @escaping () -> Void) -> CaptureCancellation {
        labels.append(label)
        operations.append(operation)
        return FakeCaptureCancellation()
    }

    public func runScheduledOperation(at index: Int = 0) {
        operations[index]()
    }
}

public final class FakeCaptureCancellation: CaptureCancellation {
    public private(set) var cancelled = false

    public init() {}

    public func cancel() {
        cancelled = true
    }
}

public final class FakeCaptureHealthAdapter: CaptureHealthAdapter {
    public private(set) var emissions: [(
        status: CaptureStatus,
        configuration: CaptureConfiguration,
        sentMonotonicNS: UInt64
    )] = []

    public init() {}

    public func emit(
        status: CaptureStatus,
        configuration: CaptureConfiguration,
        sentMonotonicNS: UInt64
    ) throws {
        emissions.append((
            status: status,
            configuration: configuration,
            sentMonotonicNS: sentMonotonicNS
        ))
    }
}

public extension CaptureController {
    static func fakeForLocalDevelopment() -> CaptureController {
        CaptureController(
            source: FakeCaptureSourceAdapter(frames: []),
            transport: FakeCaptureTransportAdapter(),
            keyStore: FakeCaptureKeyStoreAdapter(),
            clock: FakeCaptureClockAdapter(),
            scheduler: FakeCaptureSchedulerAdapter(),
            health: FakeCaptureHealthAdapter()
        )
    }
}
