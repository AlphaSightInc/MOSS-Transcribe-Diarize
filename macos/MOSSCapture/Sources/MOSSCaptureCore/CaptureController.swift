import Foundation

public enum CaptureLane: String, CaseIterable, Codable, Equatable {
    case system
    case microphone
}

public struct CaptureConfiguration: Equatable {
    public var sessionID: String
    public var serverURL: URL
    public var label: String?

    public init(sessionID: String, serverURL: URL, label: String? = nil) {
        self.sessionID = sessionID
        self.serverURL = serverURL
        self.label = label
    }
}

public struct CaptureFrame: Equatable {
    public var lane: CaptureLane
    public var sequence: UInt64
    public var sampleRate: Int
    public var sampleCount: Int
    public var captureTimestampNS: UInt64
    public var deviceEpoch: UInt64
    public var silent: Bool
    public var discontinuity: Bool
    public var pcm16: Data

    public init(
        lane: CaptureLane,
        sequence: UInt64,
        sampleRate: Int,
        sampleCount: Int,
        captureTimestampNS: UInt64,
        deviceEpoch: UInt64,
        silent: Bool,
        discontinuity: Bool,
        pcm16: Data
    ) {
        self.lane = lane
        self.sequence = sequence
        self.sampleRate = sampleRate
        self.sampleCount = sampleCount
        self.captureTimestampNS = captureTimestampNS
        self.deviceEpoch = deviceEpoch
        self.silent = silent
        self.discontinuity = discontinuity
        self.pcm16 = pcm16
    }
}

public struct CaptureLaneStatus: Equatable {
    public var lane: CaptureLane
    public var sequence: UInt64
    public var deviceEpoch: UInt64
    public var state: String
    public var failureCode: String?

    public init(
        lane: CaptureLane,
        sequence: UInt64,
        deviceEpoch: UInt64,
        state: String,
        failureCode: String? = nil
    ) {
        self.lane = lane
        self.sequence = sequence
        self.deviceEpoch = deviceEpoch
        self.state = state
        self.failureCode = failureCode
    }
}

public struct CaptureStatus: Equatable {
    public var running: Bool
    public var sessionID: String?
    public var lanes: [CaptureLaneStatus]
    public var publishedFrameCount: Int
    public var lastHealthSequence: UInt64?
    public var pumpFailure: CapturePumpFailure?

    public init(
        running: Bool,
        sessionID: String?,
        lanes: [CaptureLaneStatus],
        publishedFrameCount: Int,
        lastHealthSequence: UInt64?,
        pumpFailure: CapturePumpFailure? = nil
    ) {
        self.running = running
        self.sessionID = sessionID
        self.lanes = lanes
        self.publishedFrameCount = publishedFrameCount
        self.lastHealthSequence = lastHealthSequence
        self.pumpFailure = pumpFailure
    }
}

public enum CapturePumpFailure: String, Codable, Equatable {
    case permissionDenied
    case deviceUnavailable
    case transportUnavailable
    case unexpected

    init(error: Error) {
        switch error {
        case NativeCaptureError.permissionDenied(_):
            self = .permissionDenied
        case NativeCaptureError.deviceUnavailable(_):
            self = .deviceUnavailable
        case NativeCaptureError.transportUnavailable(_):
            self = .transportUnavailable
        case is CaptureHTTPTransportError:
            self = .transportUnavailable
        default:
            self = .unexpected
        }
    }
}

public protocol CaptureSourceAdapter {
    func start(configuration: CaptureConfiguration) throws
    func pendingFrames() throws -> [CaptureFrame]
    func status() -> [CaptureLaneStatus]
    func stop(deadline: Date) throws
}

public protocol CaptureTransportAdapter {
    func publish(frame: CaptureFrame, configuration: CaptureConfiguration) throws
}

public protocol CaptureKeyStoreAdapter {
    func loadControlSecret() throws -> String?
}

public protocol CaptureClockAdapter {
    func now() -> Date
    func monotonicNanoseconds() -> UInt64
}

public protocol CaptureSchedulerAdapter {
    func schedule(label: String, operation: @escaping () -> Void) -> CaptureCancellation
}

public protocol CaptureCancellation {
    func cancel()
}

public protocol CaptureHealthAdapter {
    func emit(
        status: CaptureStatus,
        configuration: CaptureConfiguration,
        sentMonotonicNS: UInt64
    ) throws
}

public enum CaptureControllerError: Error, Equatable {
    case alreadyRunning
    case notRunning
    case missingControlSecret
}

public final class CaptureController {
    private let source: CaptureSourceAdapter
    private let transport: CaptureTransportAdapter
    private let keyStore: CaptureKeyStoreAdapter
    private let clock: CaptureClockAdapter
    private let scheduler: CaptureSchedulerAdapter
    private let health: CaptureHealthAdapter
    private let state = CaptureControllerState()

