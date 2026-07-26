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

    public init(lane: CaptureLane, sequence: UInt64, deviceEpoch: UInt64, state: String) {
        self.lane = lane
        self.sequence = sequence
        self.deviceEpoch = deviceEpoch
        self.state = state
    }
}

public struct CaptureStatus: Equatable {
    public var running: Bool
    public var sessionID: String?
    public var lanes: [CaptureLaneStatus]
    public var publishedFrameCount: Int
    public var lastHealthSequence: UInt64?

    public init(
        running: Bool,
        sessionID: String?,
        lanes: [CaptureLaneStatus],
        publishedFrameCount: Int,
        lastHealthSequence: UInt64?
    ) {
        self.running = running
        self.sessionID = sessionID
        self.lanes = lanes
        self.publishedFrameCount = publishedFrameCount
        self.lastHealthSequence = lastHealthSequence
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
    func emit(status: CaptureStatus, sentMonotonicNS: UInt64) throws
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

    private var configuration: CaptureConfiguration?
    private var running = false
    private var publishedFrameCount = 0
    private var healthSequence: UInt64?
    private var healthTask: CaptureCancellation?

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
        guard !running else {
            throw CaptureControllerError.alreadyRunning
        }
        guard try keyStore.loadControlSecret() != nil else {
            throw CaptureControllerError.missingControlSecret
        }

        try source.start(configuration: configuration)
        self.configuration = configuration
        running = true
        try publishPendingFrames(configuration: configuration)
        let status = try emitHealth()
        healthTask = scheduler.schedule(label: "moss.capture.health") { [weak self] in
            guard let self else { return }
            _ = try? self.emitHealth()
        }
        return status
    }

    public func status() -> CaptureStatus {
        CaptureStatus(
            running: running,
            sessionID: configuration?.sessionID,
            lanes: source.status(),
            publishedFrameCount: publishedFrameCount,
            lastHealthSequence: healthSequence
        )
    }

    @discardableResult
    public func stop(deadline: Date) throws -> CaptureStatus {
        guard running else {
            throw CaptureControllerError.notRunning
        }
        try source.stop(deadline: deadline)
        healthTask?.cancel()
        healthTask = nil
        running = false
        let stopped = CaptureStatus(
            running: false,
            sessionID: configuration?.sessionID,
            lanes: source.status(),
            publishedFrameCount: publishedFrameCount,
            lastHealthSequence: healthSequence
        )
        configuration = nil
        return stopped
    }

    private func publishPendingFrames(configuration: CaptureConfiguration) throws {
        for frame in try source.pendingFrames() {
            try transport.publish(frame: frame, configuration: configuration)
            publishedFrameCount += 1
        }
    }

    private func emitHealth() throws -> CaptureStatus {
        healthSequence = (healthSequence ?? 0) + 1
        let current = status()
        try health.emit(status: current, sentMonotonicNS: clock.monotonicNanoseconds())
        return current
    }
}
