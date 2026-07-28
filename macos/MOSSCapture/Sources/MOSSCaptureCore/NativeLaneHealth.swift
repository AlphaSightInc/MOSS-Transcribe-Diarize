import Foundation

/// A lane that can no longer produce audio.
///
/// The partition between this and `NativeLaneDegradationCode` is the rule decision D-a settled:
/// *a lane failure means the lane can no longer produce audio; an event that loses some audio
/// while the lane keeps producing is a degradation.* Every code here names a lane that has
/// stopped and cannot resume by itself, which is why a failure is sticky for a capture
/// generation and why the server may close the lane on one.
///
/// Two enums rather than one enum plus a convention: a degradation structurally cannot be minted
/// where a failure is expected, so the classification cannot drift back by accident.
enum NativeLaneFailureCode: String, CaseIterable, Equatable {
    case permissionDenied = "macos_permission_denied"
    case deviceUnavailable = "macos_device_unavailable"
    case ioStoppedAbnormally = "macos_io_stopped_abnormally"
    case callbackStalled = "macos_callback_stalled"
    case unexpectedCaptureError = "macos_unexpected_capture_error"
}

/// A lane that lost something and kept producing audio.
enum NativeLaneDegradationCode: String, CaseIterable, Equatable {
    /// The drain fell behind the device and the queue dropped captured buffers. It is a statement
    /// about this process's consumer, not about the device: the lane is still capturing, and the
    /// count of what was lost travels with it. A dropped buffer never becomes a frame, so it is
    /// never *accepted* audio — this is capture loss, not accepted-audio loss.
    case bufferOverrun = "macos_buffer_overrun"
    /// A lane's health mailbox filled before anything drained it, so *facts* were lost — never
    /// audio. It reported itself as a buffer overrun until D-a, which made one code mean two
    /// unrelated things and let a lost fact be read as lost audio.
    case healthFactsDropped = "macos_health_facts_dropped"
}

enum NativeLanePermissionFact: Equatable {
    case undetermined
    case granted
    case denied
}

enum NativeLaneObservation: Equatable {
    case admitted
    case permission(NativeLanePermissionFact)
    case startFailed(NativeCaptureError)
    case deviceUnavailable(String)
    case ioStoppedAbnormally(String)
    case configurationChanged
    case reconciliationUnresolved(String)
    case overload(count: UInt64)
    case bufferOverrun(droppedBuffers: UInt64)
    /// Health facts the mailbox could not hold. Audio is untouched; what was lost is reporting.
    case healthFactsDropped(count: UInt64)
    case discontinuity(count: UInt64)
    case unexpectedCaptureError(String)
    case deviceEpoch(UInt64)
    case stoppedCleanly
}

typealias NativeLaneFact = NativeLaneObservation

struct NativeLaneFailure: Equatable {
    var code: NativeLaneFailureCode
    var cause: String
}

struct NativeLaneDegradation: Equatable {
    var code: NativeLaneDegradationCode
    var cause: String
}

protocol NativeLaneHealthFactSink: AnyObject {
    func enqueue(_ fact: NativeLaneFact, lane: CaptureLane, generation: UInt64)
}

final class NativeLaneHealth: NativeLaneHealthFactSink {
    private let lock = NSLock()
    private let mailboxCapacity: Int
    private var generation: UInt64 = 0
    private var mailboxes: [CaptureLane: NativeLaneMailbox] = [:]
    private var lanes: [CaptureLane: NativeLaneProjection] = [:]

    init(mailboxCapacity: Int = 128) {
        precondition(mailboxCapacity > 0)
        self.mailboxCapacity = mailboxCapacity
        resetForCurrentGeneration()
    }

    func beginGeneration() -> UInt64 {
        lock.lock()
        generation += 1
        resetForCurrentGeneration()
        let current = generation
        lock.unlock()
        return current
    }

    func currentGeneration() -> UInt64 {
        lock.lock()
        defer { lock.unlock() }
        return generation
    }

    func invalidateGeneration() {
        lock.lock()
        generation += 1
        resetForCurrentGeneration()
        lock.unlock()
    }

    func enqueue(_ fact: NativeLaneFact, lane: CaptureLane, generation: UInt64) {
        enqueue(
            fact,
            lane: lane,
            generation: generation,
            callbackMonotonicNS: DispatchTime.now().uptimeNanoseconds
        )
    }

    func enqueue(
        _ fact: NativeLaneFact,
        lane: CaptureLane,
        generation: UInt64,
        callbackMonotonicNS: UInt64
    ) {
        lock.lock()
        if generation == self.generation, var mailbox = mailboxes[lane] {
            mailbox.enqueue(fact, callbackMonotonicNS: callbackMonotonicNS)
            mailboxes[lane] = mailbox
        }
        lock.unlock()
    }

