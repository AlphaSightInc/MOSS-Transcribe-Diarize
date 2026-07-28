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
    /// The lane lost some audio and is still producing. The server's helper contract has always
    /// had this word and has always declined to fail a lane for it; before D-a this client had no
    /// way to say it, so the one condition that means "keep going, with less" was reported as the
    /// one that means "this lane is over".
    public static let degraded = "degraded"
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
    /// Set once the server has said this session is not this client's to publish to. `running`
    /// stays true while the microphones are still hot — this is what says the audio has nowhere
    /// left to go.
    public var sessionRefusal: CaptureSessionRefusal?
    public var outbox: CaptureOutboxSnapshot

    public init(
        running: Bool,
        sessionID: String?,
        lanes: [CaptureLaneStatus],
        publishedFrameCount: Int,
        lastHealthSequence: UInt64?,
        pumpFailure: CapturePumpFailure? = nil,
        sessionRefusal: CaptureSessionRefusal? = nil,
        outbox: CaptureOutboxSnapshot = CaptureOutboxSnapshot()
    ) {
        self.running = running
        self.sessionID = sessionID
        self.lanes = lanes
        self.publishedFrameCount = publishedFrameCount
        self.lastHealthSequence = lastHealthSequence
        self.pumpFailure = pumpFailure
        self.sessionRefusal = sessionRefusal
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

/// What the server has said about the session this capture publishes to.
///
/// `CapturePumpFailure` answers "can the pump publish right now"; this answers the different
/// question "does this session still exist for this client", and neither substitutes for the other.
/// The heartbeat that ends a meeting is refused for an authoritative reason and classified as
/// `transportUnavailable` — indistinguishable from a dropped network — which is why an operator
/// reading `running: true` had no way to see that the server had already released the session.
///
/// Only statuses whose meaning is *this session is not available to this client, and no retry
/// changes that* appear here. `409` deliberately does not: this wire uses it both for a closed
/// session and for a frame that arrived out of sequence, so the client cannot tell a finished
/// meeting from a recoverable ordering conflict, and reporting a session gone on the strength of an
/// overloaded code would be a fresh false report rather than a fix for the old one.
public enum CaptureSessionRefusal: String, Codable, Equatable, Sendable {
    /// 401 — the authority this client publishes with is no longer accepted.
    case credentialRejected
    /// 403 — the server does not consider this session this device's. A session the server has
    /// released answers exactly this way, and it never stops: a release is one-way.
    case sessionDisowned
    /// 404 — the server has no session under this id.
    case sessionUnknown
    /// 410 — the session existed and has been retired.
    case sessionGone

    /// Reads a refusal out of a transport failure, or `nil` when the failure says nothing about
    /// whether the session still exists — a lost network, a busy server, a missing pin.
    public init?(error: Error) {
        guard let transport = error as? CaptureHTTPTransportError,
              case .nonSuccessStatus(let statusCode) = transport else {
            return nil
        }
        self.init(statusCode: statusCode)
    }

    public init?(statusCode: Int) {
        switch statusCode {
        case 401:
            self = .credentialRejected
        case 403:
            self = .sessionDisowned
        case 404:
            self = .sessionUnknown
        case 410:
            self = .sessionGone
        default:
            return nil
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
/// One line per lane per fault. A lane's verdict is sticky for the life of a capture generation,
/// so logging it every 0.5 s tick would bury the evidence this exists to preserve — but a lane that
/// recovers and faults again, or faults a second time with a different code, is recorded again.
///
/// A **degradation** is recorded here as well as a failure. D-a made a buffer overrun a
/// degradation, and the two live diagnoses that found it — F1's and F3's — were both read off this
/// line: reclassifying the condition without following it here would have traded a dead meeting
/// for a blind one.
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
            let faulted = lane.state == CaptureLaneStates.failed
                || lane.state == CaptureLaneStates.degraded
            let signature = "\(lane.state)/\(lane.failureCode ?? "")"
            lock.lock()
            let alreadyRecorded = faulted && reported[lane.lane] == signature
            reported[lane.lane] = faulted ? signature : nil
            lock.unlock()
            if faulted && !alreadyRecorded {
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
            recordTransportVerdict(error)
            guard CaptureFrameRetryPolicy.retryReason(for: error) != nil else {
                try? source.stop(deadline: clock.now())
                state.rollbackStart()
                throw error
            }
        }
        let status: CaptureStatus
        do {
            status = try emitHealth(configuration: configuration)
        } catch {
            // The same rule as the publish above, and for the same reason: the start-time heartbeat
            // is a report about the capture, not the capture itself. A transient refusal is a
            // degraded start — the pump's next tick emits health again. A refusal no retry can
            // change means this process cannot hold this session at all, and letting that throw
            // escape is what left both lanes hot with no pump draining them: `running` stayed true,
            // the source overran unattended, and `alreadyRunning` refused every later start.
            recordTransportVerdict(error)
            guard CaptureFrameRetryPolicy.retryReason(for: error) != nil else {
                try? source.stop(deadline: clock.now())
                state.rollbackStart()
                throw error
            }
            status = state.snapshot(lanes: source.status(), outbox: outbox.snapshot())
        }
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
                if published {
                    self.state.clearPumpFailure()
                }
            } catch {
                self.recordTransportVerdict(error)
            }
            // Outside the publish's `do`, because a publish that *throws* needs the heartbeat more
            // than a healthy one does. A lane the server has closed refuses the same retained frame
            // on every tick, so a heartbeat coupled to the publish stops for the rest of the
            // meeting — and thirty seconds later the helper lease expires and the server ends a
            // session that was still one healthy lane and an accepted heartbeat away from working.
            // The publish's failure is left standing: this emission reports it rather than clearing
            // it, and only a publish that succeeds says the transport recovered.
            do {
                _ = try self.emitHealth(configuration: configuration)
            } catch {
                self.recordTransportVerdict(error)
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
            do {
                _ = try publishPendingFrames(configuration: configuration, onContention: .wait)
            } catch {
                // The drain's failure is still not the operator's problem, with one exception: a
                // server that refuses the session is telling us the meeting was already over, and
                // that is exactly what the returned status has to say instead of a clean stop.
                state.recordSessionRefusal(from: error)
            }
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

    /// Records what one failed request to the server says, on every path that talks to it — the
    /// start's publish, the start's heartbeat, and the tick's two halves. Both facts are read from
    /// the same error because they answer different questions: `pumpFailure` says whether this
    /// client can reach the server right now and clears on the next successful publish, while a
    /// refusal names a verdict on this session id that no retry changes.
    private func recordTransportVerdict(_ error: Error) {
        state.recordPumpFailure(CapturePumpFailure(error: error))
        state.recordSessionRefusal(from: error)
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
    private var sessionRefusal: CaptureSessionRefusal?

    func beginStart(configuration: CaptureConfiguration) throws {
        lock.lock()
        defer { lock.unlock() }
        guard !running else {
            throw CaptureControllerError.alreadyRunning
        }
        self.configuration = configuration
        running = true
        pumpFailure = nil
        // A refusal names one session id, so a new session starts without the last one's verdict.
        sessionRefusal = nil
    }

    /// Undoes a start that could not complete. The pump failure goes with it — nothing is pumping —
    /// but a refusal the server gave during that start is kept: it is the only record of *why* the
    /// start failed, and an operator reading `status` afterwards has nowhere else to find it.
    /// `beginStart` clears it, so a refusal can never outlive the session id it names.
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

    /// Keeps the server's verdict on this session, if the failure carried one. Deliberately not
    /// cleared by a later success the way a pump failure is: the refusal answers a question about
    /// this session id, and the server's answer to that question is final.
    func recordSessionRefusal(from error: Error) {
        guard let refusal = CaptureSessionRefusal(error: error) else {
            return
        }
        lock.lock()
        sessionRefusal = refusal
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
            sessionRefusal: sessionRefusal,
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
            sessionRefusal: sessionRefusal,
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
