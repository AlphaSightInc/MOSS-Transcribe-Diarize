import Foundation

/// Why one published frame has to be re-sent with its identity unchanged.
///
/// Every reason here describes a failure of the *attempt*, never of the audio: the frame is still
/// the frame the server has to receive, so the retry reuses the original `(lane, sequence)`. The
/// server acknowledges that identity idempotently, which is what makes an ambiguous answer safe to
/// resolve by simply asking again — a replay returns the original acknowledgement instead of
/// admitting the audio twice.
public enum CaptureFrameRetryReason: String, Codable, Equatable, Sendable {
    /// The request left this process but no answer came back, so whether the server accepted the
    /// frame is unknown.
    case ambiguous
    /// The server asked for less work: 429.
    case backpressure
    /// The server answered about itself rather than about this frame: 5xx.
    case serverUnavailable
}

/// Decides whether a publish failure means "send this exact frame again".
///
/// Retryability is a property of the failure alone. It never depends on how long a frame has
/// waited, because waiting is not evidence of delivery: audio leaves the outbox only when the
/// server acknowledges it.
public enum CaptureFrameRetryPolicy {
    public static func retryReason(for error: Error) -> CaptureFrameRetryReason? {
        if let transport = error as? CaptureHTTPTransportError {
            switch transport {
            case .nonSuccessStatus(let statusCode):
                return retryReason(forStatusCode: statusCode)
            case .missingCaptureBearer, .missingCertificatePin:
                // Nothing about the wire will change on a retry: this client is not authorized to
                // publish at all until it is paired again.
                return nil
            }
        }
        if let urlError = error as? URLError {
            return retryReason(forURLErrorCode: urlError.code)
        }
        return nil
    }

    public static func retryReason(forStatusCode statusCode: Int) -> CaptureFrameRetryReason? {
        switch statusCode {
        case 0:
            // No HTTP response was observed at all, so acceptance is unknown.
            return .ambiguous
        case 408:
            return .ambiguous
        case 429:
            return .backpressure
        case 500...599:
            return .serverUnavailable
        default:
            return nil
        }
    }

    public static func retryReason(forURLErrorCode code: URLError.Code) -> CaptureFrameRetryReason? {
        switch code {
        case .timedOut,
             .networkConnectionLost,
             .cannotConnectToHost,
             .cannotFindHost,
             .dnsLookupFailed,
             .notConnectedToInternet,
             .resourceUnavailable,
             .internationalRoamingOff,
             .dataNotAllowed,
             .callIsActive:
            return .ambiguous
        default:
            // A refused pin, a cancelled task, or a malformed URL are not transient: retrying the
            // identical request cannot change the answer.
            return nil
        }
    }
}

/// A lane state the operator has to be told about, because audio that was captured never reached
/// the server. It is deliberately not clearable by later success: a run that lost audio must not
/// report clean afterwards.
public enum CaptureOutboxDegradation: String, Codable, Equatable, Sendable {
    /// A lane was already holding its whole retention window of unacknowledged audio when new audio
    /// arrived. Retained audio is never discarded to make room: dropping an unacknowledged frame
    /// would leave a permanent hole in the lane's sequence stream, which the server rejects for
    /// every later frame.
    case overflowedLaneRetention
    /// A frame that does not describe positive audio can never be acknowledged, so it is refused
    /// rather than left to occupy the window forever.
    case undeliverableFrame
}

/// What the outbox currently holds. Depth is reported so a bounded run can be proven bounded.
public struct CaptureOutboxSnapshot: Equatable, Sendable {
    public var retainedFrames: Int
    public var retainedSecondsByLane: [CaptureLane: Double]
    public var refusedFrames: UInt64
    public var degradation: CaptureOutboxDegradation?

    public init(
        retainedFrames: Int = 0,
        retainedSecondsByLane: [CaptureLane: Double] = [:],
        refusedFrames: UInt64 = 0,
        degradation: CaptureOutboxDegradation? = nil
    ) {
        self.retainedFrames = retainedFrames
        self.retainedSecondsByLane = retainedSecondsByLane
        self.refusedFrames = refusedFrames
        self.degradation = degradation
    }
}