    public init(
        source: CaptureSourceAdapter,
        transport: CaptureTransportAdapter,
        keyStore: CaptureKeyStoreAdapter,
        clock: CaptureClockAdapter,
        scheduler: CaptureSchedulerAdapter,
        health: CaptureHealthAdapter
    ) {
        self.source = source
        self.transport = transport
        self.keyStore = keyStore
        self.clock = clock
        self.scheduler = scheduler
        self.health = health
    }

    @discardableResult
    public func start(configuration: CaptureConfiguration) throws -> CaptureStatus {
        guard try keyStore.loadControlSecret() != nil else {
            throw CaptureControllerError.missingControlSecret
        }

        try state.beginStart(configuration: configuration)
        do {
            try source.start(configuration: configuration)
        } catch {
            state.rollbackStart()
            throw error
        }
        try publishPendingFrames(configuration: configuration)
        let status = try emitHealth(configuration: configuration)
        let task = scheduler.schedule(label: "moss.capture.pump") { [weak self] in
            guard let self else { return }
            guard let configuration = self.state.runningConfiguration() else {
                return
            }
            do {
                try self.publishPendingFrames(configuration: configuration)
                _ = try self.emitHealth(configuration: configuration)
                self.state.clearPumpFailure()
            } catch {
                self.state.recordPumpFailure(CapturePumpFailure(error: error))
            }
        }
        state.storeHealthTask(task)
        return status
    }

    public func status() -> CaptureStatus {
        state.snapshot(lanes: source.status())
    }

    @discardableResult
    public func stop(deadline: Date) throws -> CaptureStatus {
        try state.requireRunning()
        try source.stop(deadline: deadline)
        let lanes = source.status()
        let (task, stopped) = state.finishStop(lanes: lanes)
        task?.cancel()
        return stopped
    }

    private func publishPendingFrames(configuration: CaptureConfiguration) throws {
        for frame in try source.pendingFrames() {
            try transport.publish(frame: frame, configuration: configuration)
            state.recordPublishedFrame()
        }
    }

    private func emitHealth(configuration: CaptureConfiguration) throws -> CaptureStatus {
        state.recordHealthEmissionAttempt()
        let current = state.snapshot(lanes: source.status())
        try health.emit(
            status: current,
            configuration: configuration,
            sentMonotonicNS: clock.monotonicNanoseconds()
        )
        return current
    }
}

private final class CaptureControllerState {
    private let lock = NSLock()
    private var configuration: CaptureConfiguration?
    private var running = false
    private var publishedFrameCount = 0
    private var healthSequence: UInt64?
    private var healthTask: CaptureCancellation?
    private var pumpFailure: CapturePumpFailure?

    func beginStart(configuration: CaptureConfiguration) throws {
        lock.lock()
        defer { lock.unlock() }
        guard !running else {
            throw CaptureControllerError.alreadyRunning
        }
        self.configuration = configuration
        running = true
        pumpFailure = nil
    }

    func rollbackStart() {
        lock.lock()
        configuration = nil
        running = false
        pumpFailure = nil
        lock.unlock()
    }

    func runningConfiguration() -> CaptureConfiguration? {
        lock.lock()
        defer { lock.unlock() }
        guard running else {
            return nil
        }
        return configuration
    }

    func requireRunning() throws {
        lock.lock()
        defer { lock.unlock() }
        guard running else {
            throw CaptureControllerError.notRunning
        }
    }

    func storeHealthTask(_ task: CaptureCancellation) {
        lock.lock()
        healthTask = task
        lock.unlock()
    }

    func recordPublishedFrame() {
        lock.lock()
        publishedFrameCount += 1
        lock.unlock()
    }

    func recordHealthEmissionAttempt() {
        lock.lock()
        healthSequence = (healthSequence ?? 0) + 1
        lock.unlock()
    }

    func clearPumpFailure() {
        lock.lock()
        pumpFailure = nil
        lock.unlock()
    }

    func recordPumpFailure(_ failure: CapturePumpFailure) {
        lock.lock()
        if running {
            pumpFailure = failure
        }
        lock.unlock()
    }

    func snapshot(lanes: [CaptureLaneStatus]) -> CaptureStatus {
        lock.lock()
        defer { lock.unlock() }
        return CaptureStatus(
            running: running,
            sessionID: configuration?.sessionID,
            lanes: lanes,
            publishedFrameCount: publishedFrameCount,
            lastHealthSequence: healthSequence,
            pumpFailure: pumpFailure
        )
    }

    func finishStop(lanes: [CaptureLaneStatus]) -> (CaptureCancellation?, CaptureStatus) {
        lock.lock()
        let stopped = CaptureStatus(
            running: false,
            sessionID: configuration?.sessionID,
            lanes: lanes,
            publishedFrameCount: publishedFrameCount,
            lastHealthSequence: healthSequence,
            pumpFailure: pumpFailure
        )
        let task = healthTask
        healthTask = nil
        configuration = nil
        running = false
        lock.unlock()
        return (task, stopped)
    }
}
