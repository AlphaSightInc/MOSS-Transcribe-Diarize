import Foundation

/// Sends one pass of unacknowledged audio, with the transport's work bounded in two independent
/// ways.
///
/// *Width — one request in flight per lane, lanes at the same time.* A lane has to arrive in
/// sequence order, so a lane can never have two requests outstanding; the lanes are independent of
/// each other, so nothing is gained by making one wait for the other. In-flight work is therefore
/// bounded by the number of lanes and never by how much audio is waiting. That is what makes a
/// recovery predictable: a full retention window is thirty frames per lane, and sending both lanes
/// through a single serial loop would take twice as long as the wire requires at a round trip of
/// tens of milliseconds.
///
/// *Time — passes never overlap.* A periodic tick that arrives while the previous pass is still
/// draining a backlog has nothing to contribute: the audio it would send is already retained, and
/// the running pass or the next tick carries it. Starting a second pass over the same retained
/// frames would publish identities that are already in flight and multiply in-flight work by the
/// number of late ticks, so a tick skips its turn instead. A stop waits rather than skipping,
/// because the meeting's final frames only reach the wire through that last pass.
///
/// Nothing here decides *whether* a frame may be dropped. Audio is released only by an
/// acknowledgement inside `send`, so a skipped pass and a stalled lane both leave the audio queued.
public final class CaptureFramePublishPump: @unchecked Sendable {
    /// What a caller does when another pass is already running.
    public enum Contention {
        /// Give up this turn — the retained audio is not going anywhere.
        case skip
        /// Wait for the running pass and then take a turn, because this pass carries frames that no
        /// later tick will.
        case wait
    }

    /// The outcome of one call. `ran` is false only when the caller chose `.skip` and another pass
    /// held the turn.
    public struct Pass {
        public var ran: Bool
        public var failure: Error?

        public init(ran: Bool, failure: Error? = nil) {
            self.ran = ran
            self.failure = failure
        }
    }

    /// One serial queue per lane: a lane's requests are ordered by construction and the lanes run
    /// on separate threads. The queues are created once, so the number of threads the transport can
    /// occupy does not grow with the backlog, the meeting length, or the tick count.
    private let laneQueues: [CaptureLane: DispatchQueue]
    private let passGate = NSCondition()
    private var passRunning = false

    public init() {
        laneQueues = Dictionary(
            uniqueKeysWithValues: CaptureLane.allCases.map { lane in
                (lane, DispatchQueue(label: "moss.capture.publish.\(lane.rawValue)"))
            }
        )
    }

    /// Sends everything `retainedFrames` reports — already in per-lane order — and returns the
    /// failure the caller should surface. `send` publishes one frame and, on success, releases it;
    /// it is called from the lane's own thread, at most once per frame, and never concurrently for
    /// the same lane.
    ///
    /// `retainedFrames` is read *after* the turn is won, never before. A caller that waited would
    /// otherwise work from a list captured while the previous pass still had those frames in
    /// flight, and re-send identities that were about to be acknowledged.
    @discardableResult
    public func run(
        onContention contention: Contention,
        retainedFrames: () -> [CaptureFrame],
        send: @escaping (CaptureFrame) throws -> Void
    ) -> Pass {
        guard beginPass(onContention: contention) else {
            return Pass(ran: false)
        }
        defer { endPass() }
        return Pass(ran: true, failure: sendLanesConcurrently(frames: retainedFrames(), send: send))
    }

    /// True while a pass holds the turn. Exposed so a caller can report that the transport is busy
    /// rather than idle.
    public var isRunningPass: Bool {
        passGate.lock()
        defer { passGate.unlock() }
        return passRunning
    }

    private func sendLanesConcurrently(
        frames: [CaptureFrame],
        send: @escaping (CaptureFrame) throws -> Void
    ) -> Error? {
        guard !frames.isEmpty else {
            return nil
        }
        var framesByLane: [CaptureLane: [CaptureFrame]] = [:]
        for frame in frames {
            framesByLane[frame.lane, default: []].append(frame)
        }

        let failures = CaptureLaneFailureBox()
        let carried = CaptureLaneSend(send: send)
        let group = DispatchGroup()
        for lane in CaptureLane.allCases {
            guard let laneFrames = framesByLane[lane],
                  !laneFrames.isEmpty,
                  let queue = laneQueues[lane] else {
                continue
            }
            queue.async(group: group) {
                for frame in laneFrames {
                    do {
                        try carried.send(frame)
                    } catch {
                        // The lane has to arrive in sequence order, so its first unacknowledged
                        // frame stops that lane for this pass — and only that lane. The rest of its
                        // backlog is not re-attempted here, which is what keeps a stalled lane from
                        // hammering the server with a whole window of doomed requests.
                        failures.record(error, lane: lane)
                        return
                    }
                }
            }
        }
        group.wait()
        // Reported in lane order rather than in whichever thread finished first, so two lanes
        // failing in one pass always surfaces the same failure.
        return failures.firstFailure(inLaneOrder: CaptureLane.allCases)
    }

    private func beginPass(onContention contention: Contention) -> Bool {
        passGate.lock()
        defer { passGate.unlock() }
        while passRunning {
            guard contention == .wait else {
                return false
            }
            passGate.wait()
        }
        passRunning = true
        return true
    }

    private func endPass() {
        passGate.lock()
        passRunning = false
        passGate.broadcast()
        passGate.unlock()
    }
}

/// Carries the caller's per-frame publish onto the lane threads. The lanes call it at the same
/// time, so whatever it touches has to tolerate that; what the pump guarantees in exchange is that
/// one lane never calls it twice at once and that each frame is offered at most once per pass.
private struct CaptureLaneSend: @unchecked Sendable {
    let send: (CaptureFrame) throws -> Void
}

private final class CaptureLaneFailureBox: @unchecked Sendable {
    private let lock = NSLock()
    private var failuresByLane: [CaptureLane: Error] = [:]

    func record(_ error: Error, lane: CaptureLane) {
        lock.lock()
        failuresByLane[lane] = error
        lock.unlock()
    }

    func firstFailure(inLaneOrder lanes: [CaptureLane]) -> Error? {
        lock.lock()
        defer { lock.unlock() }
        return lanes.compactMap { failuresByLane[$0] }.first
    }
}
