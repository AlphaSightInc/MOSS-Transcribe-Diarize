import Foundation

public enum CaptureLane: String, CaseIterable, Codable, Equatable {
    case system
    case microphone
}

/// The whole vocabulary of lane states, in one place.
///
/// Every reporting surface — the heartbeat, the control channel, the app's log — has to agree on
/// which word means "this lane is dead", and a surface that spells it itself is a surface that can
/// silently stop recognising it.
public enum CaptureLaneStates {
    public static let capturing = "capturing"
    public static let recovering = "recovering"
    public static let stopped = "stopped"
    public static let failed = "failed"
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

public struct CaptureFrame: Equatable, Sendable {
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
    public var droppedFrames: UInt64
    public var discontinuities: UInt64
    public var failureCode: String?

    public init(
        lane: CaptureLane,
        sequence: UInt64,
        deviceEpoch: UInt64,
        state: String,
        droppedFrames: UInt64 = 0,
        discontinuities: UInt64 = 0,
        failureCode: String? = nil
    ) {
        self.lane = lane
        self.sequence = sequence
        self.deviceEpoch = deviceEpoch
        self.state = state
        self.droppedFrames = droppedFrames
        self.discontinuities = discontinuities
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
    public var outbox: CaptureOutboxSnapshot

    public init(
        running: Bool,
        sessionID: String?,
        lanes: [CaptureLaneStatus],
        publishedFrameCount: Int,
        lastHealthSequence: UInt64?,
        pumpFailure: CapturePumpFailure? = nil,
        outbox: CaptureOutboxSnapshot = CaptureOutboxSnapshot()
    ) {
        self.running = running
        self.sessionID = sessionID
        self.lanes = lanes
        self.publishedFrameCount = publishedFrameCount
        self.lastHealthSequence = lastHealthSequence
        self.pumpFailure = pumpFailure
        self.outbox = outbox
    }

    /// Every lane the contract defines, in a stable order, carrying the source's status when it has
    /// one. Reporting surfaces project from this rather than from `lanes` directly, so none of them
    /// can disagree about which lanes exist: a lane the source never reported is named as stopped,
    /// never omitted.
    public func reportedLanes() -> [CaptureLaneStatus] {
        CaptureLane.allCases.map { lane in
            lanes.first { $0.lane == lane }
                ?? CaptureLaneStatus(
                    lane: lane,
                    sequence: 0,
                    deviceEpoch: 0,
                    state: CaptureLaneStates.stopped
                )
        }
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
        case is URLError:
            // A pinned `URLSession` reports an interrupted network as a raw `URLError`, and losing
            // the network is the definition of the transport being unavailable.
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

/// Sees the audio the server actually took, so a measurement can anchor itself to the same timeline
/// the server mixer builds.
///
/// It is handed facts, not frames: an observer structurally cannot reach the PCM, so nothing on this
/// path can grow into a second consumer of the audio.
public protocol CaptureAcknowledgedFrameObserving: AnyObject {
    /// A new server session mixes a fresh timeline and numbers its samples from zero.
    func observeSessionStart()
    func observeAcknowledgedFrame(
        lane: CaptureLane,
        captureTimestampNS: UInt64,
        sampleRate: Int,
        sampleCount: Int,
        discontinuity: Bool
    )
}

public protocol CaptureHealthAdapter {
    func emit(
        status: CaptureStatus,
        configuration: CaptureConfiguration,
        sentMonotonicNS: UInt64
    ) throws
}

/// Records every lane failure the app sees, on its way to the server.
///
/// It sits on the health path rather than the control channel because the heartbeat is the only
/// report the app produces without an operator asking for one: a meeting that dies while nobody is
/// polling still leaves the typed code in the unified log. G3 made a control failure *nobody could
/// name* readable afterwards; a typed lane failure that ends the meeting must not be quieter than
/// that.
///
/// One line per lane per failure. A lane's failure is sticky for the life of a capture generation,
/// so logging it every 0.5 s tick would bury the evidence this exists to preserve — but a lane that
/// recovers and fails again, or fails a second time with a different code, is recorded again.
public final class LaneFailureLoggingHealthAdapter: CaptureHealthAdapter {
    private let wrapped: CaptureHealthAdapter
    private let log: any CaptureLaneFailureLogging
    private let lock = NSLock()
    private var reported: [CaptureLane: String] = [:]

    public init(wrapping wrapped: CaptureHealthAdapter, log: any CaptureLaneFailureLogging) {
        self.wrapped = wrapped
        self.log = log
    }

    public func emit(
        status: CaptureStatus,
        configuration: CaptureConfiguration,
        sentMonotonicNS: UInt64
    ) throws {
        // Before the delegate, not after: a heartbeat the server never receives is exactly the case
        // where the local record is the only evidence anyone will have.
        record(status.reportedLanes())
        try wrapped.emit(
            status: status,
            configuration: configuration,
            sentMonotonicNS: sentMonotonicNS
        )
    }

    /// Reads the same projection the heartbeat and the control channel report, so the log cannot
    /// name a different set of lanes than the ones the operator and the server are told about.
    private func record(_ lanes: [CaptureLaneStatus]) {
        for lane in lanes {
            let failed = lane.state == CaptureLaneStates.failed
            let signature = "\(lane.state)/\(lane.failureCode ?? "")"
            lock.lock()
            let alreadyRecorded = failed && reported[lane.lane] == signature
            reported[lane.lane] = failed ? signature : nil
            lock.unlock()
            if failed && !alreadyRecorded {
                log.recordLaneFailure(lane)
            }
        }
    }
}

extension LaneFailureLoggingHealthAdapter: @unchecked Sendable {}

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
    private let outbox: CaptureFrameOutbox
    private let pump: CaptureFramePublishPump
    private let frameObserver: CaptureAcknowledgedFrameObserving?
    private let state = CaptureControllerState()

    public init(
        source: CaptureSourceAdapter,
        transport: CaptureTransportAdapter,
        keyStore: CaptureKeyStoreAdapter,
        clock: CaptureClockAdapter,
        scheduler: CaptureSchedulerAdapter,
        health: CaptureHealthAdapter,
        outbox: CaptureFrameOutbox = CaptureFrameOutbox(),
        pump: CaptureFramePublishPump = CaptureFramePublishPump(),
        frameObserver: CaptureAcknowledgedFrameObserving? = nil
    ) {
        self.source = source
        self.transport = transport
        self.keyStore = keyStore
        self.clock = clock
        self.scheduler = scheduler
        self.health = health
        self.outbox = outbox
        self.pump = pump
        self.frameObserver = frameObserver
    }

    @discardableResult
    public func start(configuration: CaptureConfiguration) throws -> CaptureStatus {
        guard try keyStore.loadControlSecret() != nil else {
            throw CaptureControllerError.missingControlSecret
        }

        try state.beginStart(configuration: configuration)
        // A server session numbers each lane's frames from zero, so a new session starts from an
        // empty outbox with fresh wire sequences — and from a measurement that has forgotten the
        // previous session's timeline.
        outbox.reset()
        frameObserver?.observeSessionStart()
        do {
            try source.start(configuration: configuration)
        } catch {
            state.rollbackStart()
            throw error
        }
        do {
            // No pump exists yet, so nothing can be holding the turn; waiting is the honest
            // instruction for a pass whose frames no later tick would carry differently.
            try publishPendingFrames(configuration: configuration, onContention: .wait)
        } catch {
            // The audio is retained either way, so a transient answer at start is a degraded start
            // rather than a failed one: the pump delivers what is queued. A failure that no retry
            // can change means this process cannot publish at all — unwind instead of leaving a
            // capture running with nowhere to send it.
            guard CaptureFrameRetryPolicy.retryReason(for: error) != nil else {
                try? source.stop(deadline: clock.now())
                state.rollbackStart()
                throw error
            }
            state.recordPumpFailure(CapturePumpFailure(error: error))
        }
        let status = try emitHealth(configuration: configuration)
        let task = scheduler.schedule(label: "moss.capture.pump") { [weak self] in
            guard let self else { return }
            guard let configuration = self.state.runningConfiguration() else {
                return
            }
            do {
                // A tick that finds the previous pass still draining skips its publish turn, but it
                // still emits health: the server's helper lease is what a silent client loses, and
                // a long recovery drain must not be mistaken for a dead helper.
                let published = try self.publishPendingFrames(
                    configuration: configuration,
                    onContention: .skip
                )
                _ = try self.emitHealth(configuration: configuration)
                if published {
                    self.state.clearPumpFailure()
                }
            } catch {
                self.state.recordPumpFailure(CapturePumpFailure(error: error))
            }
        }
        state.storeHealthTask(task)
        return status
    }

    public func status() -> CaptureStatus {
        state.snapshot(lanes: source.status(), outbox: outbox.snapshot())
    }

    @discardableResult
    public func stop(deadline: Date) throws -> CaptureStatus {
        try state.requireRunning()
        let configuration = state.runningConfiguration()
        try source.stop(deadline: deadline)
        if let configuration {
            // The meeting's last partial frame only exists once the source has flushed, so the
            // final drain belongs after the stop. It waits for any pass still in flight rather than
            // skipping, because no later tick will carry these frames. A failure here loses nothing
            // — unacknowledged audio stays in the outbox and the returned status reports the depth
            // it kept.
            _ = try? publishPendingFrames(configuration: configuration, onContention: .wait)
        }
        let lanes = source.status()
        let (task, stopped) = state.finishStop(lanes: lanes, outbox: outbox.snapshot())
        task?.cancel()
        return stopped
    }

    /// Moves captured audio into the outbox, then publishes as much of the outbox as the server
    /// takes. Nothing captured is lost by a failure here: audio is released only by an
    /// acknowledgement, so whatever is not acknowledged is still queued for the next tick.
    ///
    /// Returns whether this call actually took a turn — a periodic tick that finds the previous
    /// pass still draining reports `false` and has observed nothing about the transport.
    @discardableResult
    private func publishPendingFrames(
        configuration: CaptureConfiguration,
        onContention contention: CaptureFramePublishPump.Contention
    ) throws -> Bool {
        for frame in try source.pendingFrames() {
            outbox.admit(frame)
        }

        let outbox = self.outbox
        let transport = self.transport
        let state = self.state
        let frameObserver = self.frameObserver
        let pass = pump.run(
            onContention: contention,
            retainedFrames: { outbox.retainedFrames() }
        ) { frame in
            try transport.publish(frame: frame, configuration: configuration)
            outbox.acknowledge(lane: frame.lane, sequence: frame.sequence)
            state.recordPublishedFrame()
            // After the acknowledgement, so what is observed is audio the server accepted — a frame
            // that is still being retried has not entered the server's timeline yet.
            frameObserver?.observeAcknowledgedFrame(
                lane: frame.lane,
                captureTimestampNS: frame.captureTimestampNS,
                sampleRate: frame.sampleRate,
                sampleCount: frame.sampleCount,
                discontinuity: frame.discontinuity
            )
        }

        if let failure = pass.failure {
            throw failure
        }
        return pass.ran
    }

    private func emitHealth(configuration: CaptureConfiguration) throws -> CaptureStatus {
        state.recordHealthEmissionAttempt()
        let current = state.snapshot(lanes: source.status(), outbox: outbox.snapshot())
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

    func snapshot(lanes: [CaptureLaneStatus], outbox: CaptureOutboxSnapshot) -> CaptureStatus {
        lock.lock()
        defer { lock.unlock() }
        return CaptureStatus(
            running: running,
            sessionID: configuration?.sessionID,
            lanes: lanes,
            publishedFrameCount: publishedFrameCount,
            lastHealthSequence: healthSequence,
            pumpFailure: pumpFailure,
            outbox: outbox
        )
    }

    func finishStop(
        lanes: [CaptureLaneStatus],
        outbox: CaptureOutboxSnapshot
    ) -> (CaptureCancellation?, CaptureStatus) {
        lock.lock()
        let stopped = CaptureStatus(
            running: false,
            sessionID: configuration?.sessionID,
            lanes: lanes,
            publishedFrameCount: publishedFrameCount,
            lastHealthSequence: healthSequence,
            pumpFailure: pumpFailure,
            outbox: outbox
        )
        let task = healthTask
        healthTask = nil
        configuration = nil
        running = false
        lock.unlock()
        return (task, stopped)
    }
}
