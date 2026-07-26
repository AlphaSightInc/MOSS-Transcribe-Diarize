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
    private var generation: UInt64 = 0
    private var mailboxes: [CaptureLane: NativeLaneMailbox] = [:]
    private var lanes: [CaptureLane: NativeLaneProjection] = [:]

    init() {
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
        lock.lock()
        if generation == self.generation {
            mailboxes[lane]?.facts.append(fact)
        }
        lock.unlock()
    }

    func statuses(running: Bool) -> [CaptureLaneStatus] {
        lock.lock()
        drainAcceptedFacts()
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
        lock.lock()
        drainAcceptedFacts()
        let failure = lanes[lane]?.failure
        lock.unlock()
        return failure
    }

    private func resetForCurrentGeneration() {
        mailboxes = Dictionary(
            uniqueKeysWithValues: CaptureLane.allCases.map {
                ($0, NativeLaneMailbox(generation: generation))
            }
        )
        lanes = Dictionary(
            uniqueKeysWithValues: CaptureLane.allCases.map {
                ($0, NativeLaneProjection())
            }
        )
    }

    private func drainAcceptedFacts() {
        for lane in CaptureLane.allCases {
            guard var mailbox = mailboxes[lane],
                  mailbox.generation == generation,
                  !mailbox.facts.isEmpty else {
                continue
            }
            let facts = mailbox.facts
            mailbox.facts.removeAll(keepingCapacity: true)
            mailboxes[lane] = mailbox
            for fact in facts {
                NativeLaneHealthReducer.reduce(fact, lane: lane, into: &lanes)
            }
        }
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

private struct NativeLaneMailbox {
    var generation: UInt64
    var facts: [NativeLaneFact] = []
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