    func statuses(running: Bool) -> [CaptureLaneStatus] {
        drainAcceptedFacts()
        lock.lock()
        let snapshot = CaptureLane.allCases.map { lane in
            let projection = lanes[lane, default: NativeLaneProjection()]
            return CaptureLaneStatus(
                lane: lane,
                sequence: projection.sequence,
                deviceEpoch: projection.deviceEpoch,
                state: projection.reportedState(running: running),
                droppedFrames: projection.droppedFrames,
                discontinuities: projection.discontinuities,
                failureCode: projection.reportedCode
            )
        }
        lock.unlock()
        return snapshot
    }

    func failure(for lane: CaptureLane) -> NativeLaneFailure? {
        drainAcceptedFacts()
        lock.lock()
        let failure = lanes[lane]?.failure
        lock.unlock()
        return failure
    }

    func detachAcceptedFacts() -> [NativeLaneBatch] {
        lock.lock()
        let batches = CaptureLane.allCases.compactMap { lane -> NativeLaneBatch? in
            guard var mailbox = mailboxes[lane] else {
                return nil
            }
            let batch = mailbox.detach(lane: lane)
            mailboxes[lane] = mailbox
            return batch
        }
        lock.unlock()
        return batches
    }

    func applyDetachedFacts(_ batches: [NativeLaneBatch]) {
        for batch in batches {
            lock.lock()
            guard batch.generation == generation else {
                lock.unlock()
                continue
            }
            for entry in batch.entries {
                NativeLaneHealthReducer.reduce(entry.fact, lane: batch.lane, into: &lanes)
            }
            lock.unlock()
        }
    }

    private func resetForCurrentGeneration() {
        mailboxes = Dictionary(
            uniqueKeysWithValues: CaptureLane.allCases.map {
                (
                    $0,
                    NativeLaneMailbox(
                        generation: generation,
                        capacity: mailboxCapacity
                    )
                )
            }
        )
        lanes = Dictionary(
            uniqueKeysWithValues: CaptureLane.allCases.map {
                ($0, NativeLaneProjection())
            }
        )
    }

    private func drainAcceptedFacts() {
        applyDetachedFacts(detachAcceptedFacts())
    }
}

private struct NativeLaneHealthReducer {
    static func reduce(
        _ observation: NativeLaneObservation,
        lane: CaptureLane,
        into lanes: inout [CaptureLane: NativeLaneProjection]
    ) {
        var projection = lanes[lane, default: NativeLaneProjection()]
        switch observation {
        case .admitted:
            if projection.failure == nil {
                projection.state = CaptureLaneStates.capturing
            }
        case .permission(.denied):
            projection.recordFailure(.permissionDenied, cause: "permission denied")
        case .permission(.undetermined), .permission(.granted):
            break
        case .startFailed(let error):
            if let failure = Self.failure(for: error) {
                projection.recordFailure(failure.code, cause: failure.cause)
            }
        case .deviceUnavailable(let cause):
            projection.recordFailure(.deviceUnavailable, cause: cause)
        case .ioStoppedAbnormally(let cause):
            projection.recordFailure(.ioStoppedAbnormally, cause: cause)
        case .configurationChanged:
            if projection.failure == nil {
                projection.state = CaptureLaneStates.recovering
            }
        case .reconciliationUnresolved:
            break
        case .overload:
            break
        case .bufferOverrun(let droppedBuffers):
            projection.droppedFrames += droppedBuffers
            if droppedBuffers > 0 {
                projection.recordDegradation(
                    .bufferOverrun,
                    cause: "dropped buffers: \(droppedBuffers)"
                )
            }
        case .healthFactsDropped(let count):
            // Deliberately not `droppedFrames`: that counter is audio, and the PRD's accounting
            // reads it. Facts and frames are different losses and must not share a number.
            if count > 0 {
                projection.recordDegradation(
                    .healthFactsDropped,
                    cause: "dropped health facts: \(count)"
                )
            }
        case .discontinuity(let count):
            projection.discontinuities += count
        case .unexpectedCaptureError(let cause):
            projection.recordFailure(.unexpectedCaptureError, cause: cause)
        case .deviceEpoch(let deviceEpoch):
            projection.deviceEpoch = deviceEpoch
            if projection.failure == nil {
                projection.state = CaptureLaneStates.capturing
            }
        case .stoppedCleanly:
            if projection.failure == nil {
                projection.state = CaptureLaneStates.stopped
            }
        }
        lanes[lane] = projection
    }

    private static func failure(for error: NativeCaptureError) -> NativeLaneFailure? {
        switch error {
        case .permissionDenied(let cause):
            return NativeLaneFailure(code: .permissionDenied, cause: cause)
        case .deviceUnavailable(let cause), .unavailable(let cause):
            return NativeLaneFailure(code: .deviceUnavailable, cause: cause)
        case .osStatus(let operation, let status):
            return NativeLaneFailure(
                code: .unexpectedCaptureError,
                cause: "\(operation) OSStatus \(status)"
            )
        case .transportUnavailable:
            return nil
        }
    }
}