/// Holds captured audio until the server acknowledges it.
///
/// The outbox is the authority for wire identity: it stamps the `(lane, sequence)` a frame keeps
/// for every attempt, so a refused frame burns no sequence number and the admitted stream stays
/// gapless even after audio is lost. That is what lets a lane keep publishing after an overflow
/// instead of being rejected forever as out of order — and the loss is still reported, both as a
/// typed degraded state and as a discontinuity on the next frame that lane admits.
///
/// Capacity is audio duration, not a frame count, so it holds for any frame size or sample rate the
/// capture side happens to produce.
public final class CaptureFrameOutbox: @unchecked Sendable {
    /// Domain contract: the client retains 15 s of audio per lane awaiting acknowledgement.
    public static let retainedSecondsPerLane: Double = 15

    private let capacitySeconds: Double
    private let lock = NSLock()
    /// Admission order, so frames leave in the order they were captured across lanes.
    private var retained: [CaptureFrame] = []
    private var nextWireSequence: [CaptureLane: UInt64] = [:]
    private var lanesMissingAudio: Set<CaptureLane> = []
    private var refusedFrames: UInt64 = 0
    private var degradation: CaptureOutboxDegradation?

    public init(retainedSecondsPerLane: Double = CaptureFrameOutbox.retainedSecondsPerLane) {
        precondition(retainedSecondsPerLane > 0)
        capacitySeconds = retainedSecondsPerLane
    }

    /// Takes ownership of one captured frame and stamps the wire identity it keeps until it is
    /// acknowledged. Returns `nil` when the lane cannot take it, which is the only case in which
    /// captured audio is dropped.
    @discardableResult
    public func admit(_ frame: CaptureFrame) -> CaptureFrame? {
        lock.lock()
        defer { lock.unlock() }

        guard let duration = Self.seconds(of: frame) else {
            refusedFrames += 1
            degradation = .undeliverableFrame
            if frame.sampleCount > 0 {
                lanesMissingAudio.insert(frame.lane)
            }
            return nil
        }
        guard retainedSeconds(lane: frame.lane) + duration <= capacitySeconds else {
            refusedFrames += 1
            degradation = .overflowedLaneRetention
            lanesMissingAudio.insert(frame.lane)
            return nil
        }

        var admitted = frame
        admitted.sequence = nextWireSequence[frame.lane, default: 0]
        if lanesMissingAudio.remove(frame.lane) != nil {
            admitted.discontinuity = true
        }
        nextWireSequence[frame.lane] = admitted.sequence + 1
        retained.append(admitted)
        return admitted
    }

    /// Every unacknowledged frame, in admission order across lanes.
    public func retainedFrames() -> [CaptureFrame] {
        lock.lock()
        defer { lock.unlock() }
        return retained
    }

    public func retainedFrames(lane: CaptureLane) -> [CaptureFrame] {
        lock.lock()
        defer { lock.unlock() }
        return retained.filter { $0.lane == lane }
    }

    /// Releases one acknowledged identity. Nothing else releases audio.
    public func acknowledge(lane: CaptureLane, sequence: UInt64) {
        lock.lock()
        retained.removeAll { $0.lane == lane && $0.sequence == sequence }
        lock.unlock()
    }

    public func snapshot() -> CaptureOutboxSnapshot {
        lock.lock()
        defer { lock.unlock() }
        var secondsByLane: [CaptureLane: Double] = [:]
        for lane in CaptureLane.allCases {
            secondsByLane[lane] = retainedSeconds(lane: lane)
        }
        return CaptureOutboxSnapshot(
            retainedFrames: retained.count,
            retainedSecondsByLane: secondsByLane,
            refusedFrames: refusedFrames,
            degradation: degradation
        )
    }

    /// Starts a new session's wire numbering from zero. A server session counts each lane's frames
    /// from zero, so carrying the previous session's sequences into a new one would make every
    /// frame out of order.
    public func reset() {
        lock.lock()
        retained.removeAll(keepingCapacity: true)
        nextWireSequence.removeAll(keepingCapacity: true)
        lanesMissingAudio.removeAll(keepingCapacity: true)
        refusedFrames = 0
        degradation = nil
        lock.unlock()
    }

    private func retainedSeconds(lane: CaptureLane) -> Double {
        retained.reduce(into: 0) { total, frame in
            guard frame.lane == lane, let seconds = Self.seconds(of: frame) else {
                return
            }
            total += seconds
        }
    }

    private static func seconds(of frame: CaptureFrame) -> Double? {
        guard frame.sampleRate > 0, frame.sampleCount > 0 else {
            return nil
        }
        return Double(frame.sampleCount) / Double(frame.sampleRate)
    }
}
