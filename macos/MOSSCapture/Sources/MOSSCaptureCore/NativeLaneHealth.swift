import Foundation

enum NativeLaneFailureCode: String, CaseIterable, Equatable {
    case permissionDenied = "macos_permission_denied"
    case deviceUnavailable = "macos_device_unavailable"
    case ioStoppedAbnormally = "macos_io_stopped_abnormally"
    case callbackStalled = "macos_callback_stalled"
    case bufferOverrun = "macos_buffer_overrun"
    case unexpectedCaptureError = "macos_unexpected_capture_error"
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
            let state = projection.failure == nil
                ? (running ? projection.state : "stopped")
                : "failed"
            return CaptureLaneStatus(
                lane: lane,
                sequence: projection.sequence,
                deviceEpoch: projection.deviceEpoch,
                state: state,
                droppedFrames: projection.droppedFrames,
                discontinuities: projection.discontinuities,
                failureCode: projection.failure?.code.rawValue
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
                projection.state = "capturing"
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
                projection.state = "recovering"
            }
        case .reconciliationUnresolved:
            break
        case .overload:
            break
        case .bufferOverrun(let droppedBuffers):
            projection.droppedFrames += droppedBuffers
            if droppedBuffers > 0 {
                projection.recordFailure(.bufferOverrun, cause: "dropped buffers: \(droppedBuffers)")
            }
        case .discontinuity(let count):
            projection.discontinuities += count
        case .unexpectedCaptureError(let cause):
            projection.recordFailure(.unexpectedCaptureError, cause: cause)
        case .deviceEpoch(let deviceEpoch):
            projection.deviceEpoch = deviceEpoch
            if projection.failure == nil {
                projection.state = "capturing"
            }
        case .stoppedCleanly:
            if projection.failure == nil {
                projection.state = "stopped"
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
    var terminalFenced = false
    var entries: [SequencedNativeLaneFact] = []

    mutating func enqueue(_ fact: NativeLaneFact, callbackMonotonicNS: UInt64) {
        guard !terminalFenced else {
            return
        }
        if isTerminalOverrun(fact) {
            append(fact, callbackMonotonicNS: callbackMonotonicNS)
            terminalFenced = true
            return
        }
        guard entries.count < capacity else {
            append(
                .bufferOverrun(droppedBuffers: 1),
                callbackMonotonicNS: callbackMonotonicNS
            )
            terminalFenced = true
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

    private func isTerminalOverrun(_ fact: NativeLaneFact) -> Bool {
        if case .bufferOverrun(let droppedBuffers) = fact {
            return droppedBuffers > 0
        }
        return false
    }
}

private struct NativeLaneProjection {
    var state = "stopped"
    var sequence: UInt64 = 0
    var deviceEpoch: UInt64 = 0
    var droppedFrames: UInt64 = 0
    var discontinuities: UInt64 = 0
    var failure: NativeLaneFailure?

    mutating func recordFailure(_ code: NativeLaneFailureCode, cause: String) {
        guard failure == nil else {
            return
        }
        failure = NativeLaneFailure(code: code, cause: cause)
    }
}