struct NativeLaneBatch: Equatable {
    var lane: CaptureLane
    var generation: UInt64
    var entries: [SequencedNativeLaneFact]
}

struct SequencedNativeLaneFact: Equatable {
    var mailboxOrder: UInt64
    var callbackMonotonicNS: UInt64
    var fact: NativeLaneFact
}

private struct NativeLaneMailbox {
    var generation: UInt64
    var capacity: Int
    var nextMailboxOrder: UInt64 = 0
    var overflowFenced = false
    var entries: [SequencedNativeLaneFact] = []

    /// Facts in, until the mailbox is full — and then one fact saying so, and nothing after it.
    ///
    /// Until D-a an overrun also fenced the mailbox, because an overrun was a lane failure and a
    /// failed lane had nothing left to report. Now that an overrun is a degradation, that fence
    /// would silence every later fact on a lane that is *still producing audio* — including the
    /// device failure that genuinely ends it. The only fence left is the one that is true by
    /// construction: once facts have been dropped, this mailbox's account of the lane is
    /// incomplete and later entries would misrepresent it as complete.
    mutating func enqueue(_ fact: NativeLaneFact, callbackMonotonicNS: UInt64) {
        guard !overflowFenced else {
            return
        }
        guard entries.count < capacity else {
            append(
                .healthFactsDropped(count: 1),
                callbackMonotonicNS: callbackMonotonicNS
            )
            overflowFenced = true
            return
        }
        append(fact, callbackMonotonicNS: callbackMonotonicNS)
    }

    mutating func detach(lane: CaptureLane) -> NativeLaneBatch? {
        guard !entries.isEmpty else {
            return nil
        }
        let batch = NativeLaneBatch(
            lane: lane,
            generation: generation,
            entries: entries
        )
        entries.removeAll(keepingCapacity: true)
        return batch
    }

    private mutating func append(
        _ fact: NativeLaneFact,
        callbackMonotonicNS: UInt64
    ) {
        entries.append(
            SequencedNativeLaneFact(
                mailboxOrder: nextMailboxOrder,
                callbackMonotonicNS: callbackMonotonicNS,
                fact: fact
            )
        )
        nextMailboxOrder += 1
    }

}

private struct NativeLaneProjection {
    var state = CaptureLaneStates.stopped
    var sequence: UInt64 = 0
    var deviceEpoch: UInt64 = 0
    var droppedFrames: UInt64 = 0
    var discontinuities: UInt64 = 0
    var failure: NativeLaneFailure?
    var degradation: NativeLaneDegradation?

    /// What the lane is doing, in the one vocabulary every reporting surface shares.
    ///
    /// The order is precedence and it is the order the facts answer in: a lane that cannot
    /// produce audio is `failed` whether or not the capture is running; a capture that is not
    /// running has no capturing lanes; a running lane that lost audio and kept going is
    /// `degraded`. `degraded` is not a new word on the wire — the server's helper contract has
    /// always accepted it and has always declined to fail a lane for it; this client simply never
    /// had a way to say it.
    func reportedState(running: Bool) -> String {
        if failure != nil {
            return CaptureLaneStates.failed
        }
        guard running else {
            return CaptureLaneStates.stopped
        }
        if degradation != nil {
            return CaptureLaneStates.degraded
        }
        return state
    }

    /// The typed code for whichever verdict `reportedState` names.
    ///
    /// The wire has one code slot and the contract requires it only for `failed` while permitting
    /// it elsewhere, so a degradation travels in the same field rather than in silence. A lane
    /// that lost audio for a reason nobody can name is the defect this whole phase exists to fix.
    var reportedCode: String? {
        failure?.code.rawValue ?? degradation?.code.rawValue
    }

    mutating func recordFailure(_ code: NativeLaneFailureCode, cause: String) {
        guard failure == nil else {
            return
        }
        failure = NativeLaneFailure(code: code, cause: cause)
    }

    /// First cause wins and lasts the generation, exactly as a failure does.
    ///
    /// A verdict about a lane is a verdict about *this* capture generation: `beginGeneration()`
    /// clears it, and nothing inside a generation un-says it. Un-degrading on a quiet tick would
    /// need a "no drops for N ticks" threshold nothing has measured, and it would trade a durable
    /// statement — this meeting lost audio on this lane — for a flickering one. The live count of
    /// what was lost keeps rising in `droppedFrames` either way.
    mutating func recordDegradation(_ code: NativeLaneDegradationCode, cause: String) {
        guard degradation == nil else {
            return
        }
        degradation = NativeLaneDegradation(code: code, cause: cause)
    }
}
