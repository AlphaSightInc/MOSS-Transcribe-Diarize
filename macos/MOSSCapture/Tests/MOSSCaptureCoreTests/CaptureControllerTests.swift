import CryptoKit
import CoreAudio
import Darwin
import Foundation
import Security
@testable import MOSSCaptureCore
import XCTest

final class CaptureControllerTests: XCTestCase {
    func testStartStatusStopPublishesIndependentFakeLaneFrames() throws {
        let systemFrame = CaptureFrame(
            lane: .system,
            sequence: 0,
            sampleRate: 16_000,
            sampleCount: 2,
            captureTimestampNS: 10,
            deviceEpoch: 1,
            silent: false,
            discontinuity: false,
            pcm16: Data([1, 0, 2, 0])
        )
        let microphoneFrame = CaptureFrame(
            lane: .microphone,
            sequence: 0,
            sampleRate: 16_000,
            sampleCount: 2,
            captureTimestampNS: 12,
            deviceEpoch: 7,
            silent: true,
            discontinuity: false,
            pcm16: Data([0, 0, 0, 0])
        )
        let source = FakeCaptureSourceAdapter(frames: [systemFrame, microphoneFrame])
        let transport = FakeCaptureTransportAdapter()
        let scheduler = FakeCaptureSchedulerAdapter()
        let health = FakeCaptureHealthAdapter()
        let controller = CaptureController(
            source: source,
            transport: transport,
            keyStore: FakeCaptureKeyStoreAdapter(),
            clock: FakeCaptureClockAdapter(ticks: [100]),
            scheduler: scheduler,
            health: health
        )
        let configuration = CaptureConfiguration(
            sessionID: "session-a",
            serverURL: URL(string: "https://127.0.0.1/live")!,
            label: "local"
        )

        let started = try controller.start(configuration: configuration)
        let current = controller.status()
        let stopped = try controller.stop(deadline: Date(timeIntervalSince1970: 1))

        XCTAssertTrue(started.running)
        XCTAssertEqual(started.sessionID, "session-a")
        XCTAssertEqual(started.publishedFrameCount, 2)
        XCTAssertEqual(current.lanes.map(\.lane), [.system, .microphone])
        XCTAssertEqual(current.lanes.first { $0.lane == .system }?.deviceEpoch, 1)
        XCTAssertEqual(current.lanes.first { $0.lane == .microphone }?.deviceEpoch, 7)
        // Per lane, because the lanes publish concurrently: within a lane the order is the
        // contract, across lanes it is a race the server does not care about.
        XCTAssertEqual(transport.publishedFrames(lane: .system).map(\.sequence), [0])
        XCTAssertEqual(transport.publishedFrames(lane: .microphone).map(\.sequence), [0])
        XCTAssertEqual(transport.sessionIDs, ["session-a", "session-a"])
        XCTAssertEqual(health.emissions.count, 1)
        XCTAssertEqual(health.emissions.first?.configuration, configuration)
        XCTAssertEqual(health.emissions.first?.sentMonotonicNS, 100)
        XCTAssertEqual(scheduler.labels, ["moss.capture.pump"])
        XCTAssertFalse(stopped.running)
        XCTAssertNil(controller.status().sessionID)
    }

    func testContinuousPumpPublishesAcrossTicks() throws {
        let firstSystem = CaptureFrame(
            lane: CaptureLane.system,
            sequence: 0,
            sampleRate: 16_000,
            sampleCount: 1,
            captureTimestampNS: 10,
            deviceEpoch: 1,
            silent: false,
            discontinuity: false,
            pcm16: Data([1, 0])
        )
        let firstMicrophone = CaptureFrame(
            lane: CaptureLane.microphone,
            sequence: 0,
            sampleRate: 16_000,
            sampleCount: 1,
            captureTimestampNS: 20,
            deviceEpoch: 7,
            silent: true,
            discontinuity: false,
            pcm16: Data([0, 0])
        )
        let secondSystem = CaptureFrame(
            lane: CaptureLane.system,
            sequence: 1,
            sampleRate: 16_000,
            sampleCount: 1,
            captureTimestampNS: 30,
            deviceEpoch: 1,
            silent: false,
            discontinuity: false,
            pcm16: Data([2, 0])
        )
        let secondMicrophone = CaptureFrame(
            lane: CaptureLane.microphone,
            sequence: 1,
            sampleRate: 16_000,
            sampleCount: 1,
            captureTimestampNS: 40,
            deviceEpoch: 7,
            silent: false,
            discontinuity: true,
            pcm16: Data([3, 0])
        )
        let source = FakeCaptureSourceAdapter(frames: [firstSystem])
        let transport = FakeCaptureTransportAdapter()
        let scheduler = FakeCaptureSchedulerAdapter()
        let health = FakeCaptureHealthAdapter()
        let controller = CaptureController(
            source: source,
            transport: transport,
            keyStore: FakeCaptureKeyStoreAdapter(),
            clock: FakeCaptureClockAdapter(ticks: [100, 200, 300, 400]),
            scheduler: scheduler,
            health: health
        )
        let configuration = CaptureConfiguration(
            sessionID: "session-a",
            serverURL: URL(string: "https://127.0.0.1/live")!
        )

        try controller.start(configuration: configuration)
        source.enqueue(frames: [firstMicrophone, secondSystem])
        scheduler.runScheduledOperation()
        source.enqueue(frames: [secondMicrophone])
        scheduler.runScheduledOperation()
        scheduler.runScheduledOperation()

        // Each lane's own stream is ordered and complete; the interleaving between the two lanes is
        // deliberately not asserted, because the lanes publish on separate threads.
        XCTAssertEqual(transport.publishedFrames(lane: .system).map(\.sequence), [0, 1])
        XCTAssertEqual(
            transport.publishedFrames(lane: .system).map(\.captureTimestampNS),
            [10, 30]
        )
        XCTAssertEqual(transport.publishedFrames(lane: .microphone).map(\.sequence), [0, 1])
        XCTAssertEqual(
            transport.publishedFrames(lane: .microphone).map(\.captureTimestampNS),
            [20, 40]
        )
        XCTAssertEqual(transport.publishedFrames.count, 4)
        XCTAssertEqual(health.emissions.map(\.sentMonotonicNS), [100, 200, 300, 400])
        XCTAssertEqual(health.emissions.map(\.status.publishedFrameCount), [1, 3, 4, 4])
        XCTAssertEqual(controller.status().publishedFrameCount, 4)
    }

    func testPumpFailureIsTypedAndLaterTicksContinue() throws {
        let scheduler = FakeCaptureSchedulerAdapter()
        let health = FailOnceScheduledHealthAdapter()
        let controller = CaptureController(
            source: FakeCaptureSourceAdapter(frames: []),
            transport: FakeCaptureTransportAdapter(),
            keyStore: FakeCaptureKeyStoreAdapter(),
            clock: FakeCaptureClockAdapter(ticks: [100, 200, 300]),
            scheduler: scheduler,
            health: health
        )
        try controller.start(
            configuration: CaptureConfiguration(
                sessionID: "session-a",
                serverURL: URL(string: "https://127.0.0.1/live")!
            )
        )

        scheduler.runScheduledOperation()
        let failed = controller.status()
        scheduler.runScheduledOperation()
        let recovered = controller.status()

        XCTAssertTrue(failed.running)
        XCTAssertEqual(failed.pumpFailure, .transportUnavailable)
        XCTAssertEqual(failed.lastHealthSequence, 2)
        XCTAssertEqual(failed.lanes.map(\.state), ["capturing", "capturing"], "transportUnavailable is degraded/recovering policy, not lane failure")
        XCTAssertEqual(
            ControlChannelResponse(status: failed).pumpFailure,
            .transportUnavailable
        )
        XCTAssertTrue(recovered.running)
        XCTAssertNil(recovered.pumpFailure)
        XCTAssertEqual(recovered.lastHealthSequence, 3)
        XCTAssertEqual(health.attemptCount, 3)
    }

    func testControlChannelStatusCarriesEveryLanesStateAndTypedFailureCode() throws {
        let failed = CaptureStatus(
            running: true,
            sessionID: "session-a",
            lanes: [
                CaptureLaneStatus(
                    lane: .system,
                    sequence: 4,
                    deviceEpoch: 2,
                    state: "failed",
                    droppedFrames: 1,
                    discontinuities: 2,
                    failureCode: "macos_permission_denied"
                ),
                CaptureLaneStatus(lane: .microphone, sequence: 6, deviceEpoch: 8, state: "capturing"),
            ],
            publishedFrameCount: 10,
            lastHealthSequence: 5
        )

        let response = ControlChannelResponse(status: failed)

        XCTAssertEqual(
            response.lanes,
            [
                ControlChannelLaneStatus(
                    lane: "system",
                    state: "failed",
                    failureCode: "macos_permission_denied"
                ),
                ControlChannelLaneStatus(lane: "microphone", state: "capturing"),
            ],
            "the code that ends a meeting has to reach the operator's status, not only the server"
        )

        let encoded = try XCTUnwrap(
            String(data: JSONEncoder().encode(response), encoding: .utf8)
        )
        for forbidden in ["pcm", "token", "secret", "cause"] {
            XCTAssertFalse(
                encoded.lowercased().contains(forbidden),
                "lane reporting carries states and typed codes only, never \(forbidden)"
            )
        }
    }

    func testControlChannelStatusNamesALaneTheSourceNeverReported() throws {
        // A lane the source omits is exactly the case that made the failure unreadable: absent and
        // failed look the same to an operator. Both surfaces name every lane in the contract.
        let silent = CaptureStatus(
            running: true,
            sessionID: "session-a",
            lanes: [
                CaptureLaneStatus(lane: .microphone, sequence: 6, deviceEpoch: 8, state: "capturing"),
            ],
            publishedFrameCount: 0,
            lastHealthSequence: 1
        )

        XCTAssertEqual(
            ControlChannelResponse(status: silent).lanes,
            [
                ControlChannelLaneStatus(lane: "system", state: "stopped"),
                ControlChannelLaneStatus(lane: "microphone", state: "capturing"),
            ]
        )
        XCTAssertEqual(
            silent.reportedLanes().map(\.lane),
            CaptureLane.allCases,
            "the heartbeat and the control channel project the same lane set, in the same order"
        )
    }

    func testAReleasedSessionIsReportedGoneInsteadOfMerelyUnreachable() throws {
        // The attended session's exact shape: the first heartbeat is accepted, the server releases
        // the session, and every request after that is refused. Before this, `status` answered
        // `running: true` with a transport failure — the same answer a pulled network cable gives.
        let scheduler = FakeCaptureSchedulerAdapter()
        let health = ReleasedSessionHealthAdapter(refusedStatusCode: 403)
        let controller = CaptureController(
            source: FakeCaptureSourceAdapter(frames: []),
            transport: FakeCaptureTransportAdapter(),
            keyStore: FakeCaptureKeyStoreAdapter(),
            clock: FakeCaptureClockAdapter(ticks: [100, 200, 300]),
            scheduler: scheduler,
            health: health
        )
        try controller.start(
            configuration: CaptureConfiguration(
                sessionID: "session-a",
                serverURL: URL(string: "https://127.0.0.1/live")!
            )
        )
        XCTAssertNil(controller.status().sessionRefusal, "an accepted heartbeat refuses nothing")

        scheduler.runScheduledOperation()
        let refused = controller.status()

        XCTAssertTrue(refused.running, "the microphones really are still open; that is not the lie")
        XCTAssertEqual(
            refused.sessionRefusal,
            .sessionDisowned,
            "a session the server has released has to be visible as gone, not as unreachable"
        )
        XCTAssertEqual(
            refused.pumpFailure,
            .transportUnavailable,
            "the pump answer is still true — it is just not an answer to whether the session exists"
        )
        let response = ControlChannelResponse(status: refused)
        XCTAssertEqual(response.sessionRefusal, .sessionDisowned)
        let encoded = try XCTUnwrap(String(data: JSONEncoder().encode(response), encoding: .utf8))
        XCTAssertTrue(
            encoded.contains("sessionDisowned"),
            "`mtd-capture status` encodes whatever the app answers, so the word has to be in it"
        )
    }

    func testASessionTheServerRefusedStaysRefusedWhenALaterRequestSucceeds() throws {
        // A pump failure clears on the next good tick because it describes right now. A refusal
        // describes one session id, and the server's answer about that id is final — a release is
        // one-way — so it must not be quietly erased by whatever happens next.
        let scheduler = FakeCaptureSchedulerAdapter()
        let health = ReleasedSessionHealthAdapter(refusedStatusCode: 403, refusedAttempts: [2])
        let controller = CaptureController(
            source: FakeCaptureSourceAdapter(frames: []),
            transport: FakeCaptureTransportAdapter(),
            keyStore: FakeCaptureKeyStoreAdapter(),
            clock: FakeCaptureClockAdapter(ticks: [100, 200, 300]),
            scheduler: scheduler,
            health: health
        )
        try controller.start(
            configuration: CaptureConfiguration(
                sessionID: "session-a",
                serverURL: URL(string: "https://127.0.0.1/live")!
            )
        )

        scheduler.runScheduledOperation()
        scheduler.runScheduledOperation()
        let recovered = controller.status()

        XCTAssertNil(recovered.pumpFailure, "the transport is working again and says so")
        XCTAssertEqual(recovered.sessionRefusal, .sessionDisowned)

        // A new session is a new question, so the previous session's verdict does not carry over.
        let stopped = try controller.stop(deadline: Date(timeIntervalSince1970: 1))
        XCTAssertEqual(stopped.sessionRefusal, .sessionDisowned, "the stopped meeting was refused")
        try controller.start(
            configuration: CaptureConfiguration(
                sessionID: "session-b",
                serverURL: URL(string: "https://127.0.0.1/live")!
            )
        )
        XCTAssertNil(controller.status().sessionRefusal)
    }

    func testStopReportsASessionTheServerRefusedWhileDrainingTheLastFrames() throws {
        // The final drain's failure is deliberately swallowed — the audio stays queued either way —
        // but "the server would not take it because the session was already gone" is the one thing
        // in it an operator needs, and a clean-looking stop is exactly the report that hides it.
        let tail = laneFrame(.microphone, sampleCount: 341, captureTimestampNS: 1_500_000_000)
        let transport = ProgrammableCaptureTransport()
        transport.failure = { _, _ in CaptureHTTPTransportError.nonSuccessStatus(404) }
        let controller = CaptureController(
            source: TerminalTailCaptureSource(tail: [tail]),
            transport: transport,
            keyStore: FakeCaptureKeyStoreAdapter(),
            clock: FakeCaptureClockAdapter(ticks: [100, 200]),
            scheduler: FakeCaptureSchedulerAdapter(),
            health: FakeCaptureHealthAdapter()
        )
        try controller.start(
            configuration: CaptureConfiguration(
                sessionID: "session-a",
                serverURL: URL(string: "https://127.0.0.1/live")!
            )
        )

        let stopped = try controller.stop(deadline: Date(timeIntervalSince1970: 1))

        XCTAssertEqual(stopped.sessionRefusal, .sessionUnknown)
        XCTAssertEqual(
            stopped.outbox.retainedFrames,
            1,
            "the refusal is a report, not a licence to drop the audio"
        )
        XCTAssertEqual(stopped.publishedFrameCount, 0)
    }

    func testSessionRefusalNamesOnlyTheAnswersThatMeanTheSessionIsGone() throws {
        XCTAssertEqual(CaptureSessionRefusal(statusCode: 401), .credentialRejected)
        XCTAssertEqual(CaptureSessionRefusal(statusCode: 403), .sessionDisowned)
        XCTAssertEqual(CaptureSessionRefusal(statusCode: 404), .sessionUnknown)
        XCTAssertEqual(CaptureSessionRefusal(statusCode: 410), .sessionGone)
        XCTAssertEqual(
            CaptureSessionRefusal(error: CaptureHTTPTransportError.nonSuccessStatus(403)),
            .sessionDisowned
        )
        XCTAssertNil(
            CaptureSessionRefusal(statusCode: 409),
            "409 is this wire's answer both for a closed session and for an out-of-sequence frame, "
                + "so it cannot tell an operator which one happened"
        )
        for silent: Error in [
            CaptureHTTPTransportError.nonSuccessStatus(200),
            CaptureHTTPTransportError.nonSuccessStatus(400),
            CaptureHTTPTransportError.nonSuccessStatus(429),
            CaptureHTTPTransportError.nonSuccessStatus(503),
            CaptureHTTPTransportError.nonSuccessStatus(0),
            CaptureHTTPTransportError.missingCaptureBearer,
            CaptureHTTPTransportError.missingCertificatePin,
            URLError(.networkConnectionLost),
            URLError(.secureConnectionFailed),
            CaptureSecurityError.pinMismatch,
        ] {
            XCTAssertNil(CaptureSessionRefusal(error: silent), String(describing: silent))
        }

        // The two policies read the same status codes and must never both claim one: an answer a
        // retry can fix is by definition not the server saying the session is gone for good.
        for statusCode in 0..<600 {
            let refusal = CaptureSessionRefusal(statusCode: statusCode)
            let retry = CaptureFrameRetryPolicy.retryReason(forStatusCode: statusCode)
            XCTAssertFalse(
                refusal != nil && retry != nil,
                "status \(statusCode) cannot be both retryable (\(String(describing: retry))) "
                    + "and a final refusal (\(String(describing: refusal)))"
            )
        }
    }

    func testPumpMapsCaptureHTTPTransportErrorToTransportUnavailableAndRecovers() throws {
        let scheduler = FakeCaptureSchedulerAdapter()
        let health = FailOnceHTTPTransportHealthAdapter()
        let controller = CaptureController(
            source: FakeCaptureSourceAdapter(frames: []),
            transport: FakeCaptureTransportAdapter(),
            keyStore: FakeCaptureKeyStoreAdapter(),
            clock: FakeCaptureClockAdapter(ticks: [100, 200, 300]),
            scheduler: scheduler,
            health: health
        )
        try controller.start(
            configuration: CaptureConfiguration(
                sessionID: "session-a",
                serverURL: URL(string: "https://127.0.0.1/live")!
            )
        )

        scheduler.runScheduledOperation()
        let failed = controller.status()
        scheduler.runScheduledOperation()
        let recovered = controller.status()

        XCTAssertEqual(failed.pumpFailure, .transportUnavailable)
        XCTAssertNotEqual(failed.pumpFailure, .deviceUnavailable)
        XCTAssertNil(recovered.pumpFailure)
        XCTAssertEqual(recovered.lastHealthSequence, 3)
        XCTAssertEqual(health.attemptCount, 3)
    }

    func testOutboxRetainsEveryFrameAcrossAFiveSecondOutageAndDeliversEachExactlyOnce() throws {
        // Ten 0.5 s pump ticks is the 5 s interruption the meeting has to survive.
        let outageTicks = 10
        let source = FakeCaptureSourceAdapter(frames: [])
        let transport = ProgrammableCaptureTransport()
        let scheduler = FakeCaptureSchedulerAdapter()
        let controller = CaptureController(
            source: source,
            transport: transport,
            keyStore: FakeCaptureKeyStoreAdapter(),
            clock: FakeCaptureClockAdapter(),
            scheduler: scheduler,
            health: FakeCaptureHealthAdapter()
        )
        try controller.start(
            configuration: CaptureConfiguration(
                sessionID: "session-a",
                serverURL: URL(string: "https://127.0.0.1/live")!
            )
        )

        transport.failure = { _, _ in URLError(.networkConnectionLost) }
        for tick in 0..<outageTicks {
            source.enqueue(
                frames: [
                    laneFrame(.system, captureTimestampNS: UInt64(1_000 + tick)),
                    laneFrame(.microphone, captureTimestampNS: UInt64(2_000 + tick)),
                ]
            )
            scheduler.runScheduledOperation()
        }
        let interrupted = controller.status()
        let acceptedDuringOutage = transport.accepted.count

        transport.failure = nil
        scheduler.runScheduledOperation()
        let recovered = controller.status()

        XCTAssertEqual(interrupted.outbox.retainedFrames, 2 * outageTicks)
        XCTAssertEqual(interrupted.outbox.retainedSecondsByLane, [.system: 5, .microphone: 5])
        XCTAssertEqual(interrupted.outbox.refusedFrames, 0)
        XCTAssertNil(interrupted.outbox.degradation, "5 s of audio fits inside the 15 s window")
        XCTAssertEqual(interrupted.pumpFailure, .transportUnavailable)
        XCTAssertEqual(interrupted.publishedFrameCount, 0)
        XCTAssertEqual(acceptedDuringOutage, 0, "nothing reached the server during the outage")

        XCTAssertEqual(recovered.publishedFrameCount, 2 * outageTicks)
        XCTAssertEqual(recovered.outbox.retainedFrames, 0)
        XCTAssertNil(recovered.pumpFailure)
        XCTAssertEqual(
            transport.accepted.filter { $0.lane == .system }.map(\.sequence),
            Array(0..<UInt64(outageTicks)),
            "the whole interrupted lane arrives, in order"
        )
        XCTAssertEqual(
            transport.accepted.filter { $0.lane == .microphone }.map(\.sequence),
            Array(0..<UInt64(outageTicks))
        )
        XCTAssertEqual(
            transport.accepted.filter { $0.lane == .system }.map(\.captureTimestampNS),
            (0..<outageTicks).map { UInt64(1_000 + $0) },
            "retained frames keep their captured audio, not a resynthesized substitute"
        )
        XCTAssertEqual(
            Set(transport.accepted.map { "\($0.lane.rawValue):\($0.sequence)" }).count,
            2 * outageTicks,
            "no identity is accepted twice"
        )
        XCTAssertGreaterThan(
            transport.attempts.count,
            transport.accepted.count,
            "the outage was retried rather than skipped"
        )
    }

    func testAmbiguousAnswerAndDuplicateRetryReuseTheOriginalLaneSequenceIdentity() throws {
        let source = FakeCaptureSourceAdapter(
            frames: [laneFrame(.microphone, captureTimestampNS: 4_242)]
        )
        let transport = ProgrammableCaptureTransport()
        // The server admitted the frame and then the answer was lost on the way back. Only the
        // reply is missing, so the retry has to be the identical frame: the server acknowledges
        // `(lane, sequence)` idempotently and replays the original acknowledgement.
        transport.failure = { _, attempt in attempt == 1 ? URLError(.timedOut) : nil }
        let scheduler = FakeCaptureSchedulerAdapter()
        let controller = CaptureController(
            source: source,
            transport: transport,
            keyStore: FakeCaptureKeyStoreAdapter(),
            clock: FakeCaptureClockAdapter(),
            scheduler: scheduler,
            health: FakeCaptureHealthAdapter()
        )

        let started = try controller.start(
            configuration: CaptureConfiguration(
                sessionID: "session-a",
                serverURL: URL(string: "https://127.0.0.1/live")!
            )
        )
        let ambiguous = controller.status()
        scheduler.runScheduledOperation()
        let resolved = controller.status()

        XCTAssertEqual(
            started.pumpFailure,
            .transportUnavailable,
            "an unanswered publish is a degraded start, not a failed one"
        )
        XCTAssertEqual(scheduler.labels, ["moss.capture.pump"], "the pump still has to run")
        XCTAssertEqual(ambiguous.outbox.retainedFrames, 1, "an unanswered frame is still queued")
        XCTAssertEqual(ambiguous.publishedFrameCount, 0)
        XCTAssertEqual(transport.attempts.count, 2)
        XCTAssertEqual(transport.attempts.map(\.lane), [.microphone, .microphone])
        XCTAssertEqual(transport.attempts.map(\.sequence), [0, 0])
        XCTAssertEqual(transport.attempts.map(\.captureTimestampNS), [4_242, 4_242])
        XCTAssertEqual(transport.attempts[0].pcm16, transport.attempts[1].pcm16)
        XCTAssertEqual(transport.attempts[0].discontinuity, transport.attempts[1].discontinuity)
        XCTAssertEqual(resolved.publishedFrameCount, 1, "an idempotent replay is not a second frame")
        XCTAssertEqual(resolved.outbox.retainedFrames, 0)
        XCTAssertEqual(resolved.outbox.refusedFrames, 0)
    }

    func testStartUnwindsOnlyWhenNoRetryCouldEverPublish() throws {
        let source = FakeCaptureSourceAdapter(
            frames: [laneFrame(.system, captureTimestampNS: 1)]
        )
        let transport = ProgrammableCaptureTransport()
        transport.failure = { _, _ in CaptureHTTPTransportError.missingCaptureBearer }
        let scheduler = FakeCaptureSchedulerAdapter()
        let controller = CaptureController(
            source: source,
            transport: transport,
            keyStore: FakeCaptureKeyStoreAdapter(),
            clock: FakeCaptureClockAdapter(),
            scheduler: scheduler,
            health: FakeCaptureHealthAdapter()
        )
        let configuration = CaptureConfiguration(
            sessionID: "session-a",
            serverURL: URL(string: "https://127.0.0.1/live")!
        )

        XCTAssertThrowsError(try controller.start(configuration: configuration)) { error in
            XCTAssertEqual(error as? CaptureHTTPTransportError, .missingCaptureBearer)
        }
        let unwound = controller.status()

        XCTAssertFalse(unwound.running, "an unpublishable start leaves nothing running")
        XCTAssertEqual(unwound.lanes.map(\.state), ["stopped", "stopped"])
        XCTAssertTrue(scheduler.labels.isEmpty, "no pump is left behind")
        XCTAssertNoThrow(
            try controller.start(configuration: configuration),
            "the failed start is not remembered as a running capture"
        )
    }

    func testAThrowingPublishStillEmitsTheHeartbeatThatHoldsTheServerLease() throws {
        // F3's death in one node. One lane's frames are refused for the rest of the meeting — the
        // server answers `409 v2 system lane is failed.` and never stops — so the tick's publish
        // throws, and the throw used to jump over `emitHealth`. The heartbeat stopped permanently,
        // the 30 s helper lease expired, and the server correctly ended a meeting whose other lane
        // was still healthy and whose heartbeats it would still have accepted.
        let source = FakeCaptureSourceAdapter(frames: [])
        let transport = ProgrammableCaptureTransport()
        transport.failure = { frame, _ in
            frame.lane == .system ? CaptureHTTPTransportError.nonSuccessStatus(409) : nil
        }
        let scheduler = FakeCaptureSchedulerAdapter()
        let health = FakeCaptureHealthAdapter()
        let controller = CaptureController(
            source: source,
            transport: transport,
            keyStore: FakeCaptureKeyStoreAdapter(),
            clock: FakeCaptureClockAdapter(ticks: [100, 200, 300, 400]),
            scheduler: scheduler,
            health: health
        )
        try controller.start(
            configuration: CaptureConfiguration(
                sessionID: "session-a",
                serverURL: URL(string: "https://127.0.0.1/live")!
            )
        )

        for tick in 0..<3 {
            source.enqueue(frames: [
                laneFrame(.system, captureTimestampNS: UInt64(tick) * 2 + 1),
                laneFrame(.microphone, captureTimestampNS: UInt64(tick) * 2 + 2),
            ])
            scheduler.runScheduledOperation()
        }
        let refused = controller.status()

        XCTAssertEqual(
            health.emissions.count,
            4,
            "one heartbeat at start and one per tick: a refused lane must not silence the client"
        )
        XCTAssertEqual(refused.lastHealthSequence, 4)
        XCTAssertTrue(refused.running)
        XCTAssertEqual(
            transport.accepted.map(\.lane),
            [.microphone, .microphone, .microphone],
            "the peer lane keeps publishing — a fault on one lane is not a fault on the meeting"
        )
        XCTAssertEqual(refused.pumpFailure, .transportUnavailable)
        XCTAssertNil(
            refused.sessionRefusal,
            "409 says nothing about whether the session exists, and the heartbeats prove it does"
        )
        XCTAssertEqual(
            refused.outbox.retainedFrames,
            3,
            "the refused lane's audio stays queued; the heartbeat is not bought with dropped audio"
        )
    }

    func testAStartHeartbeatTheServerRefusesUnwindsInsteadOfLeavingTheLanesHot() throws {
        // K5d's wedge. A session the server had already released answers the *start*-time heartbeat
        // 403, and that throw escaped past both the unwind and `scheduler.schedule`: both lanes
        // stayed hot with nothing draining them, `running` stayed true, no refusal was recorded, and
        // `alreadyRunning` refused every later start until the app was killed. The starved lanes
        // then overran — 14005 dropped frames on `system` — and poisoned the next meeting.
        let scheduler = FakeCaptureSchedulerAdapter()
        let health = ReleasedSessionHealthAdapter(refusedStatusCode: 403, refusedAttempts: [1])
        let controller = CaptureController(
            source: FakeCaptureSourceAdapter(frames: []),
            transport: FakeCaptureTransportAdapter(),
            keyStore: FakeCaptureKeyStoreAdapter(),
            clock: FakeCaptureClockAdapter(ticks: [100, 200]),
            scheduler: scheduler,
            health: health
        )
        let configuration = CaptureConfiguration(
            sessionID: "session-a",
            serverURL: URL(string: "https://127.0.0.1/live")!
        )

        XCTAssertThrowsError(try controller.start(configuration: configuration)) { error in
            XCTAssertEqual(error as? CaptureHTTPTransportError, .nonSuccessStatus(403))
        }
        let unwound = controller.status()

        XCTAssertFalse(unwound.running, "a start whose session the server refuses runs nothing")
        XCTAssertEqual(unwound.lanes.map(\.state), ["stopped", "stopped"], "no lane is left hot")
        XCTAssertTrue(scheduler.labels.isEmpty, "no pump is left behind")
        XCTAssertEqual(
            unwound.sessionRefusal,
            .sessionDisowned,
            "the start path is the third caller that has to record the server's verdict"
        )
        XCTAssertNoThrow(
            try controller.start(
                configuration: CaptureConfiguration(
                    sessionID: "session-b",
                    serverURL: URL(string: "https://127.0.0.1/live")!
                )
            ),
            "a refused start must not block the next one with alreadyRunning"
        )
        XCTAssertNil(controller.status().sessionRefusal, "a new session id is a new question")
    }

    func testATransientStartHeartbeatFailureIsADegradedStartWithAPumpRunning() throws {
        // The publish at start already draws this line — a transient answer is a degraded start, an
        // answer no retry can change is an unwind. The heartbeat is the same kind of report, so it
        // gets the same rule: a 503 keeps the meeting and the pump's next heartbeat clears it.
        // (The adapter's status code is the test's choice, not a claim about the session.)
        let scheduler = FakeCaptureSchedulerAdapter()
        let health = ReleasedSessionHealthAdapter(refusedStatusCode: 503, refusedAttempts: [1])
        let controller = CaptureController(
            source: FakeCaptureSourceAdapter(frames: []),
            transport: FakeCaptureTransportAdapter(),
            keyStore: FakeCaptureKeyStoreAdapter(),
            clock: FakeCaptureClockAdapter(ticks: [100, 200]),
            scheduler: scheduler,
            health: health
        )

        let started = try controller.start(
            configuration: CaptureConfiguration(
                sessionID: "session-a",
                serverURL: URL(string: "https://127.0.0.1/live")!
            )
        )

        XCTAssertTrue(started.running, "a transient answer at start is a degraded start")
        XCTAssertEqual(started.pumpFailure, .transportUnavailable)
        XCTAssertNil(
            started.sessionRefusal,
            "5xx is the server talking about itself, not about whether this session exists"
        )
        XCTAssertEqual(started.lanes.map(\.state), ["capturing", "capturing"])
        XCTAssertEqual(
            scheduler.labels,
            ["moss.capture.pump"],
            "the pump is what carries the next heartbeat, so it has to exist"
        )

        scheduler.runScheduledOperation()
        let recovered = controller.status()

        XCTAssertNil(recovered.pumpFailure, "the next heartbeat was accepted and says so")
        XCTAssertEqual(recovered.lastHealthSequence, 2)
        XCTAssertEqual(health.attemptCount, 2)
    }

    func testTypedRetryPolicySeparatesTransientAnswersFromUnauthorizedOnesAndNeitherLosesAudio() throws {
        XCTAssertEqual(
            CaptureFrameRetryPolicy.retryReason(for: CaptureHTTPTransportError.nonSuccessStatus(429)),
            .backpressure
        )
        XCTAssertEqual(
            CaptureFrameRetryPolicy.retryReason(for: CaptureHTTPTransportError.nonSuccessStatus(503)),
            .serverUnavailable
        )
        XCTAssertEqual(
            CaptureFrameRetryPolicy.retryReason(for: CaptureHTTPTransportError.nonSuccessStatus(500)),
            .serverUnavailable
        )
        XCTAssertEqual(
            CaptureFrameRetryPolicy.retryReason(for: CaptureHTTPTransportError.nonSuccessStatus(408)),
            .ambiguous
        )
        XCTAssertEqual(
            CaptureFrameRetryPolicy.retryReason(for: CaptureHTTPTransportError.nonSuccessStatus(0)),
            .ambiguous
        )
        XCTAssertEqual(CaptureFrameRetryPolicy.retryReason(for: URLError(.timedOut)), .ambiguous)
        XCTAssertEqual(
            CaptureFrameRetryPolicy.retryReason(for: URLError(.cannotConnectToHost)),
            .ambiguous
        )
        for unretryable: Error in [
            CaptureHTTPTransportError.nonSuccessStatus(401),
            CaptureHTTPTransportError.nonSuccessStatus(403),
            CaptureHTTPTransportError.nonSuccessStatus(404),
            CaptureHTTPTransportError.nonSuccessStatus(409),
            CaptureHTTPTransportError.missingCaptureBearer,
            CaptureHTTPTransportError.missingCertificatePin,
            URLError(.secureConnectionFailed),
            URLError(.cancelled),
            CaptureSecurityError.pinMismatch,
        ] {
            XCTAssertNil(
                CaptureFrameRetryPolicy.retryReason(for: unretryable),
                String(describing: unretryable)
            )
        }

        let answers: [Error?] = [
            CaptureHTTPTransportError.nonSuccessStatus(429),
            CaptureHTTPTransportError.nonSuccessStatus(503),
            CaptureHTTPTransportError.nonSuccessStatus(401),
            nil,
        ]
        let source = FakeCaptureSourceAdapter(frames: [])
        let transport = ProgrammableCaptureTransport()
        let scheduler = FakeCaptureSchedulerAdapter()
        let controller = CaptureController(
            source: source,
            transport: transport,
            keyStore: FakeCaptureKeyStoreAdapter(),
            clock: FakeCaptureClockAdapter(),
            scheduler: scheduler,
            health: FakeCaptureHealthAdapter()
        )
        try controller.start(
            configuration: CaptureConfiguration(
                sessionID: "session-a",
                serverURL: URL(string: "https://127.0.0.1/live")!
            )
        )

        var depthAfterEachAnswer: [Int] = []
        for (index, answer) in answers.enumerated() {
            transport.failure = { _, _ in answer }
            source.enqueue(frames: [laneFrame(.system, captureTimestampNS: UInt64(index))])
            scheduler.runScheduledOperation()
            depthAfterEachAnswer.append(controller.status().outbox.retainedFrames)
        }
        let final = controller.status()

        XCTAssertEqual(
            depthAfterEachAnswer,
            [1, 2, 3, 0],
            "429, 5xx and an unauthorized answer all keep the audio queued; only an ack releases it"
        )
        XCTAssertEqual(transport.accepted.map(\.sequence), [0, 1, 2, 3])
        XCTAssertEqual(
            transport.accepted.map(\.captureTimestampNS),
            [0, 1, 2, 3],
            "the backlog and the tick's own audio both arrive, in capture order"
        )
        XCTAssertEqual(final.publishedFrameCount, 4)
        XCTAssertEqual(final.outbox.refusedFrames, 0)
        XCTAssertNil(final.outbox.degradation)
        XCTAssertNil(final.pumpFailure)
    }

    func testOutboxOverflowKeepsSequencesGaplessAndReportsATypedDegradedState() throws {
        // The default window is the contract: 15 s per lane, which is thirty 0.5 s frames.
        let admittedFrames = 30
        let refusedFrames = 2
        let source = FakeCaptureSourceAdapter(frames: [])
        let transport = ProgrammableCaptureTransport()
        transport.failure = { _, _ in URLError(.notConnectedToInternet) }
        let scheduler = FakeCaptureSchedulerAdapter()
        let controller = CaptureController(
            source: source,
            transport: transport,
            keyStore: FakeCaptureKeyStoreAdapter(),
            clock: FakeCaptureClockAdapter(),
            scheduler: scheduler,
            health: FakeCaptureHealthAdapter()
        )
        try controller.start(
            configuration: CaptureConfiguration(
                sessionID: "session-a",
                serverURL: URL(string: "https://127.0.0.1/live")!
            )
        )

        for index in 0..<(admittedFrames + refusedFrames) {
            source.enqueue(frames: [laneFrame(.system, captureTimestampNS: UInt64(index))])
        }
        source.enqueue(frames: [laneFrame(.microphone, captureTimestampNS: 9_000)])
        scheduler.runScheduledOperation()
        let overflowed = controller.status()

        transport.failure = nil
        scheduler.runScheduledOperation()
        source.enqueue(frames: [laneFrame(.system, captureTimestampNS: 8_888)])
        scheduler.runScheduledOperation()
        let drained = controller.status()

        XCTAssertEqual(overflowed.outbox.retainedFrames, admittedFrames + 1)
        XCTAssertEqual(
            overflowed.outbox.retainedSecondsByLane,
            [.system: 15, .microphone: 0.5],
            "the full window is held and the other lane is untouched by it"
        )
        XCTAssertEqual(overflowed.outbox.refusedFrames, UInt64(refusedFrames))
        XCTAssertEqual(overflowed.outbox.degradation, .overflowedLaneRetention)
        XCTAssertEqual(
            ControlChannelResponse(status: overflowed).outboxDegradation,
            .overflowedLaneRetention,
            "the operator is told, in typed form, that captured audio was lost"
        )
        XCTAssertEqual(
            ControlChannelResponse(status: overflowed).outboxRetainedFrames,
            admittedFrames + 1
        )

        let systemAccepted = transport.accepted.filter { $0.lane == .system }
        XCTAssertEqual(
            systemAccepted.map(\.sequence),
            Array(0..<UInt64(admittedFrames + 1)),
            "a refused frame burns no sequence number, so the lane stays admissible"
        )
        XCTAssertEqual(
            systemAccepted.map(\.captureTimestampNS),
            (0..<admittedFrames).map(UInt64.init) + [8_888]
        )
        XCTAssertEqual(
            systemAccepted.map(\.discontinuity),
            Array(repeating: false, count: admittedFrames) + [true],
            "the first frame admitted after the loss reports the gap in the audio"
        )
        XCTAssertEqual(drained.outbox.retainedFrames, 0)
        XCTAssertEqual(
            drained.outbox.degradation,
            .overflowedLaneRetention,
            "a run that lost audio never reports clean afterwards"
        )
        XCTAssertNil(drained.pumpFailure)
    }

    func testOneStalledLaneNeitherBlocksTheOtherLaneNorReattemptsItsWholeBacklog() throws {
        let source = FakeCaptureSourceAdapter(frames: [])
        let transport = ProgrammableCaptureTransport()
        transport.failure = { frame, _ in
            frame.lane == .system ? CaptureHTTPTransportError.nonSuccessStatus(429) : nil
        }
        let scheduler = FakeCaptureSchedulerAdapter()
        let controller = CaptureController(
            source: source,
            transport: transport,
            keyStore: FakeCaptureKeyStoreAdapter(),
            clock: FakeCaptureClockAdapter(),
            scheduler: scheduler,
            health: FakeCaptureHealthAdapter()
        )
        try controller.start(
            configuration: CaptureConfiguration(
                sessionID: "session-a",
                serverURL: URL(string: "https://127.0.0.1/live")!
            )
        )

        for tick in 0..<2 {
            source.enqueue(
                frames: [
                    laneFrame(.system, captureTimestampNS: UInt64(100 + tick)),
                    laneFrame(.microphone, captureTimestampNS: UInt64(200 + tick)),
                ]
            )
            scheduler.runScheduledOperation()
        }
        let stalled = controller.status()

        XCTAssertEqual(transport.accepted.map(\.lane), [.microphone, .microphone])
        XCTAssertEqual(transport.accepted.map(\.sequence), [0, 1])
        XCTAssertEqual(stalled.outbox.retainedFrames, 2, "only the stalled lane is still queued")
        XCTAssertEqual(stalled.outbox.retainedSecondsByLane, [.system: 1, .microphone: 0])
        XCTAssertEqual(
            transport.attempts.filter { $0.lane == .system }.map(\.sequence),
            [0, 0],
            "a stalled lane retries its head once per tick instead of hammering its backlog"
        )
        XCTAssertEqual(stalled.pumpFailure, .transportUnavailable)
    }

    func testOutboxIsTheWireSequenceAuthorityAndReleasesOnlyAcknowledgedAudio() throws {
        let outbox = CaptureFrameOutbox(retainedSecondsPerLane: 1)

        let first = outbox.admit(laneFrame(.system, captureTimestampNS: 1, sequence: 77))
        let second = outbox.admit(laneFrame(.system, captureTimestampNS: 2, sequence: 78))
        let refused = outbox.admit(laneFrame(.system, captureTimestampNS: 3))
        XCTAssertEqual(first?.sequence, 0, "the outbox, not the capture source, owns wire identity")
        XCTAssertEqual(second?.sequence, 1)
        XCTAssertNil(refused)
        XCTAssertEqual(outbox.snapshot().refusedFrames, 1)
        XCTAssertEqual(outbox.snapshot().degradation, .overflowedLaneRetention)
        XCTAssertEqual(outbox.snapshot().retainedSecondsByLane[.system], 1)

        let empty = CaptureFrameOutbox(retainedSecondsPerLane: 1)
        XCTAssertNil(
            empty.admit(laneFrame(.system, sampleCount: 32_000, captureTimestampNS: 4)),
            "a frame larger than the whole window is refused, not admitted unbounded"
        )
        XCTAssertNil(
            outbox.admit(laneFrame(.system, sampleRate: 0, captureTimestampNS: 5)),
            "a frame that cannot be acknowledged must not occupy the window"
        )
        XCTAssertEqual(outbox.snapshot().degradation, .undeliverableFrame)

        outbox.acknowledge(lane: .system, sequence: 0)
        XCTAssertEqual(outbox.retainedFrames().map(\.sequence), [1])
        outbox.acknowledge(lane: .microphone, sequence: 1)
        XCTAssertEqual(
            outbox.retainedFrames().map(\.sequence),
            [1],
            "an acknowledgement releases one lane's identity only"
        )

        let resumed = outbox.admit(laneFrame(.system, captureTimestampNS: 6))
        XCTAssertEqual(resumed?.sequence, 2, "the admitted stream has no gap after the refusals")
        XCTAssertEqual(resumed?.discontinuity, true, "audio was lost before this frame")
        XCTAssertNil(
            outbox.admit(laneFrame(.system, captureTimestampNS: 7)),
            "the window is full again, so this one is refused"
        )

        outbox.reset()
        XCTAssertEqual(outbox.snapshot(), CaptureOutboxSnapshot(retainedSecondsByLane: [.system: 0, .microphone: 0]))
        XCTAssertEqual(outbox.admit(laneFrame(.system, captureTimestampNS: 8))?.sequence, 0)
    }

    func testEachSessionNumbersItsLaneFramesFromZero() throws {
        let source = FakeCaptureSourceAdapter(
            frames: [laneFrame(.system, captureTimestampNS: 1, sequence: 40)]
        )
        let transport = ProgrammableCaptureTransport()
        let controller = CaptureController(
            source: source,
            transport: transport,
            keyStore: FakeCaptureKeyStoreAdapter(),
            clock: FakeCaptureClockAdapter(),
            scheduler: FakeCaptureSchedulerAdapter(),
            health: FakeCaptureHealthAdapter()
        )

        try controller.start(
            configuration: CaptureConfiguration(
                sessionID: "session-a",
                serverURL: URL(string: "https://127.0.0.1/live")!
            )
        )
        try controller.stop(deadline: Date(timeIntervalSince1970: 1))
        source.enqueue(frames: [laneFrame(.system, captureTimestampNS: 2, sequence: 41)])
        try controller.start(
            configuration: CaptureConfiguration(
                sessionID: "session-b",
                serverURL: URL(string: "https://127.0.0.1/live")!
            )
        )

        XCTAssertEqual(transport.accepted.map(\.sequence), [0, 0])
        XCTAssertEqual(transport.accepted.map(\.captureTimestampNS), [1, 2])
        XCTAssertEqual(
            transport.sessionIDs,
            ["session-a", "session-b"],
            "a new server session counts each lane from zero, so the outbox restarts with it"
        )
    }

    func testLanesPublishConcurrentlyWithOneRequestInFlightPerLane() throws {
        let framesPerLane = 4
        let source = FakeCaptureSourceAdapter(frames: [])
        // Every lane's first request is held until every lane has one in flight. A transport that
        // sends the lanes one after another can never satisfy that, so a serial pump fails on the
        // rendezvous deadline instead of passing because it happened to be fast.
        let transport = RendezvousCaptureTransport(expectedLanes: [.system, .microphone])
        let scheduler = FakeCaptureSchedulerAdapter()
        let controller = CaptureController(
            source: source,
            transport: transport,
            keyStore: FakeCaptureKeyStoreAdapter(),
            clock: FakeCaptureClockAdapter(),
            scheduler: scheduler,
            health: FakeCaptureHealthAdapter()
        )
        try controller.start(configuration: laneConfiguration())

        for index in 0..<framesPerLane {
            source.enqueue(
                frames: [
                    laneFrame(.system, captureTimestampNS: UInt64(100 + index)),
                    laneFrame(.microphone, captureTimestampNS: UInt64(200 + index)),
                ]
            )
        }
        scheduler.runScheduledOperation()
        let drained = controller.status()

        XCTAssertFalse(
            transport.rendezvousTimedOut,
            "the lanes never overlapped, so the transport is still draining them one after another"
        )
        XCTAssertEqual(
            transport.maxConcurrentRequests,
            CaptureLane.allCases.count,
            "in-flight work is bounded by the number of lanes, not by how much audio is waiting"
        )
        for lane in CaptureLane.allCases {
            XCTAssertEqual(
                transport.maxConcurrentRequests(lane: lane),
                1,
                "\(lane.rawValue) has to arrive in sequence order, so it can only have one request out"
            )
            XCTAssertEqual(
                transport.published(lane: lane).map(\.sequence),
                Array(0..<UInt64(framesPerLane)),
                "concurrency across lanes never reorders a lane's own stream"
            )
        }
        XCTAssertEqual(drained.publishedFrameCount, CaptureLane.allCases.count * framesPerLane)
        XCTAssertEqual(drained.outbox.retainedFrames, 0)
        XCTAssertNil(drained.pumpFailure)
    }

    func testATickArrivingDuringADrainSkipsInsteadOfReSendingFramesAlreadyInFlight() throws {
        let source = FakeCaptureSourceAdapter(frames: [])
        let transport = GatedCaptureTransport()
        let scheduler = FakeCaptureSchedulerAdapter()
        let health = ConcurrentCaptureHealth()
        let controller = CaptureController(
            source: source,
            transport: transport,
            keyStore: FakeCaptureKeyStoreAdapter(),
            clock: IncrementingCaptureClock(),
            scheduler: scheduler,
            health: health
        )
        try controller.start(configuration: laneConfiguration())
        let healthEmissionsBeforeTheLateTick = health.emissionCount()
        source.enqueue(
            frames: [
                laneFrame(.system, captureTimestampNS: 1),
                laneFrame(.microphone, captureTimestampNS: 2),
            ]
        )

        let tickRunner = FakeScheduledPumpRunner(scheduler: scheduler)
        let drainingTick = DispatchSemaphore(value: 0)
        DispatchQueue.global().async {
            tickRunner.run()
            drainingTick.signal()
        }
        XCTAssertTrue(
            transport.waitUntilInFlight(CaptureLane.allCases.count, timeout: 5),
            "both lanes should be waiting on the transport"
        )

        let lateTick = DispatchSemaphore(value: 0)
        DispatchQueue.global().async {
            tickRunner.run()
            lateTick.signal()
        }

        XCTAssertEqual(
            lateTick.wait(timeout: .now() + 5),
            .success,
            "a tick that finds a pass running skips its turn instead of queueing behind the drain"
        )
        XCTAssertEqual(
            transport.attempts.count,
            CaptureLane.allCases.count,
            "the skipped tick issued no second attempt at identities that are already in flight"
        )
        XCTAssertGreaterThan(
            health.emissionCount(),
            healthEmissionsBeforeTheLateTick,
            "skipping the publish turn must not skip the heartbeat the helper lease depends on"
        )

        transport.release()
        XCTAssertEqual(drainingTick.wait(timeout: .now() + 5), .success)
        let drained = controller.status()

        XCTAssertEqual(transport.published.count, CaptureLane.allCases.count)
        XCTAssertEqual(drained.publishedFrameCount, CaptureLane.allCases.count)
        XCTAssertEqual(drained.outbox.retainedFrames, 0)
    }

    func testStopWaitsForTheRunningPassInsteadOfSkippingTheFinalDrain() throws {
        let tailHandedOver = DispatchSemaphore(value: 0)
        let source = ConcurrentTailCaptureSource(
            tail: [laneFrame(.microphone, captureTimestampNS: 2)],
            onTailHandover: { tailHandedOver.signal() }
        )
        let transport = GatedCaptureTransport()
        let scheduler = FakeCaptureSchedulerAdapter()
        let controller = CaptureController(
            source: source,
            transport: transport,
            keyStore: FakeCaptureKeyStoreAdapter(),
            clock: IncrementingCaptureClock(),
            scheduler: scheduler,
            health: ConcurrentCaptureHealth()
        )
        try controller.start(configuration: laneConfiguration())
        source.enqueue(frames: [laneFrame(.system, captureTimestampNS: 1)])

        let tickRunner = FakeScheduledPumpRunner(scheduler: scheduler)
        let drainingTick = DispatchSemaphore(value: 0)
        DispatchQueue.global().async {
            tickRunner.run()
            drainingTick.signal()
        }
        XCTAssertTrue(transport.waitUntilInFlight(1, timeout: 5))

        let stopper = CaptureControllerStopper(controller: controller)
        let stopped = CaptureStatusBox()
        let stopFinished = DispatchSemaphore(value: 0)
        DispatchQueue.global().async {
            if let status = stopper.stop(deadline: Date(timeIntervalSince1970: 1)) {
                stopped.append(status)
            }
            stopFinished.signal()
        }
        XCTAssertEqual(
            tailHandedOver.wait(timeout: .now() + 5),
            .success,
            "the stop has flushed the source and is at the transport"
        )
        XCTAssertEqual(
            stopFinished.wait(timeout: .now() + 0.3),
            .timedOut,
            "the stop is held by the pass still in flight rather than skipping past it"
        )

        transport.release()
        XCTAssertEqual(stopFinished.wait(timeout: .now() + 5), .success)
        XCTAssertEqual(drainingTick.wait(timeout: .now() + 5), .success)
        let finalStatus = try XCTUnwrap(stopped.load().first)

        // The meeting's last frame only exists after the stop flushes, and no later tick will ever
        // carry it: a stop that gave up its turn would leave it queued forever.
        XCTAssertEqual(
            transport.published.map(\.captureTimestampNS).sorted(),
            [1, 2]
        )
        XCTAssertEqual(finalStatus.publishedFrameCount, 2)
        XCTAssertEqual(finalStatus.outbox.retainedFrames, 0)
        XCTAssertFalse(finalStatus.running)
    }

    func testPinnedProviderKeepsOneSessionPerPinAndSupersedesARotatedOne() throws {
        var built: [String] = []
        let provider = PinnedURLSessionCaptureHTTPClientProvider(makeClient: { pin in
            built.append(pin)
            return URLSessionCaptureHTTPClient(session: URLSession(configuration: .ephemeral))
        })
        let firstPin = String(repeating: "a", count: 64)
        let rotatedPin = String(repeating: "b", count: 64)

        // One meeting-minute of frames plus heartbeats, all on the same pin.
        var clients: [CaptureHTTPClient] = []
        for _ in 0..<180 {
            clients.append(try provider.client(certificatePinSHA256Hex: firstPin))
        }
        let rotated = try provider.client(certificatePinSHA256Hex: rotatedPin)

        // A per-request session would leak its pinning delegate for the whole meeting and
        // re-handshake TLS every 0.5 s; one per live pin is the bound.
        XCTAssertEqual(built, [firstPin, rotatedPin])
        XCTAssertEqual(Set(clients.map { ObjectIdentifier($0 as AnyObject) }).count, 1)
        XCTAssertNotEqual(
            ObjectIdentifier(clients[0] as AnyObject),
            ObjectIdentifier(rotated as AnyObject),
            "a rotated pin is a different session, not the same one with a new expectation"
        )

        // A real pinned client owns its session, so it is the one that can be superseded.
        let owned = try URLSessionCaptureHTTPClient(certificatePinSHA256Hex: firstPin)
        XCTAssertFalse(owned.isInvalidated)
        owned.invalidate()
        XCTAssertTrue(owned.isInvalidated)
        XCTAssertThrowsError(
            try owned.send(URLRequest(url: URL(string: "https://127.0.0.1/api/live")!))
        ) { error in
            XCTAssertEqual(
                error as? CaptureHTTPTransportError,
                .missingCertificatePin,
                "a superseded session must fail rather than keep serving a rotated-away pin"
            )
        }
    }

    func testProductionPumpTicksOncePerCanonicalWireFrameOnOneSharedPinnedProvider() throws {
        let canonicalFramePeriod = Double(NativeLaneWireFormat.live.frameSamples)
            / Double(NativeLaneWireFormat.live.sampleRate)
        XCTAssertEqual(CapturePumpContract.interval, canonicalFramePeriod, accuracy: 1e-9)
        XCTAssertEqual(CapturePumpContract.interval, 0.5, accuracy: 1e-9)

        let source = try String(
            contentsOf: packageRoot()
                .appendingPathComponent("Sources")
                .appendingPathComponent("MOSSCaptureApp")
                .appendingPathComponent("main.swift"),
            encoding: .utf8
        )

        XCTAssertTrue(
            source.contains("RepeatingCaptureSchedulerAdapter(interval: CapturePumpContract.interval)"),
            "the shipped pump cadence is the stated contract, not a literal beside it"
        )
        XCTAssertEqual(
            try matches(pattern: #"(PinnedURLSessionCaptureHTTPClientProvider\(\))"#, in: source).count,
            1,
            "frames, heartbeats and pairing share one provider, so the process holds one session per pin"
        )
        for dependent in ["CaptureV2HTTPTransportAdapter", "CaptureHTTPHealthAdapter"] {
            // The invariant is the argument, not the indentation: a dependent may be nested inside
            // a decorator, and it still has to be handed the one shared provider.
            XCTAssertEqual(
                try matches(pattern: #"(\#(dependent)\(\s*clientProvider: httpClients,)"#, in: source).count,
                1,
                "\(dependent) has to be given the shared provider rather than defaulting to its own"
            )
        }
    }

    private func laneFrame(
        _ lane: CaptureLane,
        sampleRate: Int = 16_000,
        sampleCount: Int = 8_000,
        captureTimestampNS: UInt64,
        sequence: UInt64 = 0,
        deviceEpoch: UInt64 = 1
    ) -> CaptureFrame {
        var pcm16 = Data(count: Swift.max(sampleCount, 0) * 2)
        if !pcm16.isEmpty {
            pcm16[0] = UInt8(truncatingIfNeeded: captureTimestampNS)
        }
        return CaptureFrame(
            lane: lane,
            sequence: sequence,
            sampleRate: sampleRate,
            sampleCount: sampleCount,
            captureTimestampNS: captureTimestampNS,
            deviceEpoch: deviceEpoch,
            silent: false,
            discontinuity: false,
            pcm16: pcm16
        )
    }

    func testControllerSharedStatusIsSynchronizedUnderConcurrentPumpStatus() throws {
        let source = ConcurrentEmptyCaptureSource()
        let scheduler = ConcurrentCaptureScheduler()
        let health = ConcurrentCaptureHealth()
        let controller = CaptureController(
            source: source,
            transport: NoOpCaptureTransport(),
            keyStore: FakeCaptureKeyStoreAdapter(),
            clock: IncrementingCaptureClock(),
            scheduler: scheduler,
            health: health
        )
        try controller.start(
            configuration: CaptureConfiguration(
                sessionID: "session-a",
                serverURL: URL(string: "https://127.0.0.1/live")!
            )
        )

        let queue = DispatchQueue(label: "moss.capture.test.concurrent", attributes: .concurrent)
        let group = DispatchGroup()
        let snapshots = CaptureStatusBox()
        let pumpRunner = ScheduledPumpRunner(scheduler: scheduler)
        let statusReader = CaptureStatusReader(controller: controller)
        for _ in 0..<20 {
            group.enter()
            queue.async {
                pumpRunner.run()
                group.leave()
            }
        }
        for _ in 0..<100 {
            group.enter()
            queue.async {
                snapshots.append(statusReader.status())
                group.leave()
            }
        }

        XCTAssertEqual(group.wait(timeout: .now() + 2), .success)
        let current = controller.status()
        let stopped = try controller.stop(deadline: Date(timeIntervalSince1970: 1))

        XCTAssertTrue(current.running)
        XCTAssertEqual(current.sessionID, "session-a")
        XCTAssertEqual(current.publishedFrameCount, 0)
        XCTAssertEqual(current.lastHealthSequence, 21)
        XCTAssertNil(current.pumpFailure)
        XCTAssertEqual(health.emissionCount(), 21)
        XCTAssertTrue(snapshots.load().allSatisfy { $0.running && $0.sessionID == "session-a" })
        XCTAssertTrue(snapshots.load().allSatisfy { $0.publishedFrameCount == 0 })
        XCTAssertFalse(stopped.running)
        XCTAssertEqual(stopped.sessionID, "session-a")
        XCTAssertNil(controller.status().sessionID)
    }

    func testCaptureControllerStateSharedAccessInventoryIsLockFenced() throws {
        let sourceURL = packageRoot()
            .appendingPathComponent("Sources/MOSSCaptureCore/CaptureController.swift")
        let source = try String(contentsOf: sourceURL, encoding: .utf8)
        let stateSource = try XCTUnwrap(
            source.components(
                separatedBy: "private final class CaptureControllerState {"
            ).dropFirst().first
        )
        let expectedMethods = Set([
            "beginStart",
            "rollbackStart",
            "runningConfiguration",
            "requireRunning",
            "storeHealthTask",
            "recordPublishedFrame",
            "recordHealthEmissionAttempt",
            "clearPumpFailure",
            "recordPumpFailure",
            "recordSessionRefusal",
            "snapshot",
            "finishStop",
        ])
        let actualMethods = Set(
            try matches(
                pattern: #"(?m)^\s{4}func\s+([A-Za-z0-9_]+)\s*\("#,
                in: stateSource
            )
        )
        XCTAssertEqual(actualMethods, expectedMethods)

        for method in expectedMethods {
            let methodSource = try XCTUnwrap(
                stateSource.components(
                    separatedBy: "    func \(method)("
                ).dropFirst().first?
                    .components(separatedBy: "\n    func ").first
            )
            XCTAssertTrue(methodSource.contains("lock.lock()"), method)
            XCTAssertTrue(methodSource.contains("lock.unlock()"), method)
        }
    }

    func testRepeatingSchedulerContinuesUntilExplicitCancellation() throws {
        let scheduler = RepeatingCaptureSchedulerAdapter(interval: 0.01)
        let repeated = expectation(description: "repeating scheduler fired three times")
        repeated.expectedFulfillmentCount = 3
        let cancellation = scheduler.schedule(label: "moss.capture.test-repeating") {
            repeated.fulfill()
        }

        wait(for: [repeated], timeout: 1)
        cancellation.cancel()
    }

    func testStartRequiresControlSecretAndRejectsSecondStart() throws {
        let configuration = CaptureConfiguration(
            sessionID: "session-a",
            serverURL: URL(string: "https://127.0.0.1/live")!
        )
        let missingSecret = CaptureController(
            source: FakeCaptureSourceAdapter(frames: []),
            transport: FakeCaptureTransportAdapter(),
            keyStore: FakeCaptureKeyStoreAdapter(secret: nil),
            clock: FakeCaptureClockAdapter(),
            scheduler: FakeCaptureSchedulerAdapter(),
            health: FakeCaptureHealthAdapter()
        )
        XCTAssertThrowsError(try missingSecret.start(configuration: configuration)) { error in
            XCTAssertEqual(error as? CaptureControllerError, .missingControlSecret)
        }

        let controller = CaptureController.fakeForLocalDevelopment()
        try controller.start(configuration: configuration)
        XCTAssertThrowsError(try controller.start(configuration: configuration)) { error in
            XCTAssertEqual(error as? CaptureControllerError, .alreadyRunning)
        }
    }

    func testNativeSourceVectorsUseRequiredMacOSCapturePaths() throws {
        let system = SystemAudioTap()
        let description = system.makeTapDescription(name: "test")

        XCTAssertTrue(description.isPrivate)
        XCTAssertEqual(description.muteBehavior, .unmuted)
        XCTAssertTrue(description.isExclusive)
        XCTAssertTrue(description.isMixdown)
        XCTAssertEqual(SystemAudioTap.sourceVector.processTapFunction, "AudioHardwareCreateProcessTap")
        XCTAssertEqual(SystemAudioTap.sourceVector.halCallbackFunction, "AudioDeviceCreateIOProcIDWithBlock")
        XCTAssertEqual(SystemAudioTap.sourceVector.aggregateDevice, "private transient aggregate")
        XCTAssertEqual(MicrophoneCapture.sourceVector.engine, "AVAudioEngine")
        XCTAssertEqual(MicrophoneCapture.sourceVector.input, "inputNode")
        XCTAssertEqual(MicrophoneCapture.sourceVector.tap, "installTap")
    }

    func testNativeDualCaptureSourceComposesTwoSourcesAndDrainsEachBufferOnce() throws {
        let system = RecordingNativeCaptureComponent(
            buffersOnStart: [
                nativeBuffer(lane: .system, timestamp: 10, deviceEpoch: 1, samples: [0.5])
            ]
        )
        let microphone = RecordingNativeCaptureComponent(
            buffersOnStart: [
                nativeBuffer(lane: .microphone, timestamp: 12, deviceEpoch: 7, samples: [0])
            ]
        )
        let source = NativeDualCaptureSource(
            system: system,
            microphone: microphone,
            queue: RealTimeNativeAudioBufferQueue(capacity: 8),
            emitter: laboratoryEmitter()
        )

        try source.start(
            configuration: CaptureConfiguration(
                sessionID: "session-a",
                serverURL: URL(string: "https://moss.example")!
            )
        )
        let frames = try source.pendingFrames()
        let secondDrain = try source.pendingFrames()
        let runningStatus = source.status()
        try source.stop(deadline: Date(timeIntervalSince1970: 1))
        let stoppedStatus = source.status()

        XCTAssertEqual(system.startCount, 1)
        XCTAssertEqual(microphone.startCount, 1)
        XCTAssertEqual(frames.map(\.lane), [.system, .microphone])
        XCTAssertEqual(frames.map(\.sequence), [0, 0])
        XCTAssertEqual(frames.map(\.captureTimestampNS), [10, 12])
        XCTAssertEqual(frames.map(\.deviceEpoch), [1, 7])
        XCTAssertEqual(frames.map(\.silent), [false, true])
        XCTAssertTrue(secondDrain.isEmpty)
        XCTAssertEqual(runningStatus.map(\.state), ["capturing", "capturing"])
        XCTAssertEqual(runningStatus.map(\.deviceEpoch), [1, 7])
        XCTAssertEqual(system.stopCount, 1)
        XCTAssertEqual(microphone.stopCount, 1)
        XCTAssertEqual(stoppedStatus.map(\.state), ["stopped", "stopped"])
    }

    func testNativeDualCaptureSourceSystemSurvivesMicrophoneStartFail() throws {
        let system = RecordingNativeCaptureComponent(
            buffersOnStart: [
                nativeBuffer(lane: .system, timestamp: 10, deviceEpoch: 1, samples: [0.5])
            ]
        )
        let microphone = RecordingNativeCaptureComponent(
            startError: NativeCaptureError.permissionDenied("microphone")
        )
        let source = NativeDualCaptureSource(
            system: system,
            microphone: microphone,
            queue: RealTimeNativeAudioBufferQueue(capacity: 8),
            emitter: laboratoryEmitter()
        )

        try source.start(
            configuration: CaptureConfiguration(
                sessionID: "session-a",
                serverURL: URL(string: "https://moss.example")!
            )
        )
        let frames = try source.pendingFrames()
        let runningStatus = source.status()
        try source.stop(deadline: Date(timeIntervalSince1970: 1))

        XCTAssertEqual(system.startCount, 1)
        XCTAssertEqual(system.stopCount, 1)
        XCTAssertEqual(microphone.startCount, 1)
        XCTAssertEqual(microphone.stopCount, 1)
        XCTAssertEqual(frames.map(\.lane), [.system])
        XCTAssertEqual(runningStatus.map(\.state), ["capturing", "failed"])
        XCTAssertNil(runningStatus.first { $0.lane == .system }?.failureCode)
        XCTAssertEqual(
            runningStatus.first { $0.lane == .microphone }?.failureCode,
            "macos_permission_denied"
        )
    }

    func testNativeDualCaptureSourceMicrophoneSurvivesSystemStartFail() throws {
        let system = RecordingNativeCaptureComponent(
            startError: NativeCaptureError.deviceUnavailable("system")
        )
        let microphone = RecordingNativeCaptureComponent(
            buffersOnStart: [
                nativeBuffer(lane: .microphone, timestamp: 12, deviceEpoch: 7, samples: [0])
            ]
        )
        let source = NativeDualCaptureSource(
            system: system,
            microphone: microphone,
            queue: RealTimeNativeAudioBufferQueue(capacity: 8),
            emitter: laboratoryEmitter()
        )

        try source.start(
            configuration: CaptureConfiguration(
                sessionID: "session-a",
                serverURL: URL(string: "https://moss.example")!
            )
        )
        let frames = try source.pendingFrames()
        let runningStatus = source.status()
        try source.stop(deadline: Date(timeIntervalSince1970: 1))

        XCTAssertEqual(system.startCount, 1)
        XCTAssertEqual(system.stopCount, 1)
        XCTAssertEqual(microphone.startCount, 1)
        XCTAssertEqual(microphone.stopCount, 1)
        XCTAssertEqual(frames.map(\.lane), [.microphone])
        XCTAssertEqual(runningStatus.map(\.state), ["failed", "capturing"])
        XCTAssertEqual(
            runningStatus.first { $0.lane == .system }?.failureCode,
            "macos_device_unavailable"
        )
        XCTAssertNil(runningStatus.first { $0.lane == .microphone }?.failureCode)
    }

    func testNativeDualCaptureSourceAttributesLaneOverrunAndDiscontinuityCounters() throws {
        let system = RecordingNativeCaptureComponent(
            buffersOnStart: [
                nativeBuffer(lane: .system, timestamp: 10, deviceEpoch: 1, samples: [0.5]),
                nativeBuffer(lane: .system, timestamp: 12, deviceEpoch: 1, samples: [0.25], discontinuity: true),
                nativeBuffer(lane: .system, timestamp: 13, deviceEpoch: 1, samples: [0.75]),
            ]
        )
        let microphone = RecordingNativeCaptureComponent(
            buffersOnStart: [
                nativeBuffer(lane: .microphone, timestamp: 11, deviceEpoch: 7, samples: [0])
            ]
        )
        let source = NativeDualCaptureSource(
            system: system,
            microphone: microphone,
            queue: RealTimeNativeAudioBufferQueue(capacity: 2),
            emitter: laboratoryEmitter()
        )

        try source.start(
            configuration: CaptureConfiguration(
                sessionID: "session-a",
                serverURL: URL(string: "https://moss.example")!
            )
        )
        _ = try source.pendingFrames()
        let runningStatus = source.status()
        try source.stop(deadline: Date(timeIntervalSince1970: 1))

        let systemStatus = try XCTUnwrap(runningStatus.first { $0.lane == .system })
        let microphoneStatus = try XCTUnwrap(runningStatus.first { $0.lane == .microphone })
        // D-a: the lane dropped a buffer and kept capturing, so it is degraded, not failed. The
        // code and the count are unchanged — what changed is the word that decides whether the
        // server closes the lane.
        XCTAssertEqual(systemStatus.state, "degraded")
        XCTAssertEqual(systemStatus.failureCode, "macos_buffer_overrun")
        XCTAssertEqual(systemStatus.droppedFrames, 1)
        XCTAssertEqual(systemStatus.discontinuities, 1)
        XCTAssertEqual(microphoneStatus.state, "capturing")
        XCTAssertNil(microphoneStatus.failureCode)
        XCTAssertEqual(microphoneStatus.droppedFrames, 0)
        XCTAssertEqual(microphoneStatus.discontinuities, 0)
    }

    /// A new `start` is a new question about every lane, and the drops the previous generation
    /// already reported are the previous generation's answer.
    ///
    /// The buffer queue counts drops for the life of the process while the source keeps a watermark
    /// of what it has already turned into facts. Reset the watermark without re-baselining it and
    /// the first drain of the new generation reads the whole process's drop history back as fresh
    /// loss: a meeting that has not dropped a single buffer comes up already carrying the previous
    /// meeting's damage, and says so in its first heartbeat. This is candidate 49 (L2) — the same
    /// "a new session id is a new question" rule K4 applied to `sessionRefusal`. D-a since made
    /// that verdict a degradation rather than a failure, which is why the fresh generation is
    /// asserted `capturing` with no code at all: neither verdict may be inherited.
    func testNativeDualCaptureSourceStartDoesNotReplayEarlierGenerationDrops() throws {
        let queue = RealTimeNativeAudioBufferQueue(capacity: 2)
        let source = NativeDualCaptureSource(
            system: RecordingNativeCaptureComponent(),
            microphone: RecordingNativeCaptureComponent(),
            queue: queue,
            emitter: laboratoryEmitter()
        )

        try source.start(configuration: laneConfiguration())
        // One buffer more than the lane can hold, produced the way a device callback produces it.
        for index in 0..<3 {
            queue.enqueueFromRealtimeCallback(
                nativeBuffer(
                    lane: .system,
                    timestamp: UInt64(10 + index),
                    deviceEpoch: 1,
                    samples: [0.25]
                )
            )
        }
        _ = try source.pendingFrames()

        let overrun = try XCTUnwrap(source.status().first { $0.lane == .system })
        XCTAssertEqual(overrun.state, "degraded")
        XCTAssertEqual(overrun.failureCode, "macos_buffer_overrun")
        XCTAssertEqual(overrun.droppedFrames, 1)

        try source.stop(deadline: Date(timeIntervalSince1970: 1))
        try source.start(configuration: laneConfiguration())
        _ = try source.pendingFrames()

        let restarted = try XCTUnwrap(source.status().first { $0.lane == .system })
        XCTAssertEqual(restarted.state, "capturing")
        XCTAssertNil(restarted.failureCode)
        XCTAssertEqual(restarted.droppedFrames, 0)
    }

    func testNativeDualCaptureSourceInvalidatesGenerationBeforeComponentTeardown() throws {
        let system = RecordingNativeCaptureComponent(emitLateFactOnStop: true)
        let microphone = RecordingNativeCaptureComponent()
        let source = NativeDualCaptureSource(
            system: system,
            microphone: microphone,
            queue: RealTimeNativeAudioBufferQueue(capacity: 2),
            emitter: laboratoryEmitter()
        )

        try source.start(
            configuration: CaptureConfiguration(
                sessionID: "session-a",
                serverURL: URL(string: "https://moss.example")!
            )
        )
        try source.stop(deadline: Date(timeIntervalSince1970: 1))

        XCTAssertEqual(system.lateFactWasRejected, true)
    }

    func testNativeDualCaptureSourceSilenceIsNonTerminal() throws {
        let system = RecordingNativeCaptureComponent(
            buffersOnStart: [
                nativeBuffer(lane: .system, timestamp: 10, deviceEpoch: 1, samples: [0])
            ]
        )
        let microphone = RecordingNativeCaptureComponent(
            buffersOnStart: [
                nativeBuffer(lane: .microphone, timestamp: 12, deviceEpoch: 7, samples: [0])
            ]
        )
        let source = NativeDualCaptureSource(
            system: system,
            microphone: microphone,
            queue: RealTimeNativeAudioBufferQueue(capacity: 8),
            emitter: laboratoryEmitter()
        )

        try source.start(
            configuration: CaptureConfiguration(
                sessionID: "session-a",
                serverURL: URL(string: "https://moss.example")!
            )
        )
        let frames = try source.pendingFrames()
        let status = source.status()
        try source.stop(deadline: Date(timeIntervalSince1970: 1))

        XCTAssertEqual(frames.map(\.silent), [true, true])
        XCTAssertEqual(status.map(\.state), ["capturing", "capturing"])
        XCTAssertEqual(status.map(\.failureCode), [nil, nil])
    }

    func testNativeDualCaptureSourceUnwindsBothLanesWhenEveryStartFails() throws {
        let system = RecordingNativeCaptureComponent(
            startError: NativeCaptureError.deviceUnavailable("system")
        )
        let microphone = RecordingNativeCaptureComponent(
            startError: NativeCaptureError.permissionDenied("microphone")
        )
        let source = NativeDualCaptureSource(
            system: system,
            microphone: microphone,
            queue: RealTimeNativeAudioBufferQueue(capacity: 8),
            emitter: laboratoryEmitter()
        )

        XCTAssertThrowsError(
            try source.start(
                configuration: CaptureConfiguration(
                    sessionID: "session-a",
                    serverURL: URL(string: "https://moss.example")!
                )
            )
        ) { error in
            XCTAssertEqual(error as? NativeCaptureError, .deviceUnavailable("system"))
        }

        XCTAssertEqual(system.startCount, 1)
        XCTAssertEqual(system.stopCount, 1)
        XCTAssertEqual(microphone.startCount, 1)
        XCTAssertEqual(microphone.stopCount, 1)
        XCTAssertEqual(source.status().map(\.state), ["failed", "failed"])
    }

    func testSystemAudioTapStartsStopsAndDestroysCoreAudioInOrder() throws {
        let driver = RecordingSystemAudioTapDriver()
        let tap = SystemAudioTap(driver: driver)

        try tap.start(queue: RealTimeNativeAudioBufferQueue(capacity: 4))
        tap.stop()
        tap.stop()

        XCTAssertEqual(driver.events, [
            "AudioHardwareCreateProcessTap",
            "AudioHardwareCreateAggregateDevice",
            "AudioObjectAddPropertyListenerBlock",
            "AudioDeviceCreateIOProcIDWithBlock",
            "AudioDeviceStart",
            "AudioDeviceStop",
            "AudioObjectRemovePropertyListenerBlock",
            "AudioDeviceDestroyIOProcID",
            "AudioHardwareDestroyAggregateDevice",
            "AudioHardwareDestroyProcessTap",
        ])
    }

    func testSystemAudioTapPartialStartUnwindsCreatedResourcesInReverseOrder() throws {
        let driver = RecordingSystemAudioTapDriver(
            startError: NativeCaptureError.deviceUnavailable("AudioDeviceStart")
        )
        let tap = SystemAudioTap(driver: driver)

        XCTAssertThrowsError(
            try tap.start(queue: RealTimeNativeAudioBufferQueue(capacity: 4))
        ) { error in
            XCTAssertEqual(error as? NativeCaptureError, .deviceUnavailable("AudioDeviceStart"))
        }
        tap.stop()

        XCTAssertEqual(driver.events, [
            "AudioHardwareCreateProcessTap",
            "AudioHardwareCreateAggregateDevice",
            "AudioObjectAddPropertyListenerBlock",
            "AudioDeviceCreateIOProcIDWithBlock",
            "AudioDeviceStart",
            "AudioObjectRemovePropertyListenerBlock",
            "AudioDeviceDestroyIOProcID",
            "AudioHardwareDestroyAggregateDevice",
            "AudioHardwareDestroyProcessTap",
        ])
    }

    func testSystemAudioTapReportsPostStartFailureThroughSourceHealth() throws {
        let driver = RecordingSystemAudioTapDriver()
        let tap = SystemAudioTap(deviceEpoch: 3, driver: driver)
        let health = NativeLaneHealth()
        let generation = health.beginGeneration()
        tap.attachHealthSink(health, lane: .system, generation: generation)

        try tap.start(queue: RealTimeNativeAudioBufferQueue(capacity: 4))
        health.enqueue(.admitted, lane: .system, generation: generation)
        driver.emit(.isRunning(false))

        let system = try XCTUnwrap(
            health.statuses(running: true).first { $0.lane == .system }
        )
        XCTAssertEqual(system.state, "failed")
        XCTAssertEqual(system.failureCode, "macos_io_stopped_abnormally")
        XCTAssertEqual(system.deviceEpoch, 3)
        tap.stop()
    }

    func testSystemAudioTapConfigurationChangeIsNonTerminal() throws {
        let driver = RecordingSystemAudioTapDriver()
        let tap = SystemAudioTap(deviceEpoch: 4, driver: driver)
        let health = NativeLaneHealth()
        let generation = health.beginGeneration()
        tap.attachHealthSink(health, lane: .system, generation: generation)

        try tap.start(queue: RealTimeNativeAudioBufferQueue(capacity: 4))
        health.enqueue(.admitted, lane: .system, generation: generation)
        driver.emit(.configurationChanged)

        let system = try XCTUnwrap(
            health.statuses(running: true).first { $0.lane == .system }
        )
        XCTAssertEqual(system.state, "capturing")
        XCTAssertNil(system.failureCode)
        XCTAssertEqual(system.deviceEpoch, 4)
        tap.stop()
    }

    func testSystemAudioTapStaleGenerationIgnoredAfterStop() throws {
        let driver = RecordingSystemAudioTapDriver()
        let tap = SystemAudioTap(driver: driver)
        let health = NativeLaneHealth()
        let generation = health.beginGeneration()
        tap.attachHealthSink(health, lane: .system, generation: generation)

        try tap.start(queue: RealTimeNativeAudioBufferQueue(capacity: 4))
        health.enqueue(.admitted, lane: .system, generation: generation)
        health.invalidateGeneration()
        tap.stop()
        driver.emitAfterRemoval(.isAlive(false))

        let system = try XCTUnwrap(
            health.statuses(running: false).first { $0.lane == .system }
        )
        XCTAssertEqual(system.state, "stopped")
        XCTAssertNil(system.failureCode)
    }

    func testMicrophoneCaptureReportsPermissionAndCurrentInputDevice() throws {
        let driver = RecordingMicrophoneCaptureDriver(permission: .granted, currentDeviceID: 42)
        let microphone = MicrophoneCapture(driver: driver)
        let health = NativeLaneHealth()
        let generation = health.beginGeneration()
        microphone.attachHealthSink(health, lane: .microphone, generation: generation)

        try microphone.start(queue: RealTimeNativeAudioBufferQueue(capacity: 4))
        health.enqueue(.admitted, lane: .microphone, generation: generation)

        let status = try XCTUnwrap(
            health.statuses(running: true).first { $0.lane == .microphone }
        )
        XCTAssertEqual(driver.events, [
            "recordPermission",
            "kAudioOutputUnitProperty_CurrentDevice",
            "AVAudioEngineConfigurationChange",
            "installTap",
            "AVAudioEngine.start",
        ])
        XCTAssertEqual(status.state, "capturing")
        XCTAssertEqual(status.deviceEpoch, 42)
        XCTAssertNil(status.failureCode)
        microphone.stop()
    }

    func testMicrophoneCaptureUndeterminedPermissionNeverTouchesInputNode() throws {
        let driver = RecordingMicrophoneCaptureDriver(permission: .undetermined, currentDeviceID: 64)
        let microphone = MicrophoneCapture(driver: driver)
        let health = NativeLaneHealth()
        let generation = health.beginGeneration()
        microphone.attachHealthSink(health, lane: .microphone, generation: generation)

        XCTAssertThrowsError(
            try microphone.start(queue: RealTimeNativeAudioBufferQueue(capacity: 4))
        ) { error in
            XCTAssertEqual(error as? NativeCaptureError, .permissionDenied("microphone"))
        }

        // Reading the current input device is what blocks forever behind an unanswered prompt.
        XCTAssertEqual(driver.events, ["recordPermission"])
        // Undetermined is still not denied: the lane records no terminal failure of its own.
        XCTAssertNil(health.failure(for: .microphone))
        let status = try XCTUnwrap(
            health.statuses(running: true).first { $0.lane == .microphone }
        )
        XCTAssertNil(status.failureCode)
    }

    func testMicrophoneCaptureRequestAccessIsTheExplicitPermissionTransition() throws {
        let driver = RecordingMicrophoneCaptureDriver(permission: .undetermined, currentDeviceID: 64)
        let microphone = MicrophoneCapture(driver: driver)

        XCTAssertEqual(microphone.authorization(), .undetermined)
        let answers = RecordedPermissionAnswers()
        microphone.requestAuthorization { answers.append($0) }

        // The request returns before the user answers, so the control loop is never held.
        XCTAssertEqual(driver.events, ["recordPermission", "requestRecordPermission"])
        XCTAssertTrue(answers.values.isEmpty)

        driver.answerRecordPermissionRequest(.granted)
        XCTAssertEqual(answers.values, [.granted])
        XCTAssertEqual(microphone.authorization(), .granted)
    }

    func testSystemAudioPermissionIsResolvedByTheUserInitiatedRecordingStart() throws {
        XCTAssertEqual(SystemAudioPermission.state(afterRecordingStart: nil), .granted)
        XCTAssertEqual(
            SystemAudioPermission.state(
                afterRecordingStart: NativeCaptureError.permissionDenied("system audio")
            ),
            .denied
        )
        // A device or OSStatus failure is not a permission answer; the lane's typed failure code
        // already carries the reason and the decision stays unresolved.
        XCTAssertNil(
            SystemAudioPermission.state(
                afterRecordingStart: NativeCaptureError.osStatus("AudioDeviceStart", -10_875)
            )
        )

        let source = try String(
            contentsOf: packageRoot()
                .appendingPathComponent("Sources/MOSSCaptureCore/SystemAudioTap.swift"),
            encoding: .utf8
        )
        XCTAssertTrue(source.contains("AudioHardwareCreateProcessTap"))
        for forbidden in [
            "CGPreflightScreenCaptureAccess",
            "CGRequestScreenCaptureAccess",
            "CoreGraphics",
            "ScreenCaptureKit",
        ] {
            XCTAssertFalse(source.contains(forbidden), forbidden)
        }
    }

    func testLanePermissionCoordinatorKeepsLaneStateAndFencesRetiredAnswers() throws {
        let coordinator = NativeLanePermissionCoordinator()
        let gate = PermissionGatedNativeCaptureComponent(authorization: .undetermined)
        coordinator.beginGeneration(7)
        coordinator.record(.granted, for: .system, generation: 7)

        let answers = RecordedPermissionAnswers()
        coordinator.request(lane: .microphone, generation: 7, gate: gate) { answers.append($0) }
        coordinator.request(lane: .microphone, generation: 7, gate: gate) { answers.append($0) }

        XCTAssertEqual(gate.requestCount, 1)
        XCTAssertEqual(coordinator.state(for: .system), .granted)
        XCTAssertEqual(coordinator.state(for: .microphone), .pending)

        // A generation that is not live can neither record state nor start a request.
        coordinator.record(.denied, for: .system, generation: 6)
        coordinator.request(lane: .system, generation: 6, gate: gate) { answers.append($0) }
        XCTAssertEqual(coordinator.state(for: .system), .granted)
        XCTAssertEqual(gate.requestCount, 1)

        coordinator.retire()
        gate.answerPermissionRequest(.granted)
        XCTAssertTrue(answers.values.isEmpty)
        XCTAssertNil(coordinator.state(for: .microphone))
    }

    func testUndeterminedMicrophonePromptsOnceAndJoinsRunningCaptureOnGrant() throws {
        let system = RecordingNativeCaptureComponent(
            buffersOnStart: [
                nativeBuffer(lane: .system, timestamp: 10, deviceEpoch: 1, samples: [0.5])
            ]
        )
        let microphone = PermissionGatedNativeCaptureComponent(authorization: .undetermined)
        let source = NativeDualCaptureSource(
            system: system,
            microphone: microphone,
            queue: RealTimeNativeAudioBufferQueue(capacity: 8),
            emitter: laboratoryEmitter()
        )

        try source.start(configuration: laneConfiguration())

        // `start` returned while the prompt is still on screen: the lane is pending, not failed,
        // and the microphone engine has not been touched.
        let pending = source.status()
        XCTAssertEqual(microphone.requestCount, 1)
        XCTAssertEqual(microphone.startCount, 0)
        XCTAssertEqual(pending.map(\.state), ["capturing", "pending"])
        XCTAssertEqual(pending.map(\.failureCode), [nil, nil])

        microphone.answerPermissionRequest(.granted)

        let granted = source.status()
        XCTAssertEqual(microphone.startCount, 1)
        XCTAssertEqual(microphone.requestCount, 1)
        XCTAssertEqual(granted.map(\.state), ["capturing", "capturing"])
        XCTAssertEqual(granted.map(\.failureCode), [nil, nil])
        try source.stop(deadline: Date(timeIntervalSince1970: 1))
    }

    func testUndeterminedMicrophoneDenialFailsOnlyThatLane() throws {
        let system = RecordingNativeCaptureComponent(
            buffersOnStart: [
                nativeBuffer(lane: .system, timestamp: 10, deviceEpoch: 1, samples: [0.5])
            ]
        )
        let microphone = PermissionGatedNativeCaptureComponent(authorization: .undetermined)
        let source = NativeDualCaptureSource(
            system: system,
            microphone: microphone,
            queue: RealTimeNativeAudioBufferQueue(capacity: 8),
            emitter: laboratoryEmitter()
        )

        try source.start(configuration: laneConfiguration())
        microphone.answerPermissionRequest(.denied)

        let denied = source.status()
        XCTAssertEqual(microphone.startCount, 0)
        XCTAssertEqual(denied.map(\.state), ["capturing", "failed"])
        XCTAssertEqual(
            denied.map(\.failureCode),
            [nil, "macos_permission_denied"]
        )
        // The surviving lane keeps producing frames.
        XCTAssertEqual(try source.pendingFrames().map(\.lane), [.system])
        try source.stop(deadline: Date(timeIntervalSince1970: 1))
    }

    func testDuplicateStartDoesNotRequestPermissionsTwice() throws {
        let system = RecordingNativeCaptureComponent(
            buffersOnStart: [
                nativeBuffer(lane: .system, timestamp: 10, deviceEpoch: 1, samples: [0.5])
            ]
        )
        let microphone = PermissionGatedNativeCaptureComponent(authorization: .undetermined)
        let source = NativeDualCaptureSource(
            system: system,
            microphone: microphone,
            queue: RealTimeNativeAudioBufferQueue(capacity: 8),
            emitter: laboratoryEmitter()
        )

        try source.start(configuration: laneConfiguration())
        try source.start(configuration: laneConfiguration())

        XCTAssertEqual(microphone.requestCount, 1)
        XCTAssertEqual(microphone.startCount, 0)
        XCTAssertEqual(system.startCount, 1)
        XCTAssertEqual(source.status().map(\.state), ["capturing", "pending"])

        // One answer to the one outstanding prompt still admits the lane exactly once.
        microphone.answerPermissionRequest(.granted)
        XCTAssertEqual(microphone.startCount, 1)
        try source.stop(deadline: Date(timeIntervalSince1970: 1))
    }

    func testStopDuringPermissionPromptCancelsGeneration() throws {
        let system = RecordingNativeCaptureComponent(
            buffersOnStart: [
                nativeBuffer(lane: .system, timestamp: 10, deviceEpoch: 1, samples: [0.5])
            ]
        )
        let microphone = PermissionGatedNativeCaptureComponent(authorization: .undetermined)
        let source = NativeDualCaptureSource(
            system: system,
            microphone: microphone,
            queue: RealTimeNativeAudioBufferQueue(capacity: 8),
            emitter: laboratoryEmitter()
        )

        try source.start(configuration: laneConfiguration())
        XCTAssertTrue(microphone.isPromptOutstanding)

        // `stop` answers while the prompt is still up; it must not wait for the user.
        try source.stop(deadline: Date(timeIntervalSince1970: 1))
        XCTAssertEqual(source.status().map(\.state), ["stopped", "stopped"])
        XCTAssertEqual(system.stopCount, 1)
        XCTAssertEqual(microphone.stopCount, 1)

        // The retired generation owns the outstanding prompt, so the next start asks again.
        try source.start(configuration: laneConfiguration())
        XCTAssertEqual(microphone.requestCount, 2)
        try source.stop(deadline: Date(timeIntervalSince1970: 2))
    }

    func testLatePermissionCompletionAfterStopIsNoop() throws {
        let system = RecordingNativeCaptureComponent(
            buffersOnStart: [
                nativeBuffer(lane: .system, timestamp: 10, deviceEpoch: 1, samples: [0.5])
            ]
        )
        let microphone = PermissionGatedNativeCaptureComponent(authorization: .undetermined)
        let source = NativeDualCaptureSource(
            system: system,
            microphone: microphone,
            queue: RealTimeNativeAudioBufferQueue(capacity: 8),
            emitter: laboratoryEmitter()
        )

        try source.start(configuration: laneConfiguration())
        try source.stop(deadline: Date(timeIntervalSince1970: 1))

        microphone.answerPermissionRequest(.granted)
        XCTAssertEqual(microphone.startCount, 0)
        XCTAssertEqual(source.status().map(\.state), ["stopped", "stopped"])
        XCTAssertEqual(source.status().map(\.failureCode), [nil, nil])

        microphone.answerPermissionRequest(.denied)
        XCTAssertEqual(source.status().map(\.failureCode), [nil, nil])
    }

    func testStartWithNoLaneRecordingReportsThePendingPermissionAndDisownsIt() throws {
        let system = RecordingNativeCaptureComponent(
            startError: NativeCaptureError.osStatus("AudioHardwareCreateProcessTap", 560_557_673)
        )
        let microphone = PermissionGatedNativeCaptureComponent(authorization: .undetermined)
        let source = NativeDualCaptureSource(
            system: system,
            microphone: microphone,
            queue: RealTimeNativeAudioBufferQueue(capacity: 8),
            emitter: laboratoryEmitter()
        )

        XCTAssertThrowsError(try source.start(configuration: laneConfiguration())) { error in
            XCTAssertEqual(
                error as? NativeCaptureError,
                .permissionDenied("microphone permission not granted yet")
            )
        }

        // A grant that lands behind the failed start must not begin capture on its own.
        microphone.answerPermissionRequest(.granted)
        XCTAssertEqual(microphone.startCount, 0)
        XCTAssertEqual(source.status().map(\.state), ["failed", "stopped"])
    }

    func testSystemGrantedWithMicrophoneDeniedKeepsLanePermissionsIndependent() throws {
        let system = RecordingNativeCaptureComponent(
            buffersOnStart: [
                nativeBuffer(lane: .system, timestamp: 10, deviceEpoch: 1, samples: [0.5])
            ]
        )
        let microphone = PermissionGatedNativeCaptureComponent(authorization: .denied)
        let source = NativeDualCaptureSource(
            system: system,
            microphone: microphone,
            queue: RealTimeNativeAudioBufferQueue(capacity: 8),
            emitter: laboratoryEmitter()
        )

        try source.start(configuration: laneConfiguration())

        XCTAssertEqual(microphone.requestCount, 0)
        XCTAssertEqual(microphone.startCount, 0)
        XCTAssertEqual(source.status().map(\.state), ["capturing", "failed"])
        XCTAssertEqual(
            source.status().map(\.failureCode),
            [nil, "macos_permission_denied"]
        )
        try source.stop(deadline: Date(timeIntervalSince1970: 1))
    }

    func testMicrophoneGrantedWithSystemDeniedKeepsLanePermissionsIndependent() throws {
        let system = RecordingNativeCaptureComponent(
            startError: NativeCaptureError.permissionDenied("system audio")
        )
        let microphone = PermissionGatedNativeCaptureComponent(
            authorization: .granted,
            buffersOnStart: [
                nativeBuffer(lane: .microphone, timestamp: 12, deviceEpoch: 7, samples: [0.25])
            ]
        )
        let source = NativeDualCaptureSource(
            system: system,
            microphone: microphone,
            queue: RealTimeNativeAudioBufferQueue(capacity: 8),
            emitter: laboratoryEmitter()
        )

        try source.start(configuration: laneConfiguration())

        // An already-granted lane is admitted without a second prompt.
        XCTAssertEqual(microphone.requestCount, 0)
        XCTAssertEqual(microphone.startCount, 1)
        XCTAssertEqual(source.status().map(\.state), ["failed", "capturing"])
        XCTAssertEqual(
            source.status().map(\.failureCode),
            ["macos_permission_denied", nil]
        )
        XCTAssertEqual(try source.pendingFrames().map(\.lane), [.microphone])
        try source.stop(deadline: Date(timeIntervalSince1970: 1))
    }

    func testMicrophoneCaptureDeniedPermissionReportsRawTerminalFact() throws {
        let driver = RecordingMicrophoneCaptureDriver(permission: .denied, currentDeviceID: 42)
        let microphone = MicrophoneCapture(driver: driver)
        let health = NativeLaneHealth()
        let generation = health.beginGeneration()
        microphone.attachHealthSink(health, lane: .microphone, generation: generation)

        XCTAssertThrowsError(
            try microphone.start(queue: RealTimeNativeAudioBufferQueue(capacity: 4))
        ) { error in
            XCTAssertEqual(error as? NativeCaptureError, .permissionDenied("microphone"))
        }

        let status = try XCTUnwrap(
            health.statuses(running: true).first { $0.lane == .microphone }
        )
        XCTAssertEqual(driver.events, ["recordPermission"])
        XCTAssertEqual(status.state, "failed")
        XCTAssertEqual(status.failureCode, "macos_permission_denied")
    }

    func testMicrophoneCaptureConfigurationChangeUpdatesCurrentDeviceWithoutFailure() throws {
        let driver = RecordingMicrophoneCaptureDriver(permission: .granted, currentDeviceID: 42)
        let scheduler = RecordingMicrophoneCaptureReconciliationScheduler()
        let microphone = MicrophoneCapture(
            driver: driver,
            reconciliationScheduler: scheduler
        )
        let health = NativeLaneHealth()
        let generation = health.beginGeneration()
        microphone.attachHealthSink(health, lane: .microphone, generation: generation)

        try microphone.start(queue: RealTimeNativeAudioBufferQueue(capacity: 4))
        health.enqueue(.admitted, lane: .microphone, generation: generation)
        driver.currentDeviceID = 77
        driver.emit(.configurationChanged)

        let recovering = try XCTUnwrap(
            health.statuses(running: true).first { $0.lane == .microphone }
        )
        XCTAssertEqual(recovering.state, "recovering")
        XCTAssertEqual(recovering.deviceEpoch, 42)
        XCTAssertEqual(scheduler.pendingCount, 1)
        XCTAssertFalse(driver.events.contains("AVAudioEngine.stop"))
        XCTAssertFalse(driver.events.contains("removeTap"))

        scheduler.runNext()
        let status = try XCTUnwrap(
            health.statuses(running: true).first { $0.lane == .microphone }
        )
        XCTAssertEqual(status.state, "capturing")
        XCTAssertEqual(status.deviceEpoch, 77)
        XCTAssertNil(status.failureCode)
        microphone.stop()
    }

    func testMicrophoneCaptureFailedDeviceQueryStaysRecoveringOffCallback() throws {
        let driver = RecordingMicrophoneCaptureDriver(permission: .granted, currentDeviceID: 42)
        let scheduler = RecordingMicrophoneCaptureReconciliationScheduler()
        let microphone = MicrophoneCapture(
            driver: driver,
            reconciliationScheduler: scheduler
        )
        let health = NativeLaneHealth()
        let generation = health.beginGeneration()
        microphone.attachHealthSink(health, lane: .microphone, generation: generation)

        try microphone.start(queue: RealTimeNativeAudioBufferQueue(capacity: 4))
        health.enqueue(.admitted, lane: .microphone, generation: generation)
        driver.currentDeviceError = NativeCaptureError.deviceUnavailable("query unavailable")
        driver.emit(.configurationChanged)

        XCTAssertEqual(scheduler.pendingCount, 1)
        XCTAssertFalse(driver.events.contains("AVAudioEngine.stop"))
        XCTAssertFalse(driver.events.contains("removeTap"))
        scheduler.runNext()

        let status = try XCTUnwrap(
            health.statuses(running: true).first { $0.lane == .microphone }
        )
        XCTAssertEqual(status.state, "recovering")
        XCTAssertEqual(status.deviceEpoch, 42)
        XCTAssertNil(status.failureCode)
        XCTAssertNil(health.failure(for: .microphone))
        microphone.stop()
    }

    func testMicrophoneCaptureOverloadIsRawNonTerminalFact() throws {
        let driver = RecordingMicrophoneCaptureDriver(permission: .granted, currentDeviceID: 42)
        let microphone = MicrophoneCapture(driver: driver)
        let health = NativeLaneHealth()
        let generation = health.beginGeneration()
        microphone.attachHealthSink(health, lane: .microphone, generation: generation)

        try microphone.start(queue: RealTimeNativeAudioBufferQueue(capacity: 4))
        health.enqueue(.admitted, lane: .microphone, generation: generation)
        driver.emit(.engineOverloaded)

        let status = try XCTUnwrap(
            health.statuses(running: true).first { $0.lane == .microphone }
        )
        XCTAssertEqual(status.state, "capturing")
        XCTAssertNil(status.failureCode)
        microphone.stop()
    }

    func testMicrophoneCaptureReportsPostStartAbnormalStopThroughHealth() throws {
        let driver = RecordingMicrophoneCaptureDriver(permission: .granted, currentDeviceID: 42)
        let microphone = MicrophoneCapture(driver: driver)
        let health = NativeLaneHealth()
        let generation = health.beginGeneration()
        microphone.attachHealthSink(health, lane: .microphone, generation: generation)

        try microphone.start(queue: RealTimeNativeAudioBufferQueue(capacity: 4))
        health.enqueue(.admitted, lane: .microphone, generation: generation)
        driver.emit(.engineRunning(false))

        let status = try XCTUnwrap(
            health.statuses(running: true).first { $0.lane == .microphone }
        )
        XCTAssertEqual(status.state, "failed")
        XCTAssertEqual(status.failureCode, "macos_io_stopped_abnormally")
        microphone.stop()
    }

    func testMicrophoneCaptureStaleGenerationIgnoredAfterStop() throws {
        let driver = RecordingMicrophoneCaptureDriver(permission: .granted, currentDeviceID: 42)
        let microphone = MicrophoneCapture(driver: driver)
        let health = NativeLaneHealth()
        let generation = health.beginGeneration()
        microphone.attachHealthSink(health, lane: .microphone, generation: generation)

        try microphone.start(queue: RealTimeNativeAudioBufferQueue(capacity: 4))
        health.enqueue(.admitted, lane: .microphone, generation: generation)
        health.invalidateGeneration()
        microphone.stop()
        driver.emitAfterRemoval(.engineRunning(false))

        let status = try XCTUnwrap(
            health.statuses(running: false).first { $0.lane == .microphone }
        )
        XCTAssertEqual(status.state, "stopped")
        XCTAssertNil(status.failureCode)
    }

    func testMicrophoneCaptureUsesInputAudioUnitCurrentDeviceWithoutDefaultLookup() throws {
        let source = try String(
            contentsOf: packageRoot()
                .appendingPathComponent("Sources/MOSSCaptureCore/MicrophoneCapture.swift"),
            encoding: .utf8
        )

        XCTAssertTrue(source.contains("kAudioOutputUnitProperty_CurrentDevice"))
        XCTAssertFalse(source.contains("kAudioHardwarePropertyDefaultInputDevice"))
    }

    func testNativeRuntimeErrorsAreTyped() throws {
        XCTAssertEqual(
            NativeCaptureError.permissionDenied("microphone"),
            .permissionDenied("microphone")
        )
        XCTAssertEqual(
            NativeCaptureError.deviceUnavailable("aggregate"),
            .deviceUnavailable("aggregate")
        )
        XCTAssertEqual(
            NativeCaptureError.transportUnavailable("heartbeat"),
            .transportUnavailable("heartbeat")
        )
    }

    func testRealtimeQueueIsBoundedAndFrameEmitterKeepsLaneStateIndependent() throws {
        let queue = RealTimeNativeAudioBufferQueue(capacity: 2)
        queue.enqueueFromRealtimeCallback(
            NativeCapturedAudioBuffer(
                lane: .system,
                sampleRate: 16_000,
                channelCount: 1,
                frameCount: 1,
                firstSampleMonotonicNS: 10,
                deviceEpoch: 1,
                discontinuity: false,
                samples: [0.25]
            )
        )
        queue.enqueueFromRealtimeCallback(
            NativeCapturedAudioBuffer(
                lane: .microphone,
                sampleRate: 16_000,
                channelCount: 1,
                frameCount: 1,
                firstSampleMonotonicNS: 11,
                deviceEpoch: 7,
                discontinuity: false,
                samples: [0]
            )
        )
        queue.enqueueFromRealtimeCallback(
            NativeCapturedAudioBuffer(
                lane: .system,
                sampleRate: 16_000,
                channelCount: 1,
                frameCount: 1,
                firstSampleMonotonicNS: 12,
                deviceEpoch: 1,
                discontinuity: true,
                samples: [-0.25]
            )
        )
        queue.enqueueFromRealtimeCallback(
            NativeCapturedAudioBuffer(
                lane: .system,
                sampleRate: 16_000,
                channelCount: 1,
                frameCount: 1,
                firstSampleMonotonicNS: 13,
                deviceEpoch: 1,
                discontinuity: false,
                samples: [0.5]
            )
        )

        let emitter = laboratoryEmitter()
        let frames = emitter.frames(from: queue.drain())

        XCTAssertEqual(queue.droppedBuffers, 1)
        XCTAssertEqual(
            queue.droppedBuffersByLaneSnapshot(),
            [.system: 1]
        )
        XCTAssertEqual(frames.map(\.lane), [.system, .microphone, .system])
        XCTAssertEqual(frames.map(\.sequence), [0, 0, 1])
        XCTAssertEqual(frames.map(\.deviceEpoch), [1, 7, 1])
        XCTAssertEqual(frames.map(\.captureTimestampNS), [10, 11, 12])
        XCTAssertEqual(frames.map(\.silent), [false, true, false])
        XCTAssertEqual(frames.map(\.discontinuity), [false, false, true])
        XCTAssertEqual(frames.map(\.sampleCount), [1, 1, 1])
        XCTAssertEqual(frames.map(\.pcm16.count), [2, 2, 2])

        let nextSystem = emitter.frames(
            from: [
                NativeCapturedAudioBuffer(
                    lane: .system,
                    sampleRate: 16_000,
                    channelCount: 1,
                    frameCount: 1,
                    firstSampleMonotonicNS: 13,
                    deviceEpoch: 1,
                    discontinuity: false,
                    samples: [0.5]
                )
            ]
        )
        XCTAssertEqual(nextSystem.first?.sequence, 2)
    }

    func testHostTicksBecomeRealNanosecondsAndAZeroReadingIsRefused() throws {
        // A timebase far from 1:1 is the whole point of the conversion: publishing ticks as
        // nanoseconds would compress the server's timeline by exactly this ratio.
        XCTAssertEqual(labTimebase.nanoseconds(forHostTicks: 3), 125)
        XCTAssertEqual(labTimebase.nanoseconds(forHostTicks: 12_000_000), 500_000_000)
        XCTAssertNil(labTimebase.nanoseconds(forHostTicks: 0))

        // A host that has been up for years must not wrap on the way through the numerator, and a
        // reading that genuinely cannot be expressed in nanoseconds is unusable, not a small number
        // that would pass for a valid capture instant.
        let tenYearsOfTicks = labHostTicks(forNanoseconds: 10 * 365 * 24 * 3_600 * 1_000_000_000)
        let converted = try XCTUnwrap(labTimebase.nanoseconds(forHostTicks: tenYearsOfTicks))
        let exact = Double(tenYearsOfTicks) * 125.0 / 3.0
        XCTAssertEqual(Double(converted), exact, accuracy: exact * 1e-9)
        XCTAssertNil(labTimebase.nanoseconds(forHostTicks: UInt64.max))

        // The production converter must agree with this machine's own declared timebase, whatever
        // that timebase happens to be.
        var timebase = mach_timebase_info_data_t()
        XCTAssertEqual(mach_timebase_info(&timebase), KERN_SUCCESS)
        let hostTicks: UInt64 = 12_000_000
        XCTAssertEqual(
            HostTimeNanosecondConverter().nanoseconds(forHostTicks: hostTicks),
            MachTimebaseHostTimeConverter(
                numerator: UInt64(timebase.numer),
                denominator: UInt64(timebase.denom)
            ).nanoseconds(forHostTicks: hostTicks)
        )
        XCTAssertNil(HostTimeNanosecondConverter().nanoseconds(forHostTicks: 0))
    }

    func testDeviceRateInputBecomesSteadyCanonicalFramesOnTheConvertedHostClock() throws {
        let emitter = NativeLaneFrameEmitter(wireFormat: .live, hostTime: labTimebase)
        let callbacks = 96      // 96 x 1024 at 48 kHz = 2.048 s of audio
        var frames: [CaptureFrame] = []
        for index in 0..<callbacks {
            frames += emitter.frames(from: [
                deviceBuffer(
                    lane: .system,
                    callbackIndex: index,
                    sampleRate: 48_000,
                    frameCount: 1_024
                )
            ])
        }

        // Callback-shaped output would have been 96 frames of 1024 samples at 48 kHz.
        XCTAssertEqual(frames.count, 4)
        XCTAssertEqual(Set(frames.map(\.sampleCount)), [8_000])
        XCTAssertEqual(Set(frames.map(\.sampleRate)), [16_000])
        XCTAssertEqual(Set(frames.map(\.pcm16.count)), [16_000])
        XCTAssertEqual(Set(frames.map(\.silent)), [false])
        XCTAssertEqual(frames.map(\.discontinuity), [false, false, false, false])

        let firstCaptureNS = try XCTUnwrap(
            labTimebase.nanoseconds(
                forHostTicks: deviceHostTicks(callbackIndex: 0, frameCount: 1_024, sampleRate: 48_000)
            )
        )
        let firstFrameNS = try XCTUnwrap(frames.first?.captureTimestampNS)
        // Never earlier than the instant the audio was captured, and later only by the converter's
        // fixed group delay — measured here well under a millisecond.
        XCTAssertGreaterThanOrEqual(firstFrameNS, firstCaptureNS)
        XCTAssertLessThan(firstFrameNS - firstCaptureNS, 2_000_000)

        // Half a second of audio is 500,000,000 ns on the wire, not 500,000,000 ticks. The slack is
        // one wire sample, which is all the re-anchoring of each frame on the device clock costs.
        let cadence = zip(frames.dropFirst(), frames).map {
            Int64($0.captureTimestampNS) - Int64($1.captureTimestampNS)
        }
        for step in cadence {
            XCTAssertLessThanOrEqual(abs(step - 500_000_000), 62_500, "step \(step)")
        }
    }

    func testFortyEightAndFortyFourPointOneKilohertzInputConserveDuration() throws {
        for (sampleRate, callbacks) in [(48_000, 96), (44_100, 129)] {
            let emitter = NativeLaneFrameEmitter(wireFormat: .live, hostTime: labTimebase)
            var produced = 0
            for index in 0..<callbacks {
                produced += emitter.frames(from: [
                    deviceBuffer(
                        lane: .system,
                        callbackIndex: index,
                        sampleRate: sampleRate,
                        frameCount: 1_024
                    )
                ]).reduce(0) { $0 + $1.sampleCount }
            }
            produced += emitter.flush().reduce(0) { $0 + $1.sampleCount }

            let inputSamples = callbacks * 1_024
            let expected = inputSamples * 16_000 / sampleRate
            // One sample of slack for the ratio's remainder; anything more is lost or invented
            // audio, which is what an unfiltered decimation on the server used to hide.
            XCTAssertLessThanOrEqual(abs(produced - expected), 1, "\(sampleRate) Hz produced \(produced)")
        }
    }

    func testBothLanesShareOneConvertedHostTimeDomain() throws {
        let emitter = NativeLaneFrameEmitter(wireFormat: .live, hostTime: labTimebase)
        var byLane: [CaptureLane: [CaptureFrame]] = [:]
        for index in 0..<96 {
            for lane in CaptureLane.allCases {
                let frames = emitter.frames(from: [
                    deviceBuffer(
                        lane: lane,
                        callbackIndex: index,
                        sampleRate: 48_000,
                        frameCount: 1_024,
                        deviceEpoch: lane == .system ? 1 : 7
                    )
                ])
                byLane[lane, default: []] += frames
            }
        }

        let system = try XCTUnwrap(byLane[.system])
        let microphone = try XCTUnwrap(byLane[.microphone])
        XCTAssertEqual(system.count, 4)
        XCTAssertEqual(microphone.count, 4)
        // Two lanes captured at the same host instants must land on the same wire instants, or the
        // server mixes audio that never happened together.
        XCTAssertEqual(system.map(\.captureTimestampNS), microphone.map(\.captureTimestampNS))
        XCTAssertEqual(Set(system.map(\.deviceEpoch)), [1])
        XCTAssertEqual(Set(microphone.map(\.deviceEpoch)), [7])
    }

    func testUnusableCaptureInstantIsRefusedRatherThanFabricated() throws {
        let emitter = NativeLaneFrameEmitter(wireFormat: .live, hostTime: labTimebase)
        var frames: [CaptureFrame] = []
        for index in 0..<48 {
            frames += emitter.frames(from: [
                deviceBuffer(
                    lane: .system,
                    callbackIndex: index,
                    sampleRate: 48_000,
                    frameCount: 1_024,
                    // What a device reports when it never filled the host time in.
                    hostTicks: index == 10 ? 0 : nil
                )
            ])
        }

        XCTAssertEqual(frames.count, 2)
        XCTAssertEqual(Set(frames.map(\.sampleCount)), [8_000])
        // The audio of the refused buffer is gone; the hole is declared instead of being papered
        // over with a made-up capture instant.
        XCTAssertEqual(frames.map(\.discontinuity), [true, false])
        XCTAssertEqual(emitter.drainRejectedBufferCounts(), [.system: 1])
        XCTAssertEqual(emitter.drainRejectedBufferCounts(), [:])
        XCTAssertTrue(frames.allSatisfy { $0.captureTimestampNS > 0 })
    }

    func testTerminalFlushReleasesTheTrailingPartialFrameExactlyOnce() throws {
        let emitter = NativeLaneFrameEmitter(wireFormat: .live, hostTime: labTimebase)
        var frames: [CaptureFrame] = []
        for index in 0..<96 {
            frames += emitter.frames(from: [
                deviceBuffer(
                    lane: .system,
                    callbackIndex: index,
                    sampleRate: 48_000,
                    frameCount: 1_024
                )
            ])
        }
        XCTAssertEqual(frames.count, 4)

        let flushed = emitter.flush()
        XCTAssertEqual(flushed.count, 1)
        let tail = try XCTUnwrap(flushed.first)
        // 2.048 s of audio is four whole frames plus 0.048 s: the remainder leaves on the stop,
        // and only a stop may emit a short frame.
        XCTAssertEqual(tail.sampleCount, 32_768 - 4 * 8_000)
        XCTAssertEqual(tail.sampleRate, 16_000)
        XCTAssertEqual(tail.sequence, 4)
        XCTAssertEqual(tail.pcm16.count, tail.sampleCount * 2)
        XCTAssertTrue(emitter.flush().isEmpty)
    }

    func testADeviceTimelineGapMarksTheSplicedFrameAndKeepsFollowingTheDeviceClock() throws {
        let emitter = NativeLaneFrameEmitter(wireFormat: .live, hostTime: labTimebase)
        var frames: [CaptureFrame] = []
        // 24 contiguous callbacks, then six callbacks' worth of audio never arrives.
        for index in Array(0..<24) + Array(30..<54) {
            frames += emitter.frames(from: [
                deviceBuffer(
                    lane: .system,
                    callbackIndex: index,
                    sampleRate: 48_000,
                    frameCount: 1_024
                )
            ])
        }

        XCTAssertEqual(frames.count, 2)
        XCTAssertEqual(frames.map(\.discontinuity), [false, true])
        let step = Int64(frames[1].captureTimestampNS) - Int64(frames[0].captureTimestampNS)
        // The wire timeline follows the device clock across the gap instead of pretending the
        // spliced audio was continuous, so the step is one frame plus the missing 128 ms.
        let missingNS = Int64(6 * 1_024) * 1_000_000_000 / 48_000
        XCTAssertLessThanOrEqual(abs(step - (500_000_000 + missingNS)), 62_500, "step \(step)")
    }

    func testRealtimeCallbacksNeitherConvertHostTimeNorResample() throws {
        let callbackSources = try ["MicrophoneCapture", "SystemAudioTap"].map { name in
            try String(
                contentsOf: packageRoot()
                    .appendingPathComponent("Sources/MOSSCaptureCore/\(name).swift"),
                encoding: .utf8
            )
        }
        for source in callbackSources {
            XCTAssertFalse(source.contains("AVAudioConverter"))
            XCTAssertFalse(source.contains("AudioConvertHostTimeToNanos"))
        }
        let conversionStage = try String(
            contentsOf: packageRoot()
                .appendingPathComponent("Sources/MOSSCaptureCore/NativeLaneWireFormat.swift"),
            encoding: .utf8
        )
        XCTAssertTrue(conversionStage.contains("AVAudioConverter"))
        XCTAssertTrue(conversionStage.contains("AudioConvertHostTimeToNanos"))
        XCTAssertEqual(
            MicrophoneCapture.sourceVector.realtimeCallbackWork,
            ["copy native buffer", "enqueue monotonic first-sample time"]
        )
        XCTAssertEqual(
            SystemAudioTap.sourceVector.realtimeCallbackWork,
            ["copy native buffer", "enqueue monotonic first-sample time"]
        )
    }

    func testNativeDualCaptureSourceHandsOverItsFlushedTailAfterStop() throws {
        let system = RecordingNativeCaptureComponent(
            buffersOnStart: [
                deviceBuffer(lane: .system, callbackIndex: 0, sampleRate: 48_000, frameCount: 1_024)
            ]
        )
        let microphone = RecordingNativeCaptureComponent()
        let source = NativeDualCaptureSource(
            system: system,
            microphone: microphone,
            queue: RealTimeNativeAudioBufferQueue(capacity: 8),
            emitter: NativeLaneFrameEmitter(wireFormat: .live, hostTime: labTimebase)
        )

        try source.start(configuration: laneConfiguration())
        // A third of a frame: nothing may leave yet, because a short frame mid-stream would break
        // the steady cadence the server depends on.
        XCTAssertTrue(try source.pendingFrames().isEmpty)

        try source.stop(deadline: Date(timeIntervalSince1970: 1))
        let tail = try source.pendingFrames()

        XCTAssertEqual(tail.count, 1)
        XCTAssertEqual(tail.first?.lane, .system)
        XCTAssertEqual(tail.first?.sampleRate, 16_000)
        XCTAssertEqual(tail.first?.sampleCount, 1_024 / 3)
        XCTAssertTrue(try source.pendingFrames().isEmpty)
    }

    func testCaptureControllerPublishesTheSourcesFlushedTailOnStop() throws {
        let tailFrame = CaptureFrame(
            lane: .microphone,
            sequence: 9,
            sampleRate: 16_000,
            sampleCount: 341,
            captureTimestampNS: 1_500_000_000,
            deviceEpoch: 7,
            silent: false,
            discontinuity: false,
            pcm16: Data(repeating: 1, count: 682)
        )
        let source = TerminalTailCaptureSource(tail: [tailFrame])
        let transport = FakeCaptureTransportAdapter()
        let controller = CaptureController(
            source: source,
            transport: transport,
            keyStore: FakeCaptureKeyStoreAdapter(),
            clock: FakeCaptureClockAdapter(ticks: [100]),
            scheduler: FakeCaptureSchedulerAdapter(),
            health: FakeCaptureHealthAdapter()
        )
        let configuration = laneConfiguration()

        try controller.start(configuration: configuration)
        XCTAssertTrue(transport.publishedFrames.isEmpty)
        let stopped = try controller.stop(deadline: Date(timeIntervalSince1970: 1))

        // The last partial frame of a meeting only exists after the stop flushes the converters,
        // so a stop that does not drain silently discards it.
        XCTAssertEqual(transport.publishedFrames.map(\.sampleCount), [341])
        XCTAssertEqual(stopped.publishedFrameCount, 1)
        XCTAssertEqual(stopped.outbox.retainedFrames, 0)
    }

    /// Decision D-a partitions the vocabulary rather than renaming anything in it: a *failure*
    /// means the lane can no longer produce audio, a *degradation* means it lost some and kept
    /// producing. `macos_buffer_overrun` moved sides — it is minted in one place, for a lane that
    /// is still capturing while this process's drain falls behind — and the mailbox's own overflow
    /// stopped borrowing its name, because a lost *fact* is not lost audio.
    func testNativeLaneHealthStableCodeVocabularyIsClosed() throws {
        XCTAssertEqual(
            NativeLaneFailureCode.allCases.map(\.rawValue),
            [
                "macos_permission_denied",
                "macos_device_unavailable",
                "macos_io_stopped_abnormally",
                "macos_callback_stalled",
                "macos_unexpected_capture_error",
            ]
        )
        XCTAssertEqual(
            NativeLaneDegradationCode.allCases.map(\.rawValue),
            [
                "macos_buffer_overrun",
                "macos_health_facts_dropped",
            ]
        )
    }

    func testNativeLaneHealthMailboxOrderAndFirstCauseStickiness() throws {
        let health = NativeLaneHealth()
        let generation = health.beginGeneration()

        health.enqueue(.admitted, lane: .system, generation: generation)
        health.enqueue(.deviceEpoch(4), lane: .system, generation: generation)
        health.enqueue(.startFailed(.permissionDenied("screen capture permission")), lane: .system, generation: generation)
        health.enqueue(.startFailed(.deviceUnavailable("later device miss")), lane: .system, generation: generation)
        health.enqueue(.deviceEpoch(9), lane: .microphone, generation: generation)
        health.enqueue(.admitted, lane: .microphone, generation: generation)

        let statuses = health.statuses(running: true)
        let system = try XCTUnwrap(statuses.first { $0.lane == .system })
        let microphone = try XCTUnwrap(statuses.first { $0.lane == .microphone })

        XCTAssertEqual(system.state, "failed")
        XCTAssertEqual(system.failureCode, "macos_permission_denied")
        XCTAssertEqual(health.failure(for: .system)?.cause, "screen capture permission")
        XCTAssertEqual(microphone.state, "capturing")
        XCTAssertNil(microphone.failureCode)
        XCTAssertEqual(microphone.deviceEpoch, 9)
    }

    func testNativeLaneHealthGenerationFenceRejectsDelayedFactsAfterStop() throws {
        let health = NativeLaneHealth()
        let oldGeneration = health.beginGeneration()
        health.enqueue(.admitted, lane: .system, generation: oldGeneration)
        _ = health.statuses(running: true)

        health.invalidateGeneration()
        health.enqueue(.unexpectedCaptureError("late callback"), lane: .system, generation: oldGeneration)

        let system = try XCTUnwrap(
            health.statuses(running: false).first { $0.lane == .system }
        )
        XCTAssertEqual(system.state, "stopped")
        XCTAssertNil(system.failureCode)
        XCTAssertNil(health.failure(for: .system))
    }

    func testNativeLaneMailboxLinearizationBeatsCallbackTimestamp() throws {
        let health = NativeLaneHealth()
        let generation = health.beginGeneration()
        health.enqueue(
            .deviceEpoch(4),
            lane: .system,
            generation: generation,
            callbackMonotonicNS: 200
        )
        health.enqueue(
            .deviceEpoch(9),
            lane: .system,
            generation: generation,
            callbackMonotonicNS: 100
        )

        let batches = health.detachAcceptedFacts()
        let systemBatch = try XCTUnwrap(batches.first { $0.lane == .system })
        XCTAssertEqual(systemBatch.entries.map(\.mailboxOrder), [0, 1])
        XCTAssertEqual(systemBatch.entries.map(\.callbackMonotonicNS), [200, 100])
        health.applyDetachedFacts(batches)

        let system = try XCTUnwrap(
            health.statuses(running: true).first { $0.lane == .system }
        )
        XCTAssertEqual(system.deviceEpoch, 9)
    }

    /// A mailbox that overflows says so, in its own words.
    ///
    /// It used to say `macos_buffer_overrun` with `droppedFrames: 1` — the audio code, and the
    /// audio counter — for a loss of *health facts*, so an operator reading the heartbeat could
    /// not tell a lane that dropped a buffer of PCM from a lane whose reporting fell behind, and
    /// the PRD's accounting saw a frame of audio that had never existed. D-a gave the condition
    /// its own code; the fence stays, because after this point the mailbox's account is knowingly
    /// incomplete.
    func testNativeLaneMailboxOverflowIsItsOwnCodeAndNotAudioLoss() throws {
        let health = NativeLaneHealth(mailboxCapacity: 2)
        let generation = health.beginGeneration()
        health.enqueue(.admitted, lane: .system, generation: generation)
        health.enqueue(.deviceEpoch(7), lane: .system, generation: generation)
        health.enqueue(.deviceEpoch(8), lane: .system, generation: generation)
        health.enqueue(.deviceEpoch(9), lane: .system, generation: generation)

        let system = try XCTUnwrap(
            health.statuses(running: true).first { $0.lane == .system }
        )
        XCTAssertEqual(system.state, "degraded")
        XCTAssertEqual(system.deviceEpoch, 7)
        XCTAssertEqual(system.droppedFrames, 0)
        XCTAssertEqual(system.failureCode, "macos_health_facts_dropped")
    }

    func testNativeLaneReducerDeferredBatchCannotCrossGeneration() throws {
        let health = NativeLaneHealth()
        let oldGeneration = health.beginGeneration()
        health.enqueue(
            .unexpectedCaptureError("detached old callback"),
            lane: .system,
            generation: oldGeneration
        )
        let detached = health.detachAcceptedFacts()

        let currentGeneration = health.beginGeneration()
        health.enqueue(.admitted, lane: .system, generation: currentGeneration)
        health.applyDetachedFacts(detached)

        let system = try XCTUnwrap(
            health.statuses(running: true).first { $0.lane == .system }
        )
        XCTAssertEqual(system.state, "capturing")
        XCTAssertNil(system.failureCode)
    }

    func testNativeLaneHealthIgnoresNonFailureFacts() throws {
        let health = NativeLaneHealth()
        let generation = health.beginGeneration()

        health.enqueue(.permission(.undetermined), lane: .microphone, generation: generation)
        health.enqueue(.permission(.granted), lane: .microphone, generation: generation)
        health.enqueue(.bufferOverrun(droppedBuffers: 0), lane: .microphone, generation: generation)
        health.enqueue(.startFailed(.transportUnavailable("transient heartbeat")), lane: .microphone, generation: generation)
        health.enqueue(.admitted, lane: .microphone, generation: generation)

        let microphone = try XCTUnwrap(
            health.statuses(running: true).first { $0.lane == .microphone }
        )
        XCTAssertEqual(microphone.state, "capturing")
        XCTAssertNil(microphone.failureCode)
        XCTAssertNil(health.failure(for: .microphone))
    }

    func testNativeLaneHealthMapsNativeTerminalFactsToStableCodes() throws {
        let facts: [(NativeLaneFact, NativeLaneFailureCode)] = [
            (.startFailed(.deviceUnavailable("aggregate")), .deviceUnavailable),
            (.startFailed(.osStatus("AudioHardwareCreateProcessTap", -50)), .unexpectedCaptureError),
            (.ioStoppedAbnormally("HAL stopped"), .ioStoppedAbnormally),
            (.unexpectedCaptureError("uncaught native error"), .unexpectedCaptureError),
        ]

        for (fact, code) in facts {
            let health = NativeLaneHealth()
            let generation = health.beginGeneration()
            health.enqueue(fact, lane: .system, generation: generation)

            let system = try XCTUnwrap(
                health.statuses(running: true).first { $0.lane == .system }
            )
            XCTAssertEqual(system.state, "failed")
            XCTAssertEqual(system.failureCode, code.rawValue)
        }
    }

    /// The other half of the same table, and the reason there are two: every fact that leaves a
    /// lane producing audio maps to `degraded`, and no fact maps to both states.
    func testNativeLaneHealthMapsSurvivableFactsToDegradedCodes() throws {
        let facts: [(NativeLaneFact, NativeLaneDegradationCode)] = [
            (.bufferOverrun(droppedBuffers: 3), .bufferOverrun),
            (.healthFactsDropped(count: 1), .healthFactsDropped),
        ]

        for (fact, code) in facts {
            let health = NativeLaneHealth()
            let generation = health.beginGeneration()
            health.enqueue(fact, lane: .system, generation: generation)

            let system = try XCTUnwrap(
                health.statuses(running: true).first { $0.lane == .system }
            )
            XCTAssertEqual(system.state, "degraded")
            XCTAssertEqual(system.failureCode, code.rawValue)
            // Nothing here is a failure, so nothing here closes the lane: the projection's
            // failure — the field the server's terminal path reads — stays empty.
            XCTAssertNil(health.failure(for: .system))
        }
    }

    /// A degraded lane is still a lane that reports, and the failure that genuinely ends it must
    /// still arrive.
    ///
    /// The mailbox used to fence itself shut on the first overrun, because an overrun *was* the
    /// lane's terminal verdict and nothing after it could matter. D-a makes an overrun survivable,
    /// so that fence would have left the lane silent for the rest of the meeting while it kept
    /// producing audio — losing the device failure, the abnormal stop and every discontinuity that
    /// followed. The reclassification is only safe together with the fence's removal.
    func testAnOverrunLaneStillReportsTheFailureThatGenuinelyEndsIt() throws {
        let health = NativeLaneHealth()
        let generation = health.beginGeneration()
        health.enqueue(.admitted, lane: .system, generation: generation)
        health.enqueue(.bufferOverrun(droppedBuffers: 112), lane: .system, generation: generation)

        let degraded = try XCTUnwrap(
            health.statuses(running: true).first { $0.lane == .system }
        )
        XCTAssertEqual(degraded.state, "degraded")
        XCTAssertEqual(degraded.droppedFrames, 112)

        health.enqueue(.discontinuity(count: 2), lane: .system, generation: generation)
        health.enqueue(.bufferOverrun(droppedBuffers: 8), lane: .system, generation: generation)
        health.enqueue(.ioStoppedAbnormally("HAL stopped"), lane: .system, generation: generation)

        let failed = try XCTUnwrap(
            health.statuses(running: true).first { $0.lane == .system }
        )
        XCTAssertEqual(failed.state, "failed")
        XCTAssertEqual(failed.failureCode, "macos_io_stopped_abnormally")
        // The counters kept accruing across the degradation, and the failure did not erase them.
        XCTAssertEqual(failed.droppedFrames, 120)
        XCTAssertEqual(failed.discontinuities, 2)
    }

    /// The chain that killed F1 and F3, broken at the cheapest link, on the wire the server parses.
    ///
    /// The whole chain was: the lane overruns → the *client* calls it failed → the next heartbeat
    /// carries `state: "failed"` → the server's `_fail_lane` closes that lane for the meeting →
    /// every later frame on it answers 409 → the publish throws → the heartbeat stops → the helper
    /// lease expires 30 s later and the meeting is over. Every link behaves as designed; the
    /// product of them is a dead meeting for one dropped buffer. `_failed_lanes` keys on
    /// `state == "failed"` and nothing else, so a lane that says `degraded` never enters step 4 —
    /// which is why this is asserted on the serialized body rather than on the projection.
    func testTheHeartbeatCarriesAnOverrunLaneAsDegradedAndNotAsFailed() throws {
        let system = RecordingNativeCaptureComponent(
            buffersOnStart: [
                nativeBuffer(lane: .system, timestamp: 10, deviceEpoch: 1, samples: [0.5]),
                nativeBuffer(lane: .system, timestamp: 11, deviceEpoch: 1, samples: [0.25]),
                nativeBuffer(lane: .system, timestamp: 12, deviceEpoch: 1, samples: [0.75]),
            ]
        )
        let source = NativeDualCaptureSource(
            system: system,
            microphone: RecordingNativeCaptureComponent(
                buffersOnStart: [
                    nativeBuffer(lane: .microphone, timestamp: 11, deviceEpoch: 7, samples: [0])
                ]
            ),
            queue: RealTimeNativeAudioBufferQueue(capacity: 2),
            emitter: laboratoryEmitter()
        )
        let client = RecordingCaptureHTTPClient()
        let health = CaptureHTTPHealthAdapter(
            client: client,
            bearerToken: StaticCaptureBearerTokenAdapter(token: "capture-token"),
            instanceID: "boot-a",
            helperVersion: "0.1.0"
        )
        let configuration = laneConfiguration()

        try source.start(configuration: configuration)
        _ = try source.pendingFrames()
        try health.emit(
            status: CaptureStatus(
                running: true,
                sessionID: configuration.sessionID,
                lanes: source.status(),
                publishedFrameCount: 1,
                lastHealthSequence: 1
            ),
            configuration: configuration,
            sentMonotonicNS: 900
        )

        let body = try jsonBody(try XCTUnwrap(client.requests.first))
        let lanes = try XCTUnwrap(body["lanes"] as? [String: [String: Any]])
        let systemLane = try XCTUnwrap(lanes["system"])
        XCTAssertEqual(systemLane["state"] as? String, "degraded")
        XCTAssertEqual(systemLane["failure_code"] as? String, "macos_buffer_overrun")
        // How much was lost is the report. The count is what an operator and the accounting need;
        // the lane's life is not the price of saying it.
        XCTAssertEqual(systemLane["dropped_frames"] as? Int, 1)
        XCTAssertEqual(try XCTUnwrap(lanes["microphone"])["state"] as? String, "capturing")
        // The top-level state is the whole helper's, and it is unchanged: the client has never
        // sent `failed` there, and one degraded lane is not a degraded capture.
        XCTAssertEqual(body["state"] as? String, "capturing")
    }

    func testRealtimeCallbacksOnlyCopyAndEnqueueNativeBuffers() throws {
        let root = packageRoot()
        let system = try String(
            contentsOf: root.appendingPathComponent("Sources/MOSSCaptureCore/SystemAudioTap.swift"),
            encoding: .utf8
        )
        let microphone = try String(
            contentsOf: root.appendingPathComponent("Sources/MOSSCaptureCore/MicrophoneCapture.swift"),
            encoding: .utf8
        )
        let callbackSources = system + microphone

        XCTAssertTrue(callbackSources.contains("enqueueFromRealtimeCallback"))
        XCTAssertFalse(callbackSources.contains("URLSession"))
        XCTAssertFalse(callbackSources.contains("SecItemAdd"))
        XCTAssertFalse(callbackSources.contains("FileHandle"))
        XCTAssertFalse(callbackSources.contains("print("))
        XCTAssertFalse(callbackSources.contains("JSONEncoder"))
    }

    func testHTTPTransportPostsStrictV2FramesWithBearerHeaderOnly() throws {
        let client = RecordingCaptureHTTPClient()
        let transport = CaptureV2HTTPTransportAdapter(
            client: client,
            bearerToken: StaticCaptureBearerTokenAdapter(token: "capture-token")
        )
        let configuration = CaptureConfiguration(
            sessionID: "session-a",
            serverURL: URL(string: "https://moss.example")!
        )

        try transport.publish(
            frame: CaptureFrame(
                lane: .system,
                sequence: 3,
                sampleRate: 16_000,
                sampleCount: 2,
                captureTimestampNS: 123,
                deviceEpoch: 9,
                silent: false,
                discontinuity: true,
                pcm16: Data([1, 0, 2, 0])
            ),
            configuration: configuration
        )

        let request = try XCTUnwrap(client.requests.first)
        let body = try jsonBody(request)
        XCTAssertEqual(request.httpMethod, "POST")
        XCTAssertEqual(request.url?.absoluteString, "https://moss.example/api/live/sessions/session-a/frames")
        XCTAssertNil(request.url?.query)
        XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer capture-token")
        XCTAssertEqual(request.value(forHTTPHeaderField: "Content-Type"), "application/json")
        XCTAssertEqual(Set(body.keys), [
            "lane",
            "sequence",
            "capture_timestamp_ns",
            "device_epoch",
            "silent",
            "discontinuity",
            "sample_rate",
            "sample_count",
            "pcm_base64",
        ])
        XCTAssertEqual(body["lane"] as? String, "system")
        XCTAssertEqual(body["sequence"] as? Int, 3)
        XCTAssertEqual(body["capture_timestamp_ns"] as? Int, 123)
        XCTAssertEqual(body["device_epoch"] as? Int, 9)
        XCTAssertEqual(body["silent"] as? Bool, false)
        XCTAssertEqual(body["discontinuity"] as? Bool, true)
        XCTAssertEqual(body["sample_rate"] as? Int, 16_000)
        XCTAssertEqual(body["sample_count"] as? Int, 2)
        XCTAssertEqual(body["pcm_base64"] as? String, Data([1, 0, 2, 0]).base64EncodedString())
        XCTAssertFalse(String(data: request.httpBody ?? Data(), encoding: .utf8)?.contains("capture-token") ?? true)
    }

    func testHTTPHealthPostsVersionedHeartbeatWithoutBearerLeakage() throws {
        let client = RecordingCaptureHTTPClient()
        let health = CaptureHTTPHealthAdapter(
            client: client,
            bearerToken: StaticCaptureBearerTokenAdapter(token: "capture-token"),
            instanceID: "boot-a",
            helperVersion: "0.1.0"
        )
        let configuration = CaptureConfiguration(
            sessionID: "session-a",
            serverURL: URL(string: "https://moss.example")!
        )
        let status = CaptureStatus(
            running: true,
            sessionID: "session-a",
            lanes: [
                CaptureLaneStatus(lane: .system, sequence: 4, deviceEpoch: 2, state: "capturing"),
                CaptureLaneStatus(lane: .microphone, sequence: 6, deviceEpoch: 8, state: "capturing"),
            ],
            publishedFrameCount: 10,
            lastHealthSequence: 5
        )

        try health.emit(status: status, configuration: configuration, sentMonotonicNS: 900)

        let request = try XCTUnwrap(client.requests.first)
        let body = try jsonBody(request)
        let lanes = try XCTUnwrap(body["lanes"] as? [String: [String: Any]])
        let system = try XCTUnwrap(lanes["system"])
        let microphone = try XCTUnwrap(lanes["microphone"])
        XCTAssertEqual(request.url?.absoluteString, "https://moss.example/api/live/sessions/session-a/heartbeat")
        XCTAssertNil(request.url?.query)
        XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer capture-token")
        XCTAssertEqual(Set(body.keys), [
            "schema",
            "instance_id",
            "sequence",
            "sent_monotonic_ns",
            "helper_version",
            "state",
            "lanes",
        ])
        XCTAssertEqual(body["schema"] as? String, "moss-live-helper-health.v1")
        XCTAssertEqual(body["instance_id"] as? String, "boot-a")
        XCTAssertEqual(body["sequence"] as? Int, 5)
        XCTAssertEqual(body["sent_monotonic_ns"] as? Int, 900)
        XCTAssertEqual(body["helper_version"] as? String, "0.1.0")
        XCTAssertEqual(body["state"] as? String, "capturing")
        XCTAssertEqual(Set(lanes.keys), ["system", "microphone"])
        XCTAssertEqual(system["device_epoch"] as? Int, 2)
        XCTAssertEqual(microphone["device_epoch"] as? Int, 8)
        XCTAssertTrue(system["failure_code"] is NSNull)
        XCTAssertTrue(microphone["failure_code"] is NSNull)
        XCTAssertFalse(String(data: request.httpBody ?? Data(), encoding: .utf8)?.contains("capture-token") ?? true)
    }

    func testHTTPHealthSerializesTypedLaneFailureCode() throws {
        let client = RecordingCaptureHTTPClient()
        let health = CaptureHTTPHealthAdapter(
            client: client,
            bearerToken: StaticCaptureBearerTokenAdapter(token: "capture-token"),
            instanceID: "boot-a",
            helperVersion: "0.1.0"
        )
        let status = CaptureStatus(
            running: true,
            sessionID: "session-a",
            lanes: [
                CaptureLaneStatus(
                    lane: .system,
                    sequence: 4,
                    deviceEpoch: 2,
                    state: "failed",
                    droppedFrames: 1,
                    discontinuities: 2,
                    failureCode: "macos_permission_denied"
                ),
                CaptureLaneStatus(lane: .microphone, sequence: 6, deviceEpoch: 8, state: "capturing"),
            ],
            publishedFrameCount: 10,
            lastHealthSequence: 5
        )

        try health.emit(
            status: status,
            configuration: CaptureConfiguration(
                sessionID: "session-a",
                serverURL: URL(string: "https://moss.example")!
            ),
            sentMonotonicNS: 900
        )

        let request = try XCTUnwrap(client.requests.first)
        let body = try jsonBody(request)
        let lanes = try XCTUnwrap(body["lanes"] as? [String: [String: Any]])
        let system = try XCTUnwrap(lanes["system"])
        let microphone = try XCTUnwrap(lanes["microphone"])
        XCTAssertEqual(system["state"] as? String, "failed")
        XCTAssertEqual(system["dropped_frames"] as? Int, 1)
        XCTAssertEqual(system["discontinuities"] as? Int, 2)
        XCTAssertEqual(system["failure_code"] as? String, "macos_permission_denied")
        XCTAssertTrue(microphone["failure_code"] is NSNull)
    }

    func testHTTPTransportRejectsMissingBearerBeforeRequest() throws {
        let client = RecordingCaptureHTTPClient()
        let transport = CaptureV2HTTPTransportAdapter(
            client: client,
            bearerToken: StaticCaptureBearerTokenAdapter(token: nil)
        )

        XCTAssertThrowsError(
            try transport.publish(
                frame: CaptureFrame(
                    lane: .system,
                    sequence: 0,
                    sampleRate: 16_000,
                    sampleCount: 1,
                    captureTimestampNS: 0,
                    deviceEpoch: 0,
                    silent: true,
                    discontinuity: false,
                    pcm16: Data([0, 0])
                ),
                configuration: CaptureConfiguration(
                    sessionID: "session-a",
                    serverURL: URL(string: "https://moss.example")!
                )
            )
        ) { error in
            XCTAssertEqual(error as? CaptureHTTPTransportError, .missingCaptureBearer)
        }
        XCTAssertTrue(client.requests.isEmpty)
    }

    func testHTTPTransportAndHealthBuildPinnedClientFromStoredPin() throws {
        let provider = RecordingCaptureHTTPClientProvider()
        let transport = CaptureV2HTTPTransportAdapter(
            clientProvider: provider,
            certificatePin: StaticCaptureCertificatePinAdapter(pin: String(repeating: "a", count: 64)),
            bearerToken: StaticCaptureBearerTokenAdapter(token: "capture-token")
        )
        let health = CaptureHTTPHealthAdapter(
            clientProvider: provider,
            certificatePin: StaticCaptureCertificatePinAdapter(pin: String(repeating: "a", count: 64)),
            bearerToken: StaticCaptureBearerTokenAdapter(token: "capture-token"),
            instanceID: "instance-a",
            helperVersion: "0.1.0"
        )
        let pin = String(repeating: "a", count: 64)
        let configuration = CaptureConfiguration(
            sessionID: "session-a",
            serverURL: URL(string: "https://moss.example")!
        )

        try transport.publish(
            frame: CaptureFrame(
                lane: .system,
                sequence: 0,
                sampleRate: 16_000,
                sampleCount: 1,
                captureTimestampNS: 0,
                deviceEpoch: 0,
                silent: true,
                discontinuity: false,
                pcm16: Data([0, 0])
            ),
            configuration: configuration
        )
        try health.emit(
            status: CaptureStatus(
                running: true,
                sessionID: "session-a",
                lanes: [],
                publishedFrameCount: 0,
                lastHealthSequence: 0
            ),
            configuration: configuration,
            sentMonotonicNS: 1
        )

        XCTAssertEqual(provider.requestedPins, [pin, pin])
        XCTAssertEqual(provider.client.requests.map(\.url?.path), [
            "/api/live/sessions/session-a/frames",
            "/api/live/sessions/session-a/heartbeat",
        ])
    }

    func testPinnedHTTPProviderRejectsMissingCertificatePinBeforeRequest() throws {
        let provider = RecordingCaptureHTTPClientProvider()
        let transport = CaptureV2HTTPTransportAdapter(
            clientProvider: provider,
            certificatePin: StaticCaptureCertificatePinAdapter(pin: nil),
            bearerToken: StaticCaptureBearerTokenAdapter(token: "capture-token")
        )

        XCTAssertThrowsError(
            try transport.publish(
                frame: CaptureFrame(
                    lane: .system,
                    sequence: 0,
                    sampleRate: 16_000,
                    sampleCount: 1,
                    captureTimestampNS: 0,
                    deviceEpoch: 0,
                    silent: true,
                    discontinuity: false,
                    pcm16: Data([0, 0])
                ),
                configuration: CaptureConfiguration(
                    sessionID: "session-a",
                    serverURL: URL(string: "https://moss.example")!
                )
            )
        ) { error in
            XCTAssertEqual(error as? CaptureHTTPTransportError, .missingCertificatePin)
        }
        XCTAssertTrue(provider.client.requests.isEmpty)
    }

    func testPairingExchangeUsesServerPairingThenAuthenticatedSessionContract() throws {
        let client = QueuedCaptureHTTPClient(responses: [
            CaptureHTTPResponse(
                statusCode: 200,
                body: try JSONEncoder().encode(TestPairingResponseBody(
                    deviceID: "device-a",
                    deviceToken: "device-token"
                ))
            ),
            CaptureHTTPResponse(
                statusCode: 200,
                body: try JSONEncoder().encode(TestSessionResponseBody(
                    id: "session-a",
                    ownerDeviceID: "device-a",
                    viewToken: "view-token"
                ))
            ),
        ])
        let exchange = URLSessionCapturePairingExchangeAdapter(
            client: client,
            deviceIdentity: StaticCaptureDeviceIdentityAdapter(deviceID: "device-a")
        )

        let result = try exchange.pair(
            serverURL: URL(string: "https://moss.example")!,
            pairingPayload: Data("mtd1.secret.\(String(repeating: "a", count: 64))".utf8)
        )

        XCTAssertEqual(result.deviceID, "device-a")
        XCTAssertEqual(result.sessionID, "session-a")
        XCTAssertEqual(result.viewToken, "view-token")
        XCTAssertEqual(result.captureBearerToken, "device-token")
        XCTAssertEqual(result.certificatePinSHA256Hex, String(repeating: "a", count: 64))
        XCTAssertEqual(client.requests.count, 2)
        let pairingRequest = try XCTUnwrap(client.requests.first)
        let sessionRequest = try XCTUnwrap(client.requests.dropFirst().first)
        let pairingBody = try jsonBody(pairingRequest)
        XCTAssertEqual(pairingRequest.httpMethod, "POST")
        XCTAssertEqual(pairingRequest.url?.absoluteString, "https://moss.example/api/live/pairings")
        XCTAssertEqual(pairingRequest.value(forHTTPHeaderField: "Content-Type"), "application/json")
        XCTAssertEqual(pairingRequest.value(forHTTPHeaderField: "Accept"), "application/json")
        XCTAssertNil(pairingRequest.value(forHTTPHeaderField: "Authorization"))
        XCTAssertEqual(pairingBody["device_id"] as? String, "device-a")
        XCTAssertEqual(
            pairingBody["pairing_payload"] as? String,
            "mtd1.secret.\(String(repeating: "a", count: 64))"
        )
        XCTAssertEqual(sessionRequest.httpMethod, "POST")
        XCTAssertEqual(sessionRequest.url?.absoluteString, "https://moss.example/api/live/sessions")
        XCTAssertEqual(sessionRequest.value(forHTTPHeaderField: "Authorization"), "Bearer device-token")
        XCTAssertEqual(sessionRequest.value(forHTTPHeaderField: "Accept"), "application/json")
        XCTAssertNil(sessionRequest.httpBody)
        XCTAssertFalse(
            String(decoding: pairingRequest.httpBody ?? Data(), as: UTF8.self).contains("device-token")
        )
    }

    func testPairingExchangeRejectsMalformedPayloadBeforeRequest() throws {
        let client = QueuedCaptureHTTPClient(responses: [])
        let exchange = URLSessionCapturePairingExchangeAdapter(
            client: client,
            deviceIdentity: StaticCaptureDeviceIdentityAdapter(deviceID: "device-a")
        )

        let invalidCases: [(String, CaptureSecurityError)] = [
            ("", .missingPairingPayload),
            ("secret.\(String(repeating: "a", count: 64))", .invalidPairingPayload),
            ("mtd1.secret", .invalidPairingPayload),
            ("mtd1..\(String(repeating: "a", count: 64))", .invalidPairingPayload),
            ("mtd1.secret.\(String(repeating: "a", count: 64)).extra", .invalidPairingPayload),
            ("mtd1.secret.\(String(repeating: "a", count: 63))", .invalidPinnedHash),
            ("mtd1.secret.\(String(repeating: "g", count: 64))", .invalidPinnedHash),
        ]

        for invalidCase in invalidCases {
            XCTAssertThrowsError(
                try exchange.pair(
                    serverURL: URL(string: "https://moss.example")!,
                    pairingPayload: Data(invalidCase.0.utf8)
                ),
                invalidCase.0
            ) { error in
                XCTAssertEqual(error as? CaptureSecurityError, invalidCase.1)
            }
        }
        XCTAssertTrue(client.requests.isEmpty)
    }

    func testPairingPayloadTrimsHowItWasTypedAndSendsExactlyWhatItParsed() throws {
        // The payload is pasted into `mtd-capture pair` and ended with Ctrl-D. A Return pressed
        // first, a terminal that ends lines with CRLF, or a paste that carries indentation all put
        // characters around the payload that are not part of it.
        let pin = String(repeating: "a", count: 64)
        let canonical = "mtd1.secret.\(pin)"
        let typedForms: [(String, String)] = [
            ("Return before Ctrl-D", canonical + "\n"),
            ("CRLF terminal", canonical + "\r\n"),
            ("indented paste", "  \t" + canonical + " \n"),
            ("uppercase pin with a newline", "mtd1.secret.\(pin.uppercased())\n"),
        ]

        for (label, typed) in typedForms {
            let client = QueuedCaptureHTTPClient(responses: [
                CaptureHTTPResponse(
                    statusCode: 200,
                    body: try JSONEncoder().encode(TestPairingResponseBody(
                        deviceID: "device-a",
                        deviceToken: "device-token"
                    ))
                ),
                CaptureHTTPResponse(
                    statusCode: 200,
                    body: try JSONEncoder().encode(TestSessionResponseBody(
                        id: "session-a",
                        ownerDeviceID: "device-a",
                        viewToken: "view-token"
                    ))
                ),
            ])
            let exchange = URLSessionCapturePairingExchangeAdapter(
                client: client,
                deviceIdentity: StaticCaptureDeviceIdentityAdapter(deviceID: "device-a")
            )

            let result = try exchange.pair(
                serverURL: URL(string: "https://moss.example")!,
                pairingPayload: Data(typed.utf8)
            )

            XCTAssertEqual(result.sessionID, "session-a", label)
            XCTAssertEqual(result.certificatePinSHA256Hex, pin, label)
            // The server sees only what was transmitted, so the transmitted payload must be the
            // canonical string the pin was validated from — not the bytes that arrived on stdin.
            let pairingBody = try jsonBody(try XCTUnwrap(client.requests.first, label))
            XCTAssertEqual(pairingBody["pairing_payload"] as? String, canonical, label)
        }
    }

    func testPairingPayloadWhitespaceFaultsAreReportedAgainstThePayloadNotTheCertificate() throws {
        // Whitespace that survives the trim is inside a field: the payload itself is broken, and
        // saying `invalidPinnedHash` would send the operator to look at the server's certificate.
        let pin = String(repeating: "a", count: 64)
        let client = QueuedCaptureHTTPClient(responses: [])
        let exchange = URLSessionCapturePairingExchangeAdapter(
            client: client,
            deviceIdentity: StaticCaptureDeviceIdentityAdapter(deviceID: "device-a")
        )

        let whitespaceCases: [(String, String, CaptureSecurityError)] = [
            ("nothing but whitespace", " \t\n ", .missingPairingPayload),
            ("space inside the secret", "mtd1.sec ret.\(pin)", .invalidPairingPayload),
            (
                "pin wrapped across two lines",
                "mtd1.secret.\(String(repeating: "a", count: 32))\n\(String(repeating: "a", count: 32))",
                .invalidPairingPayload
            ),
            ("space inside the prefix", "mtd 1.secret.\(pin)", .invalidPairingPayload),
        ]

        for (label, typed, expected) in whitespaceCases {
            XCTAssertThrowsError(
                try exchange.pair(
                    serverURL: URL(string: "https://moss.example")!,
                    pairingPayload: Data(typed.utf8)
                ),
                label
            ) { error in
                XCTAssertEqual(error as? CaptureSecurityError, expected, label)
            }
        }
        XCTAssertTrue(client.requests.isEmpty)
    }

    func testPairingExchangeStopsBeforeSessionWhenPairingFails() throws {
        let client = QueuedCaptureHTTPClient(responses: [
            CaptureHTTPResponse(statusCode: 403, body: Data())
        ])
        let exchange = URLSessionCapturePairingExchangeAdapter(
            client: client,
            deviceIdentity: StaticCaptureDeviceIdentityAdapter(deviceID: "device-a")
        )

        XCTAssertThrowsError(
            try exchange.pair(
                serverURL: URL(string: "https://moss.example")!,
                pairingPayload: Data("mtd1.secret.\(String(repeating: "a", count: 64))".utf8)
            )
        ) { error in
            XCTAssertEqual(error as? CaptureHTTPTransportError, .nonSuccessStatus(403))
        }
        XCTAssertEqual(client.requests.count, 1)
        XCTAssertEqual(client.requests.first?.url?.absoluteString, "https://moss.example/api/live/pairings")
    }

    func testPairingExchangeBuildsHTTPSClientFromPayloadPin() throws {
        let client = QueuedCaptureHTTPClient(responses: [
            CaptureHTTPResponse(
                statusCode: 200,
                body: try JSONEncoder().encode(TestPairingResponseBody(
                    deviceID: "device-a",
                    deviceToken: "device-token"
                ))
            ),
            CaptureHTTPResponse(
                statusCode: 200,
                body: try JSONEncoder().encode(TestSessionResponseBody(
                    id: "session-a",
                    ownerDeviceID: "device-a",
                    viewToken: "view-token"
                ))
            ),
        ])
        let provider = RecordingCaptureHTTPClientProvider(client: client)
        let exchange = URLSessionCapturePairingExchangeAdapter(
            clientProvider: provider,
            deviceIdentity: StaticCaptureDeviceIdentityAdapter(deviceID: "device-a")
        )
        let pin = String(repeating: "B", count: 64)

        let result = try exchange.pair(
            serverURL: URL(string: "https://moss.example")!,
            pairingPayload: Data("mtd1.secret.\(pin)".utf8)
        )

        XCTAssertEqual(provider.requestedPins, [pin.lowercased()])
        XCTAssertEqual(result.certificatePinSHA256Hex, pin.lowercased())
        XCTAssertEqual(client.requests.count, 2)
    }

    func testDispatcherStoresPairingPinForSubsequentHTTPSClients() throws {
        let source = FakeCaptureSourceAdapter(frames: [
            CaptureFrame(
                lane: .system,
                sequence: 0,
                sampleRate: 16_000,
                sampleCount: 1,
                captureTimestampNS: 0,
                deviceEpoch: 0,
                silent: true,
                discontinuity: false,
                pcm16: Data([0, 0])
            )
        ])
        let transport = RecordingCaptureTransportAdapter()
        let controller = CaptureController(
            source: source,
            transport: transport,
            keyStore: FakeCaptureKeyStoreAdapter(),
            clock: FakeCaptureClockAdapter(ticks: [1]),
            scheduler: FakeCaptureSchedulerAdapter(),
            health: FakeCaptureHealthAdapter()
        )
        let pin = String(repeating: "c", count: 64)
        let pinStore = RecordingCaptureCertificatePinStore()
        let dispatcher = ControlCommandDispatcher(
            controller: controller,
            pairingExchange: StaticPairingExchange(
                result: CapturePairingResult(
                    sessionID: "session-a",
                    captureBearerToken: "capture-token",
                    certificatePinSHA256Hex: pin
                )
            ),
            certificatePinStore: pinStore
        )

        _ = try dispatcher.dispatch(
            ControlChannelRequest(
                command: "pair",
                serverURL: URL(string: "https://moss.example")!,
                pairingPayload: Data("mtd1.secret.\(pin)".utf8)
            )
        )

        XCTAssertEqual(pinStore.savedPins, [pin])
        XCTAssertTrue(transport.configurations.isEmpty)
    }

    func testFileSecretStorePersistsRestartSafeAuthorityWithPrivateMode() throws {
        let path = temporarySecretStorePath()
        defer { try? FileManager.default.removeItem(at: URL(fileURLWithPath: path).deletingLastPathComponent()) }
        let store = try FileCaptureSecretStore(path: path)
        let pin = String(repeating: "d", count: 64)
        let serverURL = URL(string: "https://moss.example")!

        try store.saveControlSecret("control-secret")
        try store.saveCaptureBearerToken("capture-token")
        try store.saveCaptureCertificatePin(pin)
        try store.saveCaptureServerURL(serverURL)
        try store.saveCaptureSessionID("session-a")
        try store.saveCaptureViewToken("view-token")
        let deviceID = try store.loadDeviceID()

        let reloaded = try FileCaptureSecretStore(path: path)
        XCTAssertEqual(try reloaded.loadControlSecret(), "control-secret")
        XCTAssertEqual(try reloaded.loadCaptureBearerToken(), "capture-token")
        XCTAssertEqual(try reloaded.loadCaptureCertificatePin(), pin)
        XCTAssertEqual(try reloaded.loadCaptureServerURL(), serverURL)
        XCTAssertEqual(try reloaded.loadCaptureSessionID(), "session-a")
        XCTAssertEqual(try reloaded.loadCaptureViewToken(), "view-token")
        XCTAssertEqual(try reloaded.loadDeviceID(), deviceID)
        XCTAssertEqual(try fileMode(at: path), 0o600)
    }

    func testDefaultSecretStoreKeepsItsDirectoryAndDocumentPrivate() throws {
        let home = FileManager.default.temporaryDirectory
            .appendingPathComponent("moss-home-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: home, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: home) }
        let store = try CaptureSecretStoreSelection.makeDefault(
            environment: [:],
            homeDirectory: home.path
        )
        let path = try XCTUnwrap((store as? FileCaptureSecretStore)?.path)
        let directory = URL(fileURLWithPath: path).deletingLastPathComponent().path

        // resolving the store must not touch the home directory; only writing a secret does
        XCTAssertFalse(FileManager.default.fileExists(atPath: directory))
        try store.saveCaptureBearerToken("capture-token")
        XCTAssertEqual(try fileMode(at: directory), 0o700)
        XCTAssertEqual(try fileMode(at: path), 0o600)
        XCTAssertEqual(try fileOwner(at: path), getuid())
        XCTAssertEqual(try FileManager.default.contentsOfDirectory(atPath: directory), ["secrets.json"])

        // a directory someone widened cannot expose the 0600 document, so it is repaired
        XCTAssertEqual(chmod(directory, 0o755), 0)
        try store.saveCaptureSessionID("session-a")
        XCTAssertEqual(try fileMode(at: directory), 0o700)

        // a widened document may already have been read, so it is refused instead
        XCTAssertEqual(chmod(path, 0o644), 0)
        XCTAssertThrowsError(try FileCaptureSecretStore(path: path)) { error in
            XCTAssertEqual(error as? CaptureSecurityError, .secretStorePathNotPrivate)
        }
        XCTAssertEqual(chmod(path, 0o600), 0)
        XCTAssertEqual(
            try FileCaptureSecretStore(path: path).loadCaptureBearerToken(),
            "capture-token"
        )

        XCTAssertThrowsError(try FileCaptureSecretStore(path: path, expectedUID: getuid() + 1)) { error in
            XCTAssertEqual(
                error as? CaptureSecurityError,
                .secretStoreOwnerMismatch(expected: getuid() + 1, actual: getuid())
            )
        }
    }

    func testSecretStoreSavePublishesAReplacementRatherThanRewritingTheLiveDocument() throws {
        let path = temporarySecretStorePath()
        defer { try? FileManager.default.removeItem(at: URL(fileURLWithPath: path).deletingLastPathComponent()) }
        let directory = URL(fileURLWithPath: path).deletingLastPathComponent().path
        let store = try FileCaptureSecretStore(path: path)

        try store.saveControlSecret("control-secret")
        let firstInode = try fileInode(at: path)
        try store.saveCaptureBearerToken("capture-token")
        let secondInode = try fileInode(at: path)

        XCTAssertNotEqual(
            firstInode,
            secondInode,
            "a save must publish a renamed replacement, never truncate the live document"
        )
        XCTAssertEqual(try fileMode(at: path), 0o600)
        XCTAssertEqual(
            try FileManager.default.contentsOfDirectory(atPath: directory),
            ["secrets.json"],
            "no temporary residue may survive a save"
        )
        let reloaded = try FileCaptureSecretStore(path: path)
        XCTAssertEqual(try reloaded.loadControlSecret(), "control-secret")
        XCTAssertEqual(try reloaded.loadCaptureBearerToken(), "capture-token")
    }

    func testDispatcherPersistsPairingAuthorityAndReloadsStartConfiguration() throws {
        let path = temporarySecretStorePath()
        defer { try? FileManager.default.removeItem(at: URL(fileURLWithPath: path).deletingLastPathComponent()) }
        let store = try FileCaptureSecretStore(path: path)
        try store.saveControlSecret("control-secret")
        let serverURL = URL(string: "https://moss.example")!
        let pin = String(repeating: "e", count: 64)
        let firstController = CaptureController(
            source: FakeCaptureSourceAdapter(frames: []),
            transport: RecordingCaptureTransportAdapter(),
            keyStore: store,
            clock: FakeCaptureClockAdapter(ticks: [1]),
            scheduler: FakeCaptureSchedulerAdapter(),
            health: FakeCaptureHealthAdapter()
        )
        let firstDispatcher = ControlCommandDispatcher(
            controller: firstController,
            pairingExchange: StaticPairingExchange(
                result: CapturePairingResult(
                    sessionID: "session-persisted",
                    viewToken: "view-token",
                    captureBearerToken: "capture-token",
                    certificatePinSHA256Hex: pin
                )
            ),
            captureTokenStore: store,
            certificatePinStore: store,
            sessionStore: store
        )

        let pairResponse = try firstDispatcher.dispatch(ControlChannelRequest(
            command: "pair",
            serverURL: serverURL,
            pairingPayload: Data("mtd1.secret.\(pin)".utf8)
        ))

        let encodedResponse = String(decoding: try JSONEncoder().encode(pairResponse), as: UTF8.self)
        XCTAssertEqual(pairResponse.sessionID, "session-persisted")
        XCTAssertEqual(pairResponse.portalURL, serverURL.appendingPathComponent("live"))
        XCTAssertNil(pairResponse.portalURL?.query)
        XCTAssertNil(pairResponse.portalURL?.fragment)
        XCTAssertFalse(encodedResponse.contains("view-token"))
        XCTAssertFalse(encodedResponse.contains("capture-token"))
        XCTAssertFalse(encodedResponse.contains("?"))
        XCTAssertFalse(encodedResponse.contains("#"))
        XCTAssertEqual(try store.loadCaptureServerURL(), serverURL)
        XCTAssertEqual(try store.loadCaptureSessionID(), "session-persisted")
        XCTAssertEqual(try store.loadCaptureViewToken(), "view-token")

        let transport = RecordingCaptureTransportAdapter()
        let secondController = CaptureController(
            source: FakeCaptureSourceAdapter(frames: [
                CaptureFrame(
                    lane: .system,
                    sequence: 0,
                    sampleRate: 16_000,
                    sampleCount: 1,
                    captureTimestampNS: 0,
                    deviceEpoch: 0,
                    silent: true,
                    discontinuity: false,
                    pcm16: Data([0, 0])
                )
            ]),
            transport: transport,
            keyStore: store,
            clock: FakeCaptureClockAdapter(ticks: [2]),
            scheduler: FakeCaptureSchedulerAdapter(),
            health: FakeCaptureHealthAdapter()
        )
        let secondDispatcher = ControlCommandDispatcher(
            controller: secondController,
            pairingExchange: StaticPairingExchange(result: CapturePairingResult(sessionID: "unused")),
            sessionStore: store
        )

        _ = try secondDispatcher.dispatch(ControlChannelRequest(command: "start", label: "restart"))

        XCTAssertEqual(transport.configurations.map(\.sessionID), ["session-persisted"])
        XCTAssertEqual(transport.configurations.map(\.serverURL), [serverURL])
        XCTAssertEqual(transport.configurations.map(\.label), ["restart"])
    }

    func testAppDispatcherOwnsHandoffAndAnswersWithNonSecretViewAuthorityStatus() throws {
        let path = temporarySecretStorePath()
        defer { try? FileManager.default.removeItem(at: URL(fileURLWithPath: path).deletingLastPathComponent()) }
        let store = try FileCaptureSecretStore(path: path)
        let serverURL = URL(string: "https://moss.example/?token=leak#fragment")!
        try store.saveCaptureServerURL(serverURL)
        try store.saveCaptureSessionID("session-handoff")
        try store.saveCaptureViewToken("view-token-secret")
        var copiedTokens: [String] = []
        let dispatcher = ControlCommandDispatcher(
            controller: CaptureController.fakeForLocalDevelopment(),
            pairingExchange: StaticPairingExchange(result: CapturePairingResult(sessionID: "unused")),
            sessionStore: store,
            portalHandoff: PasteboardCapturePortalHandoff(sessionStore: store) { viewToken in
                copiedTokens.append(viewToken)
                return true
            }
        )

        let response = try dispatcher.dispatch(ControlChannelRequest(command: "handoff"))

        XCTAssertEqual(copiedTokens, ["view-token-secret"])
        XCTAssertEqual(
            response,
            ControlChannelResponse(
                ok: true,
                sessionID: "session-handoff",
                portalURL: URL(string: "https://moss.example/live")!,
                viewAuthority: "copied-to-pasteboard"
            )
        )
        let encoded = String(decoding: try JSONEncoder().encode(response), as: UTF8.self)
        XCTAssertFalse(encoded.contains("view-token-secret"))
        XCTAssertFalse(encoded.contains("?"))
        XCTAssertFalse(encoded.contains("#"))
    }

    func testHandoffFailsTypedWhenAuthorityIsMissingPasteboardFailsOrNoAdapterIsInjected() throws {
        let path = temporarySecretStorePath()
        defer { try? FileManager.default.removeItem(at: URL(fileURLWithPath: path).deletingLastPathComponent()) }
        let store = try FileCaptureSecretStore(path: path)
        try store.saveCaptureServerURL(URL(string: "https://moss.example")!)
        try store.saveCaptureSessionID("session-handoff")

        func makeDispatcher(
            portalHandoff: CapturePortalHandoffAdapter?
        ) -> ControlCommandDispatcher {
            ControlCommandDispatcher(
                controller: CaptureController.fakeForLocalDevelopment(),
                pairingExchange: StaticPairingExchange(result: CapturePairingResult(sessionID: "unused")),
                sessionStore: store,
                portalHandoff: portalHandoff
            )
        }

        var copyAttempts = 0
        let unpaired = makeDispatcher(
            portalHandoff: PasteboardCapturePortalHandoff(sessionStore: store) { _ in
                copyAttempts += 1
                return true
            }
        )
        XCTAssertThrowsError(try unpaired.dispatch(ControlChannelRequest(command: "handoff"))) { error in
            XCTAssertEqual(error as? CaptureSecurityError, .portalHandoffUnavailable)
        }
        XCTAssertEqual(copyAttempts, 0, "a missing view token must never reach the pasteboard")

        try store.saveCaptureViewToken("view-token-secret")
        let pasteboardFailure = makeDispatcher(
            portalHandoff: PasteboardCapturePortalHandoff(sessionStore: store) { _ in false }
        )
        XCTAssertThrowsError(try pasteboardFailure.dispatch(ControlChannelRequest(command: "handoff"))) { error in
            XCTAssertEqual(error as? CaptureSecurityError, .pasteboardUnavailable)
        }

        let noAdapter = makeDispatcher(portalHandoff: nil)
        XCTAssertThrowsError(try noAdapter.dispatch(ControlChannelRequest(command: "handoff"))) { error in
            XCTAssertEqual(error as? CaptureSecurityError, .portalHandoffUnavailable)
        }
    }

    func testOnlyTheAppCompositionRootHoldsViewAuthorityAndPasteboardAccess() throws {
        let sources = packageRoot().appendingPathComponent("Sources")
        func read(_ target: String, _ file: String) throws -> String {
            try String(
                contentsOf: sources.appendingPathComponent(target).appendingPathComponent(file),
                encoding: .utf8
            )
        }
        let appMain = try read("MOSSCaptureApp", "main.swift")
        let cliMain = try read("MTDCaptureCLI", "main.swift")
        let commandLine = try read("MOSSCaptureCore", "CaptureCommandLine.swift")
        let security = try read("MOSSCaptureCore", "CaptureSecurity.swift")

        XCTAssertTrue(appMain.contains("PasteboardCapturePortalHandoff(sessionStore:"))
        XCTAssertTrue(security.contains("case \"handoff\""))
        XCTAssertTrue(commandLine.contains("ControlChannelRequest(command: \"handoff\")"))
        XCTAssertTrue(appMain.contains("latencyProbe: CaptureLatencyProbe("))
        XCTAssertTrue(appMain.contains("frameObserver: latencySampler"))
        XCTAssertTrue(security.contains("case \"latency\""))
        XCTAssertTrue(commandLine.contains("ControlChannelRequest(command: \"latency\")"))
        for source in [cliMain, commandLine] {
            XCTAssertFalse(source.contains("PasteboardCapturePortalHandoff"))
            XCTAssertFalse(source.contains("loadCaptureViewToken"))
            XCTAssertFalse(source.contains("NSPasteboard"))
            // The measurement uses view authority; only the app may build the thing that holds it.
            XCTAssertFalse(source.contains("CaptureLatencyProbe("))
            XCTAssertFalse(source.contains("CaptureLatencySampler("))
        }
    }

    func testSecurityAdaptersExposeKeychainFullCertificatePinAndUDSInventory() throws {
        let source = try String(
            contentsOf: packageRoot()
                .appendingPathComponent("Sources")
                .appendingPathComponent("MOSSCaptureCore")
                .appendingPathComponent("CaptureSecurity.swift"),
            encoding: .utf8
        )

        XCTAssertTrue(source.contains("SecItemAdd"))
        XCTAssertTrue(source.contains("SecItemCopyMatching"))
        XCTAssertTrue(source.contains("SecCertificateCopyData"))
        XCTAssertTrue(source.contains("SHA256"))
        XCTAssertTrue(source.contains("AF_UNIX"))
        XCTAssertTrue(source.contains("SOCK_STREAM"))
        XCTAssertTrue(source.contains("LOCAL_PEERCRED"))
        XCTAssertTrue(source.contains("constantTimeEquals"))
    }

    func testFullCertificatePinValidatorRequiresExactValidSHA256() throws {
        let certificate = try testCertificate()
        let certificateData = SecCertificateCopyData(certificate) as Data
        let expectedHash = SHA256.hash(data: certificateData)
            .map { String(format: "%02x", $0) }
            .joined()
        let replacementLastByte = expectedHash.hasSuffix("00") ? "ff" : "00"
        let singleByteMismatch = expectedHash.dropLast(2) + replacementLastByte
        let validator = FullCertificatePinValidator()

        XCTAssertNoThrow(
            try validator.validate(
                certificate: certificate,
                expectedSHA256Hex: expectedHash.uppercased()
            )
        )
        XCTAssertThrowsError(
            try validator.validate(
                certificate: certificate,
                expectedSHA256Hex: String(singleByteMismatch)
            )
        ) { error in
            XCTAssertEqual(error as? CaptureSecurityError, .pinMismatch)
        }
        for invalidHash in [
            String(repeating: "0", count: 63),
            String(repeating: "g", count: 64),
        ] {
            XCTAssertThrowsError(
                try validator.validate(
                    certificate: certificate,
                    expectedSHA256Hex: invalidHash
                )
            ) { error in
                XCTAssertEqual(error as? CaptureSecurityError, .invalidPinnedHash)
            }
        }
    }

    func testPinnedURLSessionDelegateRequiresPresentedCertificateHash() throws {
        let certificate = try testCertificate()
        let certificateData = SecCertificateCopyData(certificate) as Data
        let expectedHash = SHA256.hash(data: certificateData)
            .map { String(format: "%02x", $0) }
            .joined()
        let trust = try testTrust(certificate: certificate)
        let delegate = try PinnedCertificateURLSessionDelegate(expectedSHA256Hex: expectedHash)
        let replacementLastByte = expectedHash.hasSuffix("00") ? "ff" : "00"
        let mismatchedHash = String(expectedHash.dropLast(2)) + replacementLastByte

        XCTAssertNoThrow(try delegate.validate(serverTrust: trust))
        XCTAssertThrowsError(
            try PinnedCertificateURLSessionDelegate(
                expectedSHA256Hex: mismatchedHash
            ).validate(serverTrust: trust)
        ) { error in
            XCTAssertEqual(error as? CaptureSecurityError, .pinMismatch)
        }
        XCTAssertThrowsError(
            try PinnedCertificateURLSessionDelegate(expectedSHA256Hex: String(repeating: "0", count: 63))
        ) { error in
            XCTAssertEqual(error as? CaptureSecurityError, .invalidPinnedHash)
        }
    }

    func testCaptureControllerPublicInterfaceIsLimitedToStartStatusStop() throws {
        let source = try String(
            contentsOf: packageRoot()
                .appendingPathComponent("Sources")
                .appendingPathComponent("MOSSCaptureCore")
                .appendingPathComponent("CaptureController.swift"),
            encoding: .utf8
        )
        let classStart = try XCTUnwrap(
            source.range(of: "public final class CaptureController {")
        )
        let controllerSource = String(source[classStart.lowerBound...])
        let declarationLine = try XCTUnwrap(
            controllerSource.split(separator: "\n", maxSplits: 1).first
        )
        let methodPattern = try NSRegularExpression(
            pattern: #"\bpublic\s+func\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("#
        )
        let methodMatches = methodPattern.matches(
            in: controllerSource,
            range: NSRange(controllerSource.startIndex..., in: controllerSource)
        )
        let methodNames = methodMatches.compactMap { match -> String? in
            guard let range = Range(match.range(at: 1), in: controllerSource) else {
                return nil
            }
            return String(controllerSource[range])
        }
        let initPattern = try NSRegularExpression(pattern: #"\bpublic\s+init\s*\("#)
        let initMatches = initPattern.matches(
            in: controllerSource,
            range: NSRange(controllerSource.startIndex..., in: controllerSource)
        )
        let storagePattern = try NSRegularExpression(
            pattern: #"\bpublic(?:\s+private\(set\))?\s+(?:var|let)\s+[A-Za-z_][A-Za-z0-9_]*"#
        )
        let storageMatches = storagePattern.matches(
            in: controllerSource,
            range: NSRange(controllerSource.startIndex..., in: controllerSource)
        )
        let publicSubscriptPattern = try NSRegularExpression(
            pattern: #"\bpublic\s+subscript\s*\("#
        )
        let publicSubscriptMatches = publicSubscriptPattern.matches(
            in: controllerSource,
            range: NSRange(controllerSource.startIndex..., in: controllerSource)
        )
        let nestedPublicTypePattern = try NSRegularExpression(
            pattern: #"\bpublic\s+(?:class|struct|enum|actor|protocol|typealias)\s+[A-Za-z_][A-Za-z0-9_]*"#
        )
        let nestedPublicTypeMatches = nestedPublicTypePattern.matches(
            in: controllerSource,
            range: NSRange(controllerSource.startIndex..., in: controllerSource)
        )

        XCTAssertEqual(methodNames.sorted(), ["start", "status", "stop"])
        XCTAssertEqual(initMatches.count, 1)
        XCTAssertTrue(storageMatches.isEmpty)
        XCTAssertTrue(publicSubscriptMatches.isEmpty)
        XCTAssertTrue(nestedPublicTypeMatches.isEmpty)
        XCTAssertFalse(declarationLine.contains(":"))
    }

    func testSameUserUDSAuthenticatorRequiresPrivateSocketPeerUIDAndSecret() throws {
        let authenticator = SameUserUDSAuthenticator(
            secrets: FakeCaptureKeyStoreAdapter(secret: "control-secret"),
            expectedUID: 501
        )

        XCTAssertNoThrow(try authenticator.validateSocketPermissions(0o600))
        XCTAssertThrowsError(try authenticator.validateSocketPermissions(0o660)) { error in
            XCTAssertEqual(error as? CaptureSecurityError, .socketPathNotPrivate)
        }
        XCTAssertNoThrow(try authenticator.validate(peerUID: 501, presentedSecret: "control-secret"))
        XCTAssertThrowsError(try authenticator.validate(peerUID: 502, presentedSecret: "control-secret")) { error in
            XCTAssertEqual(
                error as? CaptureSecurityError,
                .peerUIDMismatch(expected: 501, actual: 502)
            )
        }
        XCTAssertThrowsError(try authenticator.validate(peerUID: 501, presentedSecret: "wrong")) { error in
            XCTAssertEqual(error as? CaptureSecurityError, .controlSecretMismatch)
        }
    }

    func testUnixDomainControlClientUsesStoredControlSecretOnlyInUDSPayload() throws {
        let client = UnixDomainControlClient(
            socketPath: "/tmp/moss-capture/control.sock",
            secrets: FakeCaptureKeyStoreAdapter(secret: "control-secret")
        )

        let payload = try client.encodeRequest(
            ControlChannelRequest(command: "start", label: "local")
        )
        let body = try XCTUnwrap(String(data: payload, encoding: .utf8))

        XCTAssertTrue(body.contains("\"secret\":\"control-secret\""))
        XCTAssertTrue(body.contains("\"command\":\"start\""))
        XCTAssertTrue(body.contains("\"label\":\"local\""))
        XCTAssertFalse(client.socketPath.contains("control-secret"))
    }

    func testUnixDomainControlRoundTrip() throws {
        let socketPath = temporarySocketPath()
        let serverFinished = expectation(description: "server finished one request")
        let serverError = TestErrorBox()
        let server = UnixDomainControlServer(
            socketPath: socketPath,
            authenticator: SameUserUDSAuthenticator(secrets: FakeCaptureKeyStoreAdapter(secret: "control-secret"))
        ) { request in
            XCTAssertEqual(request.command, "status")
            return ControlChannelResponse(ok: true, running: false)
        }

        DispatchQueue.global().async {
            do {
                try server.serveOnce()
            } catch {
                serverError.store(error)
            }
            serverFinished.fulfill()
        }
        try waitForSocket(at: socketPath)

        let client = UnixDomainControlClient(
            socketPath: socketPath,
            secrets: FakeCaptureKeyStoreAdapter(secret: "control-secret")
        )
        let response = try client.sendRequest(ControlChannelRequest(command: "status"))

        wait(for: [serverFinished], timeout: 2)
        XCTAssertNil(serverError.load())
        XCTAssertTrue(response.ok)
        XCTAssertEqual(response.running, false)
    }

    func testControlServerRejectsWrongSecretBeforeMutation() throws {
        let socketPath = temporarySocketPath()
        let serverFinished = expectation(description: "server rejected one request")
        var mutationCount = 0
        let server = UnixDomainControlServer(
            socketPath: socketPath,
            authenticator: SameUserUDSAuthenticator(secrets: FakeCaptureKeyStoreAdapter(secret: "control-secret"))
        ) { _ in
            mutationCount += 1
            return ControlChannelResponse(ok: true)
        }

        DispatchQueue.global().async {
            try? server.serveOnce()
            serverFinished.fulfill()
        }
        try waitForSocket(at: socketPath)

        let client = UnixDomainControlClient(
            socketPath: socketPath,
            secrets: FakeCaptureKeyStoreAdapter(secret: "wrong-secret")
        )
        let response = try client.sendRequest(ControlChannelRequest(command: "start"))

        wait(for: [serverFinished], timeout: 2)
        XCTAssertFalse(response.ok)
        XCTAssertEqual(mutationCount, 0)
    }

    func testControlServerSanitizesUnknownErrorInActualResponseArtifact() throws {
        let socketPath = temporarySocketPath()
        let artifact = FileManager.default.temporaryDirectory
            .appendingPathComponent("moss-control-response-\(UUID().uuidString).bin")
        let secret = "raw-error-secret-\(UUID().uuidString)"
        defer {
            try? FileManager.default.removeItem(at: artifact)
        }
        let serverFinished = expectation(description: "server sanitized one error")
        let serverError = TestErrorBox()
        let server = UnixDomainControlServer(
            socketPath: socketPath,
            authenticator: SameUserUDSAuthenticator(
                secrets: FakeCaptureKeyStoreAdapter(secret: "control-secret")
            )
        ) { _ in
            throw SecretBearingControlError(secret: secret)
        }

        DispatchQueue.global().async {
            do {
                try server.serveOnce()
            } catch {
                serverError.store(error)
            }
            serverFinished.fulfill()
        }
        try waitForSocket(at: socketPath)

        let responseBody = try sendRawControlPayloadBody(
            try rawControlFrame(command: "status"),
            socketPath: socketPath
        )
        try responseBody.write(to: artifact, options: .atomic)
        let response = try JSONDecoder().decode(ControlChannelResponse.self, from: responseBody)

        wait(for: [serverFinished], timeout: 2)
        XCTAssertNil(serverError.load())
        XCTAssertFalse(response.ok)
        XCTAssertEqual(response.error, "control_failed")
        XCTAssertNil(responseBody.range(of: Data(secret.utf8)))
        XCTAssertEqual(try Data(contentsOf: artifact), responseBody)
    }

    /// The failure that hid the ATS block for a whole merge. A pinned `URLSession` reports a
    /// refused connection as an `NSURLErrorDomain` error whose real reason lives only in the
    /// underlying stream code, and the control channel discarded the domain, the code and the
    /// underlying code alike — the operator saw `control_failed` and had nothing to search for.
    /// Domain and code are compile-time constants and integers; the message and the failing URL
    /// beside them are not, so neither may cross the socket.
    func testAnUnclassifiedTransportFailureCarriesItsDomainCodeAndUnderlyingCodeButNoMessageOrURL() throws {
        struct FailureCase {
            var name: String
            var error: Error
            var expected: ControlChannelErrorDetail
        }

        let failingURL = "https://100.64.0.8:7861/api/live/pairings"
        let message = "An SSL error has occurred and a secure connection to the server cannot be made."
        let cases = [
            // Exactly what m4mbp saw: -1200 says "secure connection failed", -9802 says why.
            FailureCase(
                name: "ats-refused-tls",
                error: NSError(
                    domain: NSURLErrorDomain,
                    code: NSURLErrorSecureConnectionFailed,
                    userInfo: [
                        NSLocalizedDescriptionKey: message,
                        NSURLErrorFailingURLStringErrorKey: failingURL,
                        "_kCFStreamErrorCodeKey": -9802,
                        "_kCFStreamErrorDomainKey": 3,
                    ]
                ),
                expected: ControlChannelErrorDetail(
                    domain: NSURLErrorDomain,
                    code: NSURLErrorSecureConnectionFailed,
                    underlyingCode: -9802
                )
            ),
            // The other shape URLSession uses for the same idea: a nested NSError.
            FailureCase(
                name: "nested-underlying-error",
                error: NSError(
                    domain: NSURLErrorDomain,
                    code: NSURLErrorCannotConnectToHost,
                    userInfo: [
                        NSURLErrorFailingURLStringErrorKey: failingURL,
                        NSUnderlyingErrorKey: NSError(
                            domain: NSPOSIXErrorDomain,
                            code: 61,
                            userInfo: [NSLocalizedDescriptionKey: message]
                        ),
                    ]
                ),
                expected: ControlChannelErrorDetail(
                    domain: NSURLErrorDomain,
                    code: NSURLErrorCannotConnectToHost,
                    underlyingCode: 61
                )
            ),
            // No underlying reason at all: report that honestly rather than inventing a zero.
            FailureCase(
                name: "no-underlying-reason",
                error: NSError(domain: NSURLErrorDomain, code: NSURLErrorTimedOut, userInfo: [:]),
                expected: ControlChannelErrorDetail(
                    domain: NSURLErrorDomain,
                    code: NSURLErrorTimedOut,
                    underlyingCode: nil
                )
            ),
        ]

        for failureCase in cases {
            let socketPath = temporarySocketPath()
            let serverFinished = expectation(description: "server answered \(failureCase.name)")
            let server = UnixDomainControlServer(
                socketPath: socketPath,
                authenticator: SameUserUDSAuthenticator(
                    secrets: FakeCaptureKeyStoreAdapter(secret: "control-secret")
                )
            ) { _ in
                throw failureCase.error
            }
            DispatchQueue.global().async {
                try? server.serveOnce()
                serverFinished.fulfill()
            }
            try waitForSocket(at: socketPath)

            let responseBody = try sendRawControlPayloadBody(
                try rawControlFrame(command: "pair"),
                socketPath: socketPath
            )
            let response = try JSONDecoder().decode(ControlChannelResponse.self, from: responseBody)
            wait(for: [serverFinished], timeout: 2)

            XCTAssertFalse(response.ok, failureCase.name)
            XCTAssertEqual(response.error, "control_failed", failureCase.name)
            XCTAssertEqual(response.errorDetail, failureCase.expected, failureCase.name)
            // The detail is numbers and one constant. Everything the error knew about the
            // deployment stays inside the app.
            XCTAssertNil(responseBody.range(of: Data(failingURL.utf8)), failureCase.name)
            XCTAssertNil(responseBody.range(of: Data(message.utf8)), failureCase.name)
            XCTAssertNil(responseBody.range(of: Data("100.64.0.8".utf8)), failureCase.name)
        }
    }

    /// Classification must not rename what already worked: the tracer, the CLI and the operator's
    /// runbook all read these exact strings, and a named failure needs no detail because its name
    /// already says everything non-secret about it.
    func testAlreadyNamedControlFailuresKeepTheirNamesAndCarryNoDetail() throws {
        struct NamedCase {
            var error: Error
            var expected: String
        }

        let cases = [
            NamedCase(error: CaptureSecurityError.invalidPairingPayload, expected: "invalidPairingPayload"),
            NamedCase(error: CaptureSecurityError.invalidPinnedHash, expected: "invalidPinnedHash"),
            NamedCase(error: CaptureControllerError.notRunning, expected: "notRunning"),
            NamedCase(
                error: CaptureHTTPTransportError.nonSuccessStatus(401),
                expected: "nonSuccessStatus(401)"
            ),
            NamedCase(
                error: NativeCaptureError.permissionDenied("microphone"),
                expected: "permissionDenied(\"microphone\")"
            ),
        ]

        for namedCase in cases {
            let socketPath = temporarySocketPath()
            let serverFinished = expectation(description: "server answered \(namedCase.expected)")
            let failureLog = RecordingControlChannelFailureLog()
            let server = UnixDomainControlServer(
                socketPath: socketPath,
                authenticator: SameUserUDSAuthenticator(
                    secrets: FakeCaptureKeyStoreAdapter(secret: "control-secret")
                ),
                failureLog: failureLog
            ) { _ in
                throw namedCase.error
            }
            DispatchQueue.global().async {
                try? server.serveOnce()
                serverFinished.fulfill()
            }
            try waitForSocket(at: socketPath)

            let response = try sendRawControlPayload(
                try rawControlFrame(command: "status"),
                socketPath: socketPath
            )
            wait(for: [serverFinished], timeout: 2)

            XCTAssertFalse(response.ok, namedCase.expected)
            XCTAssertEqual(response.error, namedCase.expected)
            XCTAssertNil(response.errorDetail, namedCase.expected)
            // Only what has no name is worth a log line; a named failure is already evidence.
            XCTAssertEqual(failureLog.records.count, 0, namedCase.expected)
        }
    }

    /// An `LSUIElement` app has no window and its stderr goes nowhere when Launch Services starts
    /// it, so a failure it does not record is a failure nobody can reconstruct afterwards. The log
    /// is handed the command word and the non-secret detail and nothing else — it cannot write a
    /// payload even by accident, because it is never given one.
    func testEveryUnclassifiedControlFailureIsLoggedOnceWithOnlyItsCommandAndDetail() throws {
        let secret = "unclassified-log-secret-\(UUID().uuidString)"
        let failureLog = RecordingControlChannelFailureLog()

        func failOnce(command: String) throws -> ControlChannelResponse {
            let socketPath = temporarySocketPath()
            let serverFinished = expectation(description: "server answered \(command)")
            let server = UnixDomainControlServer(
                socketPath: socketPath,
                authenticator: SameUserUDSAuthenticator(
                    secrets: FakeCaptureKeyStoreAdapter(secret: "control-secret")
                ),
                failureLog: failureLog
            ) { _ in
                throw SecretBearingControlError(secret: secret)
            }
            DispatchQueue.global().async {
                try? server.serveOnce()
                serverFinished.fulfill()
            }
            try waitForSocket(at: socketPath)
            let response = try sendRawControlPayload(
                try rawControlFrame(command: command),
                socketPath: socketPath
            )
            wait(for: [serverFinished], timeout: 2)
            return response
        }

        let first = try failOnce(command: "pair")
        let second = try failOnce(command: "latency")

        XCTAssertEqual(failureLog.records.count, 2)
        XCTAssertEqual(failureLog.records.map(\.command), ["pair", "latency"])
        XCTAssertEqual(failureLog.records.map(\.detail), [first.errorDetail, second.errorDetail])
        XCTAssertNotNil(first.errorDetail)
        // A Swift error's bridged domain is its type name and its code is a case index, so the
        // associated secret cannot reach the log through either.
        for record in failureLog.records {
            XCTAssertFalse(record.detail.domain.contains(secret))
            XCTAssertTrue(record.detail.domain.contains("SecretBearingControlError"))
        }
    }

    /// Everything the app's log marks public has to be provably non-secret. The detail already is
    /// — it is a domain and integers — but the command word arrives over the socket, so the log
    /// reduces it to the fixed vocabulary rather than trusting it. An unknown command never
    /// reaches this path (it throws a named `unknownCommand`), which is exactly why the guard has
    /// to be structural instead of relying on that.
    func testTheAppFailureLogWritesOnlyAFixedCommandWordAndTheDetailsNumbers() throws {
        let lines = LoggedLineBox()
        let log = OSLogControlChannelFailureLog { lines.append($0) }
        let detail = ControlChannelErrorDetail(
            domain: NSURLErrorDomain,
            code: NSURLErrorSecureConnectionFailed,
            underlyingCode: -9802
        )

        log.recordUnclassifiedFailure(command: "pair", detail: detail)
        log.recordUnclassifiedFailure(
            command: "status; token=sk-live-do-not-log",
            detail: ControlChannelErrorDetail(domain: "MOSSCaptureCore.Whatever", code: 3)
        )
        log.recordUnclassifiedFailure(command: nil, detail: detail)

        XCTAssertEqual(
            lines.lines,
            [
                "control command pair failed with an unclassified error: "
                    + "domain=NSURLErrorDomain code=-1200 underlying=-9802",
                "control command other failed with an unclassified error: "
                    + "domain=MOSSCaptureCore.Whatever code=3 underlying=none",
                "control command unknown failed with an unclassified error: "
                    + "domain=NSURLErrorDomain code=-1200 underlying=-9802",
            ]
        )
        for line in lines.lines {
            XCTAssertFalse(line.contains("sk-live-do-not-log"))
        }
        // The vocabulary is the CLI's, not a second copy of it.
        XCTAssertEqual(ControlChannelCommands.all, ["pair", "start", "stop", "status", "handoff", "latency"])
    }

    /// The declaration is worthless if the shipped app never wires it. The CLI has no control
    /// server at all, so it must not grow one.
    func testTheAppEntrypointWiresTheControlChannelFailureLogAndTheCLIDoesNot() throws {
        let package = packageRoot()
        func read(_ target: String, _ file: String) throws -> String {
            try String(
                contentsOf: package
                    .appendingPathComponent("Sources")
                    .appendingPathComponent(target)
                    .appendingPathComponent(file),
                encoding: .utf8
            )
        }

        let appMain = try read("MOSSCaptureApp", "main.swift")
        let cliMain = try read("MTDCaptureCLI", "main.swift")
        XCTAssertTrue(appMain.contains("OSLogControlChannelFailureLog()"))
        XCTAssertTrue(appMain.contains("failureLog:"))
        XCTAssertFalse(cliMain.contains("OSLogControlChannelFailureLog"))
        XCTAssertFalse(cliMain.contains("UnixDomainControlServer"))
        // The lane log is the same declaration wired to the other half of the app: the health
        // adapter the controller heartbeats through. Declaring it and not wrapping the heartbeat
        // would leave the lane failure exactly as silent as it was.
        XCTAssertTrue(appMain.contains("LaneFailureLoggingHealthAdapter("))
        XCTAssertTrue(appMain.contains("log: failureLog"))
        XCTAssertFalse(cliMain.contains("LaneFailureLoggingHealthAdapter"))
    }

    /// A lane failure is the one event that ends a meeting, and the app watched two of them happen
    /// without recording either. It is logged on the health path because the heartbeat is the only
    /// report the app makes unprompted — an operator who never polls still gets the code.
    func testEveryLaneFailureIsLoggedOncePerFailureAndTheHeartbeatIsUnchanged() throws {
        let log = RecordingCaptureLaneFailureLog()
        let delegate = FakeCaptureHealthAdapter()
        let adapter = LaneFailureLoggingHealthAdapter(wrapping: delegate, log: log)
        let configuration = CaptureConfiguration(
            sessionID: "session-lane-log",
            serverURL: URL(string: "https://127.0.0.1:7861")!
        )

        func emit(_ lanes: [CaptureLaneStatus]) throws {
            try adapter.emit(
                status: CaptureStatus(
                    running: true,
                    sessionID: configuration.sessionID,
                    lanes: lanes,
                    publishedFrameCount: 0,
                    lastHealthSequence: nil
                ),
                configuration: configuration,
                sentMonotonicNS: 0
            )
        }

        let capturingBoth = [
            CaptureLaneStatus(lane: .system, sequence: 1, deviceEpoch: 1, state: "capturing"),
            CaptureLaneStatus(lane: .microphone, sequence: 1, deviceEpoch: 1, state: "capturing"),
        ]
        let microphoneDenied = CaptureLaneStatus(
            lane: .microphone,
            sequence: 1,
            deviceEpoch: 1,
            state: "failed",
            failureCode: "macos_permission_denied"
        )

        try emit(capturingBoth)
        XCTAssertEqual(log.records, [], "a healthy heartbeat is not evidence of anything")

        try emit([capturingBoth[0], microphoneDenied])
        // The projection is sticky for the life of a generation, so a 0.5 s pump would write this
        // line twice a second forever and bury what it exists to preserve.
        for _ in 0..<4 {
            try emit([capturingBoth[0], microphoneDenied])
        }
        XCTAssertEqual(log.records, [microphoneDenied])

        // A second lane failing is a second failure, not a repeat of the first.
        let systemUnavailable = CaptureLaneStatus(
            lane: .system,
            sequence: 2,
            deviceEpoch: 1,
            state: "failed",
            droppedFrames: 3,
            failureCode: "macos_device_unavailable"
        )
        try emit([systemUnavailable, microphoneDenied])
        XCTAssertEqual(log.records, [microphoneDenied, systemUnavailable])

        // Recovered and failed again is a new failure: the operator needs both, and a lane that
        // recovers must not silence the next one.
        let microphoneRecovered = CaptureLaneStatus(
            lane: .microphone,
            sequence: 3,
            deviceEpoch: 2,
            state: "capturing"
        )
        try emit([systemUnavailable, microphoneRecovered])
        // The same code again, deliberately: what makes this a second failure is the recovery
        // between them, so a log that remembers only the code would swallow it.
        let microphoneDeniedAgain = CaptureLaneStatus(
            lane: .microphone,
            sequence: 3,
            deviceEpoch: 2,
            state: "failed",
            failureCode: "macos_permission_denied"
        )
        try emit([systemUnavailable, microphoneDeniedAgain])
        XCTAssertEqual(log.records, [microphoneDenied, systemUnavailable, microphoneDeniedAgain])

        // Watching costs the heartbeat nothing: every emission still reached the real adapter.
        XCTAssertEqual(delegate.emissions.count, 9)
        XCTAssertEqual(delegate.emissions.map(\.configuration), Array(repeating: configuration, count: 9))
    }

    /// A lane the source never reported at all is named, so the log agrees with the control channel
    /// and the heartbeat about which lanes exist — and a heartbeat the server refuses still leaves
    /// the record behind, which is the case where it is the only evidence there is.
    func testTheLaneFailureIsRecordedFromTheSharedProjectionEvenWhenTheHeartbeatFails() throws {
        let log = RecordingCaptureLaneFailureLog()
        let delegate = ThrowingCaptureHealthAdapter(
            error: CaptureHTTPTransportError.nonSuccessStatus(403)
        )
        let adapter = LaneFailureLoggingHealthAdapter(wrapping: delegate, log: log)
        let systemFailed = CaptureLaneStatus(
            lane: .system,
            sequence: 1,
            deviceEpoch: 1,
            state: "failed",
            failureCode: "macos_unexpected_capture_error"
        )

        XCTAssertThrowsError(
            try adapter.emit(
                // Only one lane reported: the other is absent, exactly as in the attended session.
                status: CaptureStatus(
                    running: true,
                    sessionID: "session-lane-log",
                    lanes: [systemFailed],
                    publishedFrameCount: 0,
                    lastHealthSequence: nil
                ),
                configuration: CaptureConfiguration(
                    sessionID: "session-lane-log",
                    serverURL: URL(string: "https://127.0.0.1:7861")!
                ),
                sentMonotonicNS: 0
            )
        )

        XCTAssertEqual(log.records, [systemFailed])
        XCTAssertEqual(
            log.records.map(\.lane),
            [.system],
            "an absent lane is stopped, not failed — naming it failed would invent an event"
        )
    }

    /// Everything the app's log marks public has to be provably non-secret. The lane, the state and
    /// the code are vocabulary the capture source minted; the free-form cause behind the code is
    /// not on `CaptureLaneStatus` at all, so the log is never handed it.
    func testTheAppLaneFailureLineNamesTheLaneAndTypedCodeAndNeverTheCause() throws {
        let cause = "cause-that-must-not-be-logged-\(UUID().uuidString)"
        let health = NativeLaneHealth()
        let generation = health.beginGeneration()
        health.enqueue(.admitted, lane: .microphone, generation: generation)
        health.enqueue(.unexpectedCaptureError(cause), lane: .microphone, generation: generation)

        let statuses = health.statuses(running: true)
        let microphone = try XCTUnwrap(statuses.first { $0.lane == .microphone })
        XCTAssertEqual(health.failure(for: .microphone)?.cause, cause, "the cause is known here")

        let lines = LoggedLineBox()
        let log = OSLogControlChannelFailureLog { lines.append($0) }
        for status in statuses where status.state == "failed" {
            log.recordLaneFailure(status)
        }

        XCTAssertEqual(
            lines.lines,
            [
                "capture lane microphone failed: state=failed "
                    + "code=macos_unexpected_capture_error dropped=0 discontinuities=0"
            ]
        )
        XCTAssertFalse(try XCTUnwrap(lines.lines.first).contains(cause))
        XCTAssertEqual(microphone.failureCode, "macos_unexpected_capture_error")
    }

    /// A degradation is written to the same log, and it says what it is.
    ///
    /// Both live diagnoses that found this defect — F1's mid-meeting lane loss and F3's death at
    /// minute 14.6 — were read off this one line, so D-a's reclassification had to follow the
    /// condition here or the cycle would have traded a dead meeting for a blind one. The verb
    /// comes from the state: a degradation that announced itself as a failure would be the same
    /// lie in the log that the lane state used to tell on the wire.
    func testTheAppLogRecordsADegradationAsLoudlyAsAFailureAndNamesItCorrectly() throws {
        let lines = LoggedLineBox()
        let delegate = FakeCaptureHealthAdapter()
        let adapter = LaneFailureLoggingHealthAdapter(
            wrapping: delegate,
            log: OSLogControlChannelFailureLog { lines.append($0) }
        )
        let configuration = laneConfiguration()
        func emit(_ lanes: [CaptureLaneStatus]) throws {
            try adapter.emit(
                status: CaptureStatus(
                    running: true,
                    sessionID: configuration.sessionID,
                    lanes: lanes,
                    publishedFrameCount: 0,
                    lastHealthSequence: nil
                ),
                configuration: configuration,
                sentMonotonicNS: 0
            )
        }
        let capturing = CaptureLaneStatus(
            lane: .microphone,
            sequence: 1,
            deviceEpoch: 1,
            state: "capturing"
        )
        let degraded = CaptureLaneStatus(
            lane: .system,
            sequence: 1,
            deviceEpoch: 1,
            state: "degraded",
            droppedFrames: 149,
            failureCode: "macos_buffer_overrun"
        )

        try emit([degraded, capturing])
        // Sticky for the generation, exactly as a failure is: a 0.5 s pump must not write this
        // line twice a second for the rest of a sixteen-minute meeting.
        for _ in 0..<3 {
            try emit([degraded, capturing])
        }

        XCTAssertEqual(
            lines.lines,
            [
                "capture lane system degraded: state=degraded "
                    + "code=macos_buffer_overrun dropped=149 discontinuities=0"
            ]
        )
        XCTAssertEqual(delegate.emissions.count, 4, "watching costs the heartbeat nothing")
    }

    /// One vocabulary for the lane states. A reporting surface that spells `failed` itself is a
    /// surface that can silently stop recognising a failure the source still reports.
    func testEveryReportedLaneStateComesFromTheOneStateVocabulary() throws {
        let health = NativeLaneHealth()
        let generation = health.beginGeneration()
        health.enqueue(.admitted, lane: .system, generation: generation)
        health.enqueue(.configurationChanged, lane: .microphone, generation: generation)

        let running = health.statuses(running: true)
        XCTAssertEqual(
            running.map(\.state),
            [CaptureLaneStates.capturing, CaptureLaneStates.recovering]
        )
        XCTAssertEqual(
            health.statuses(running: false).map(\.state),
            [CaptureLaneStates.stopped, CaptureLaneStates.stopped]
        )

        health.enqueue(.permission(.denied), lane: .microphone, generation: generation)
        XCTAssertEqual(
            health.statuses(running: true).map(\.state),
            [CaptureLaneStates.capturing, CaptureLaneStates.failed]
        )

        // The one lane no source reported still answers with the same word.
        let unreported = CaptureStatus(
            running: true,
            sessionID: nil,
            lanes: [],
            publishedFrameCount: 0,
            lastHealthSequence: nil
        )
        XCTAssertEqual(
            unreported.reportedLanes().map(\.state),
            [CaptureLaneStates.stopped, CaptureLaneStates.stopped]
        )
        XCTAssertEqual(
            [
                CaptureLaneStates.capturing,
                CaptureLaneStates.recovering,
                CaptureLaneStates.stopped,
                CaptureLaneStates.failed,
            ],
            ["capturing", "recovering", "stopped", "failed"]
        )
    }

    func testControlServerRejectsMalformedPartialOversizedAndTrailingFramesBeforeMutation() throws {
        struct BadFrameCase {
            var name: String
            var payload: Data
            var maxFrameBytes: Int
            var halfCloseWrite: Bool
            var expectedError: String
        }

        let validEnvelope = try rawControlFrame(command: "status")
        let cases = [
            BadFrameCase(
                name: "malformed",
                payload: rawFrame(Data("not-json".utf8)),
                maxFrameBytes: 64,
                halfCloseWrite: false,
                expectedError: "malformedRequest"
            ),
            BadFrameCase(
                name: "partial",
                payload: rawLengthPrefix(16) + Data("{}".utf8),
                maxFrameBytes: 64,
                halfCloseWrite: true,
                expectedError: "malformedRequest"
            ),
            BadFrameCase(
                name: "oversized",
                payload: rawLengthPrefix(65),
                maxFrameBytes: 64,
                halfCloseWrite: false,
                expectedError: "oversizedRequest"
            ),
            BadFrameCase(
                name: "trailing",
                payload: validEnvelope + Data([0]),
                maxFrameBytes: 64,
                halfCloseWrite: false,
                expectedError: "trailingRequestBytes"
            ),
        ]

        for badFrame in cases {
            let socketPath = temporarySocketPath()
            let serverFinished = expectation(description: "server rejected \(badFrame.name)")
            var mutationCount = 0
            let server = UnixDomainControlServer(
                socketPath: socketPath,
                authenticator: SameUserUDSAuthenticator(secrets: FakeCaptureKeyStoreAdapter(secret: "control-secret")),
                maxFrameBytes: badFrame.maxFrameBytes
            ) { _ in
                mutationCount += 1
                return ControlChannelResponse(ok: true)
            }

            DispatchQueue.global().async {
                try? server.serveOnce()
                serverFinished.fulfill()
            }
            try waitForSocket(at: socketPath)

            let response = try sendRawControlPayload(
                badFrame.payload,
                socketPath: socketPath,
                halfCloseWrite: badFrame.halfCloseWrite
            )

            wait(for: [serverFinished], timeout: 2)
            XCTAssertFalse(response.ok, badFrame.name)
            XCTAssertEqual(response.error, badFrame.expectedError, badFrame.name)
            XCTAssertEqual(mutationCount, 0, badFrame.name)
        }
    }

    func testControlServerRejectsUnknownCommandAndMissingConfigurationWithoutControllerMutation() throws {
        let cases = [
            ("unknown", ControlChannelRequest(command: "restart"), "unknownCommand(\"restart\")"),
            ("missing configuration", ControlChannelRequest(command: "start"), "missingCaptureConfiguration"),
        ]

        for controlCase in cases {
            let controller = CaptureController.fakeForLocalDevelopment()
            let dispatcher = ControlCommandDispatcher(
                controller: controller,
                pairingExchange: RecordingPairingExchange()
            )
            let socketPath = temporarySocketPath()
            let serverFinished = expectation(description: "server rejected \(controlCase.0)")
            let server = UnixDomainControlServer(
                socketPath: socketPath,
                authenticator: SameUserUDSAuthenticator(secrets: FakeCaptureKeyStoreAdapter(secret: "control-secret"))
            ) { request in
                try dispatcher.dispatch(request)
            }

            DispatchQueue.global().async {
                try? server.serveOnce()
                serverFinished.fulfill()
            }
            try waitForSocket(at: socketPath)

            let response = try sendRawControlPayload(
                try rawControlFrame(request: controlCase.1),
                socketPath: socketPath
            )

            wait(for: [serverFinished], timeout: 2)
            XCTAssertFalse(response.ok, controlCase.0)
            XCTAssertEqual(response.error, controlCase.2, controlCase.0)
            XCTAssertFalse(controller.status().running, controlCase.0)
        }
    }

    func testPairingPayloadReachesApp() throws {
        let exchange = RecordingPairingExchange()
        let dispatcher = ControlCommandDispatcher(
            controller: CaptureController.fakeForLocalDevelopment(),
            pairingExchange: exchange
        )
        let payload = Data([1, 2, 3, 4])
        let serverURL = URL(string: "https://moss.example")!

        let response = try dispatcher.dispatch(
            ControlChannelRequest(
                command: "pair",
                serverURL: serverURL,
                pairingPayload: payload
            )
        )

        XCTAssertTrue(response.ok)
        XCTAssertEqual(response.sessionID, "session-from-pairing")
        XCTAssertEqual(response.portalURL, serverURL.appendingPathComponent("live"))
        XCTAssertEqual(exchange.serverURL, serverURL)
        XCTAssertEqual(exchange.pairingPayload, payload)
    }

    func testProductionStartDefersPermissionStateToIndependentNativeLanes() throws {
        let appMain = try String(
            contentsOf: packageRoot()
                .appendingPathComponent("Sources")
                .appendingPathComponent("MOSSCaptureApp")
                .appendingPathComponent("main.swift"),
            encoding: .utf8
        )

        XCTAssertTrue(appMain.contains("handler: dispatcher.dispatch"))
        XCTAssertFalse(appMain.contains("CGPreflightScreenCaptureAccess"))
        XCTAssertFalse(appMain.contains("CoreGraphics"))
        XCTAssertFalse(appMain.contains("authorizationStatus(for: .audio)"))
    }

    func testPromotedSwiftTestIdentifiersRemainCollected() throws {
        let testRoot = packageRoot().appendingPathComponent("Tests")
        let sources = try swiftSources(under: testRoot)
        let identifiers = Set(
            try matches(
                pattern: #"(?m)^\s*func\s+(test[A-Za-z0-9_]+)\s*\("#,
                in: sources
            )
        )
        let required = Set([
            "testUnixDomainControlRoundTrip",
            "testCLIAppLaunchDecisionAndFailureArePropagated",
            "testCLIPairingPayloadCrossesStdinThroughRealUDSWithoutOutputLeak",
            "testPumpFailureIsTypedAndLaterTicksContinue",
            "testRepeatingSchedulerContinuesUntilExplicitCancellation",
            "testFullCertificatePinValidatorRequiresExactValidSHA256",
            "testHTTPHealthSerializesTypedLaneFailureCode",
            "testControllerSharedStatusIsSynchronizedUnderConcurrentPumpStatus",
        ])

        XCTAssertTrue(required.isSubset(of: identifiers), "missing \(required.subtracting(identifiers))")
        XCTAssertGreaterThanOrEqual(identifiers.count, 32)
    }

    func testIDEA036ContextKeepsEvidenceTierMissingFence() throws {
        let repositoryRoot = packageRoot()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let context = try String(
            contentsOf: repositoryRoot.appendingPathComponent("CONTEXT.md"),
            encoding: .utf8
        )
        let marker = "- **IDEA-036 explicit helper lease**:"
        let paragraph = try XCTUnwrap(
            context.components(separatedBy: marker).dropFirst().first?
                .components(separatedBy: "\n- **").first
        )
        let normalizedParagraph = paragraph
            .split(whereSeparator: \.isWhitespace)
            .joined(separator: " ")

        for missingFact in [
            "production lease selection",
            "signed hardware evidence",
            "notarization",
            "TCC continuity",
            "deployed device behavior",
            "60/300 evidence",
            "canary",
            "deployment",
            "live enablement",
        ] {
            XCTAssertTrue(normalizedParagraph.contains(missingFact), missingFact)
        }
        XCTAssertTrue(normalizedParagraph.contains("remain Missing"))
        XCTAssertFalse(normalizedParagraph.contains("local green gates certify"))
        XCTAssertFalse(normalizedParagraph.contains("certifies production"))
    }

    func testIDEA042ContextKeepsEvidenceTierMissingFence() throws {
        let repositoryRoot = packageRoot()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let context = try String(
            contentsOf: repositoryRoot.appendingPathComponent("CONTEXT.md"),
            encoding: .utf8
        )
        let marker = "- **Runnable local helper bridge (IDEA-042)**:"
        let paragraph = try XCTUnwrap(
            context.components(separatedBy: marker).dropFirst().first?
                .components(separatedBy: "\n- **").first
        )
        let normalizedParagraph = paragraph
            .split(whereSeparator: \.isWhitespace)
            .joined(separator: " ")

        for missingFact in [
            "signing",
            "notarization",
            "TCC",
            "Keychain access-group runtime",
            "deployed certificate pinning",
            "real devices",
            "permission continuity",
            "deployment",
            "duration",
            "canary",
            "live enablement",
        ] {
            XCTAssertTrue(normalizedParagraph.contains(missingFact), missingFact)
        }
        XCTAssertTrue(normalizedParagraph.contains("remain Missing"))
        XCTAssertFalse(normalizedParagraph.contains("proven by the local unsigned build"))
        XCTAssertFalse(normalizedParagraph.contains("deployment and enablement are ready"))
    }

    func testIDEA043ContextAndADRUseSourceOwnedNativeTypedVocabulary() throws {
        let repositoryRoot = packageRoot()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let context = try String(
            contentsOf: repositoryRoot.appendingPathComponent("CONTEXT.md"),
            encoding: .utf8
        )
        let adr = try String(
            contentsOf: repositoryRoot
                .appendingPathComponent("docs")
                .appendingPathComponent("adr")
                .appendingPathComponent("0001-live-v2-json-http-contract.md"),
            encoding: .utf8
        )
        let marker = "- **Native typed lane failure (IDEA-043)**:"
        let paragraph = try XCTUnwrap(
            context.components(separatedBy: marker).dropFirst().first?
                .components(separatedBy: "\n- **").first
        )
        let normalizedParagraph = paragraph
            .split(whereSeparator: \.isWhitespace)
            .joined(separator: " ")

        XCTAssertTrue(normalizedParagraph.contains("source-owned `NativeLaneHealth`"))
        XCTAssertTrue(normalizedParagraph.contains("native typed raw facts"))
        XCTAssertTrue(normalizedParagraph.contains("`moss-live-helper-health.v1`"))
        XCTAssertTrue(normalizedParagraph.contains("remain Missing"))
        XCTAssertFalse(context.contains("No production caller detects helper loss or invokes lane failure"))
        XCTAssertTrue(adr.contains("IDEA-043 adds source-owned native lane failure ownership"))
        XCTAssertTrue(adr.contains("stable `macos_*` failure codes"))
    }

    func testIDEA042ResidualKillNodesNameExistingActualTests() throws {
        let repositoryRoot = packageRoot()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let adr = try String(
            contentsOf: repositoryRoot
                .appendingPathComponent("docs")
                .appendingPathComponent("adr")
                .appendingPathComponent("0001-live-v2-json-http-contract.md"),
            encoding: .utf8
        )
        let section = try XCTUnwrap(
            adr.components(separatedBy: "## IDEA-042 Residual Kill Nodes").dropFirst().first?
                .components(separatedBy: "\n## ").first
        )
        let namedTests = Set(
            try matches(pattern: #"`(test[A-Za-z0-9_]+)`"#, in: section)
        )
        let swiftTests = try swiftSources(
            under: repositoryRoot
                .appendingPathComponent("macos")
                .appendingPathComponent("MOSSCapture")
                .appendingPathComponent("Tests")
        )
        let pythonTests = try textSources(
            under: repositoryRoot.appendingPathComponent("tests"),
            pathExtension: "py"
        )
        let testSources = swiftTests + "\n" + pythonTests

        XCTAssertTrue(
            section.contains("- N2: `testFullCertificatePinValidatorRequiresExactValidSHA256`")
        )
        XCTAssertFalse(
            section.contains("- N2: `testSecurityAdaptersExposeKeychainFullCertificatePinAndUDSInventory`")
        )
        for testName in namedTests {
            let escaped = NSRegularExpression.escapedPattern(for: testName)
            let declaration = #"(?:func|def)\s+("# + escaped + #")\s*\("#
            XCTAssertFalse(
                try matches(pattern: declaration, in: testSources).isEmpty,
                "\(testName) is not a real Swift/Python test declaration"
            )
        }
    }

    private func testCertificate() throws -> SecCertificate {
        let fixture = """
        MIIBvzCCASgCCQCWZwVkxZUDQDANBgkqhkiG9w0BAQsFADAkMSIwIAYDVQQDDBlN
        T1NTIENhcHR1cmUgVGVzdCBGaXh0dXJlMB4XDTI2MDcyNjAyMjMxOFoXDTI2MDcy
        NzAyMjMxOFowJDEiMCAGA1UEAwwZTU9TUyBDYXB0dXJlIFRlc3QgRml4dHVyZTCB
        nzANBgkqhkiG9w0BAQEFAAOBjQAwgYkCgYEApC3PW4Izr+VU+uJmE9+1uKV9VVo
        glHQFIkOBKZ3UO218L35QVRo+V67IgDIuxKTEQsjqIFWi/pFAeTJtykP4nWDvqDJ
        4XMmJVsTTOGwfQ7Q6CoafBBV0DcvvgqvUMezLQihmfrensrPhGb06kEJgId7q0LA
        bow6DLcBtKSKm3OsCAwEAATANBgkqhkiG9w0BAQsFAAOBgQBS61haY4bsxRuxgxxH
        TXw2BHz6rooSSKktJ5SUCw03TffObW9LFWS+i7Aw/ddaMJHI03LM2lOPz9ZiC2FX
        pv/6V2MCyiBvtMJ/vNht7BNFxzYwyeMNLm1QNGwiGo6NZ/G7U9rgqrw2z/lEJ+6E
        hspPHgHJi69E6fC2EU4JUs3MCQ==
        """
        let der = try XCTUnwrap(
            Data(base64Encoded: fixture, options: .ignoreUnknownCharacters)
        )
        return try XCTUnwrap(SecCertificateCreateWithData(nil, der as CFData))
    }

    private func testTrust(certificate: SecCertificate) throws -> SecTrust {
        var trust: SecTrust?
        let status = SecTrustCreateWithCertificates(
            certificate,
            SecPolicyCreateBasicX509(),
            &trust
        )
        XCTAssertEqual(status, errSecSuccess)
        return try XCTUnwrap(trust)
    }

    private func packageRoot() -> URL {
        var url = URL(fileURLWithPath: #filePath)
        for _ in 0..<3 {
            url.deleteLastPathComponent()
        }
        return url
    }

    /// `macos/MOSSCapture` is two levels below the checkout, and the checkout is where the server
    /// source this package has to agree with lives.
    private func repositoryRoot() -> URL {
        packageRoot().deletingLastPathComponent().deletingLastPathComponent()
    }

    private func swiftSources(under root: URL) throws -> String {
        try textSources(under: root, pathExtension: "swift")
    }

    private func textSources(under root: URL, pathExtension: String) throws -> String {
        let enumerator = try XCTUnwrap(
            FileManager.default.enumerator(
                at: root,
                includingPropertiesForKeys: [.isRegularFileKey]
            )
        )
        var sources: [String] = []
        for case let url as URL in enumerator where url.pathExtension == pathExtension {
            sources.append(try String(contentsOf: url, encoding: .utf8))
        }
        return sources.joined(separator: "\n")
    }

    private func matches(pattern: String, in source: String) throws -> [String] {
        let regex = try NSRegularExpression(pattern: pattern)
        let range = NSRange(source.startIndex..., in: source)
        return regex.matches(in: source, range: range).compactMap { match in
            guard match.numberOfRanges > 1,
                  let capture = Range(match.range(at: 1), in: source) else {
                return nil
            }
            return String(source[capture])
        }
    }

    private func temporarySocketPath() -> String {
        FileManager.default.temporaryDirectory
            .appendingPathComponent("moss-control-\(UUID().uuidString).sock")
            .path
    }

    private func temporarySecretStorePath() -> String {
        FileManager.default.temporaryDirectory
            .appendingPathComponent("moss-capture-store-\(UUID().uuidString)")
            .appendingPathComponent("secrets.json")
            .path
    }

    private func fileMode(at path: String) throws -> UInt16 {
        try fileInfo(at: path).st_mode & 0o777
    }

    private func fileOwner(at path: String) throws -> uid_t {
        try fileInfo(at: path).st_uid
    }

    private func fileInode(at path: String) throws -> UInt64 {
        try fileInfo(at: path).st_ino
    }

    private func fileInfo(at path: String) throws -> stat {
        var info = stat()
        guard lstat(path, &info) == 0 else {
            throw CaptureSecurityError.secretStoreStatus(errno)
        }
        return info
    }

    private func waitForSocket(at path: String) throws {
        let deadline = Date(timeIntervalSinceNow: 2)
        while Date() < deadline {
            if FileManager.default.fileExists(atPath: path) {
                return
            }
            Thread.sleep(forTimeInterval: 0.01)
        }
        XCTFail("socket was not created")
    }

    private struct RawControlEnvelope: Encodable {
        var secret: String
        var request: ControlChannelRequest
    }

    private func rawControlFrame(command: String) throws -> Data {
        try rawControlFrame(request: ControlChannelRequest(command: command))
    }

    private func rawControlFrame(request: ControlChannelRequest) throws -> Data {
        try rawFrame(JSONEncoder().encode(RawControlEnvelope(secret: "control-secret", request: request)))
    }

    private func rawFrame(_ body: Data) -> Data {
        rawLengthPrefix(body.count) + body
    }

    private func rawLengthPrefix(_ byteCount: Int) -> Data {
        var length = UInt32(byteCount).bigEndian
        var data = Data()
        withUnsafeBytes(of: &length) { bytes in
            data.append(contentsOf: bytes)
        }
        return data
    }

    private func sendRawControlPayload(
        _ payload: Data,
        socketPath: String,
        halfCloseWrite: Bool = false
    ) throws -> ControlChannelResponse {
        let body = try sendRawControlPayloadBody(
            payload,
            socketPath: socketPath,
            halfCloseWrite: halfCloseWrite
        )
        return try JSONDecoder().decode(ControlChannelResponse.self, from: body)
    }

    private func sendRawControlPayloadBody(
        _ payload: Data,
        socketPath: String,
        halfCloseWrite: Bool = false
    ) throws -> Data {
        let fileDescriptor = socket(AF_UNIX, SOCK_STREAM, 0)
        XCTAssertGreaterThanOrEqual(fileDescriptor, 0)
        defer { close(fileDescriptor) }

        try connectRawSocket(fileDescriptor, socketPath: socketPath)
        try writeRawPayload(payload, to: fileDescriptor)
        if halfCloseWrite {
            shutdown(fileDescriptor, SHUT_WR)
        }
        return try readRawFrame(from: fileDescriptor)
    }

    private func connectRawSocket(_ fileDescriptor: Int32, socketPath: String) throws {
        let pathBytes = Array(socketPath.utf8)
        var address = sockaddr_un()
        address.sun_family = sa_family_t(AF_UNIX)
        #if os(macOS)
        address.sun_len = UInt8(MemoryLayout<sockaddr_un>.size)
        #endif
        withUnsafeMutableBytes(of: &address.sun_path) { rawBuffer in
            for index in pathBytes.indices {
                rawBuffer[index] = pathBytes[index]
            }
            rawBuffer[pathBytes.count] = 0
        }
        let length = socklen_t(MemoryLayout<sa_family_t>.size + pathBytes.count + 1)
        let result = withUnsafePointer(to: &address) { pointer in
            pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) { socketAddress in
                Darwin.connect(fileDescriptor, socketAddress, length)
            }
        }
        XCTAssertEqual(result, 0)
    }

    private func writeRawPayload(_ payload: Data, to fileDescriptor: Int32) throws {
        payload.withUnsafeBytes { rawBuffer in
            var offset = 0
            while offset < payload.count {
                let count = Darwin.write(
                    fileDescriptor,
                    rawBuffer.baseAddress!.advanced(by: offset),
                    payload.count - offset
                )
                XCTAssertGreaterThan(count, 0)
                offset += count
            }
        }
    }

    private func readRawFrame(from fileDescriptor: Int32) throws -> Data {
        let prefix = try readRawBytes(4, from: fileDescriptor)
        let length = prefix.withUnsafeBytes { rawBuffer in
            UInt32(bigEndian: rawBuffer.load(as: UInt32.self))
        }
        return try readRawBytes(Int(length), from: fileDescriptor)
    }

    private func readRawBytes(_ byteCount: Int, from fileDescriptor: Int32) throws -> Data {
        var data = Data(count: byteCount)
        var offset = 0
        while offset < byteCount {
            let count = data.withUnsafeMutableBytes { rawBuffer in
                Darwin.read(fileDescriptor, rawBuffer.baseAddress!.advanced(by: offset), byteCount - offset)
            }
            XCTAssertGreaterThan(count, 0)
            offset += count
        }
        return data
    }

    /// An emitter whose wire frame is a single sample, so one native buffer is one wire frame and
    /// the lane bookkeeping these tests are about — sequences, epochs, health counters, admission —
    /// stays legible. The whole lab timeline is shorter than one wire sample period, so the buffers
    /// read as one continuous run whatever tick values a test picks. The production grid
    /// (16 kHz, 8000-sample frames) and its timeline have their own nodes below.
    private func laboratoryEmitter() -> NativeLaneFrameEmitter {
        NativeLaneFrameEmitter(
            wireFormat: NativeLaneWireFormat(sampleRate: 16_000, frameSamples: 1),
            hostTime: MachTimebaseHostTimeConverter(numerator: 1, denominator: 1)
        )
    }

    /// A stated timebase far from 1:1, so the tick-to-nanosecond contract is checkable without
    /// depending on the timebase of whichever Mac runs the suite. It is the ratio measured on the
    /// capture Mac; the production converter asks CoreAudio for the real one.
    private var labTimebase: MachTimebaseHostTimeConverter {
        MachTimebaseHostTimeConverter(numerator: 125, denominator: 3)
    }

    private func labHostTicks(forNanoseconds nanoseconds: UInt64) -> UInt64 {
        nanoseconds * 3 / 125
    }

    /// Host ticks for the start of one device callback, on a timeline that never starts at zero —
    /// a zero host time is the invalid reading, not the first sample of a capture.
    private func deviceHostTicks(callbackIndex: Int, frameCount: Int, sampleRate: Int) -> UInt64 {
        let nanoseconds = 1_000_000_000
            + UInt64(callbackIndex) * UInt64(frameCount) * 1_000_000_000 / UInt64(sampleRate)
        return labHostTicks(forNanoseconds: nanoseconds)
    }

    /// One device callback's worth of audio at the device's own rate, carrying a tone so the
    /// converter has real content to filter.
    private func deviceBuffer(
        lane: CaptureLane,
        callbackIndex: Int,
        sampleRate: Int,
        frameCount: Int,
        deviceEpoch: UInt64 = 1,
        hostTicks: UInt64? = nil,
        discontinuity: Bool = false
    ) -> NativeCapturedAudioBuffer {
        let first = callbackIndex * frameCount
        let samples = (0..<frameCount).map { index -> Float in
            Float(sin(2.0 * Double.pi * 220.0 * Double(first + index) / Double(sampleRate)))
        }
        return NativeCapturedAudioBuffer(
            lane: lane,
            sampleRate: sampleRate,
            channelCount: 1,
            frameCount: frameCount,
            firstSampleMonotonicNS: hostTicks
                ?? deviceHostTicks(
                    callbackIndex: callbackIndex,
                    frameCount: frameCount,
                    sampleRate: sampleRate
                ),
            deviceEpoch: deviceEpoch,
            discontinuity: discontinuity,
            samples: samples
        )
    }

    private func nativeBuffer(
        lane: CaptureLane,
        timestamp: UInt64,
        deviceEpoch: UInt64,
        samples: [Float],
        discontinuity: Bool = false
    ) -> NativeCapturedAudioBuffer {
        NativeCapturedAudioBuffer(
            lane: lane,
            sampleRate: 16_000,
            channelCount: 1,
            frameCount: samples.count,
            firstSampleMonotonicNS: timestamp,
            deviceEpoch: deviceEpoch,
            discontinuity: discontinuity,
            samples: samples
        )
    }

    private func laneConfiguration() -> CaptureConfiguration {
        CaptureConfiguration(
            sessionID: "session-a",
            serverURL: URL(string: "https://moss.example")!
        )
    }

    private func jsonBody(_ request: URLRequest) throws -> [String: Any] {
        let data = try XCTUnwrap(request.httpBody)
        let object = try JSONSerialization.jsonObject(with: data)
        return try XCTUnwrap(object as? [String: Any])
    }

    // MARK: - C3c app-owned latency probe

    func testLatencySamplerMapsCommittedSamplesToTheMixerOriginOnOneCaptureClock() throws {
        XCTAssertEqual(
            1_000_000_000 % 16_000,
            0,
            "the wire rate must divide a second exactly, or the mapping adds rounding of its own"
        )
        let sampler = CaptureLatencySampler()
        sampler.noteLaneStates([
            laneStatus(.microphone, state: "capturing"),
            laneStatus(.system, state: "capturing")
        ])
        // The mixer's origin is the latest of the lanes' first capture instants, not the earliest.
        sampler.observeAcknowledgedFrame(
            lane: .microphone,
            captureTimestampNS: 1_000_000_000,
            sampleRate: 16_000,
            sampleCount: 8_000,
            discontinuity: false
        )
        sampler.observeAcknowledgedFrame(
            lane: .system,
            captureTimestampNS: 1_500_000_000,
            sampleRate: 16_000,
            sampleCount: 8_000,
            discontinuity: false
        )

        let origin: UInt64 = 1_500_000_000
        var committed = 40_000
        // The first reading has not been seen to advance, so it is only the baseline.
        sampler.observe(
            committedSamples: committed,
            atHostNanoseconds: origin + UInt64(committed) * 62_500 + 200_000_000
        )
        for latencyMS in [300, 500, 400, 900] {
            committed += 40_000
            sampler.observe(
                committedSamples: committed,
                atHostNanoseconds: origin + UInt64(committed) * 62_500 + UInt64(latencyMS) * 1_000_000
            )
        }

        let report = sampler.report(polling: false)
        XCTAssertTrue(report.mixerOriginResolved)
        XCTAssertEqual(report.committedLatency.count, 4, "the baseline reading is not a measurement")
        XCTAssertEqual(report.committedLatency.p50MS, 400)
        XCTAssertEqual(report.committedLatency.p95MS, 900)
        XCTAssertEqual(report.committedLatency.maxMS, 900)
        XCTAssertEqual(report.frameQuantisationMS, 500)
        XCTAssertFalse(report.sufficientSamples, "four advances is not the plan's twenty")
        XCTAssertNil(report.userVisibleMS, "no fetch distribution yet, so no gated number")
        XCTAssertEqual(report.rejectedNegative, 0)
        XCTAssertEqual(report.rejectedClockRegression, 0)
    }

    func testLatencySamplerRejectsNegativeRegressedAndPostBreakReadingsInsteadOfAveragingThem() throws {
        let sampler = CaptureLatencySampler()
        // A denied lane is excluded exactly as the server excludes a failed lane, so the origin is
        // the surviving lane's first capture instant.
        sampler.noteLaneStates([
            laneStatus(.microphone, state: "capturing"),
            laneStatus(.system, state: "failed", failureCode: "permissionDenied")
        ])
        sampler.observeAcknowledgedFrame(
            lane: .microphone,
            captureTimestampNS: 1_000_000_000,
            sampleRate: 16_000,
            sampleCount: 8_000,
            discontinuity: false
        )
        let origin: UInt64 = 1_000_000_000

        sampler.observe(committedSamples: 8_000, atHostNanoseconds: origin + 8_000 * 62_500 + 100_000_000)
        // Committed audio that claims to have arrived before it was captured is a broken clock
        // assumption, not a fast server.
        sampler.observe(committedSamples: 16_000, atHostNanoseconds: origin + 16_000 * 62_500 - 1)
        // A reading whose clock went backwards cannot be differenced against the previous one.
        sampler.observe(committedSamples: 24_000, atHostNanoseconds: origin + 500_000_000)
        sampler.observe(
            committedSamples: 32_000,
            atHostNanoseconds: origin + 32_000 * 62_500 + 250_000_000
        )

        var report = sampler.report(polling: false)
        XCTAssertEqual(report.committedLatency.count, 1)
        XCTAssertEqual(report.committedLatency.maxMS, 250)
        XCTAssertEqual(report.rejectedNegative, 1)
        XCTAssertEqual(report.rejectedClockRegression, 1)
        XCTAssertEqual(report.rejectedAfterTimelineBreak, 0)
        XCTAssertTrue(report.timelineIntact)

        sampler.observeAcknowledgedFrame(
            lane: .microphone,
            captureTimestampNS: origin + 4_000_000_000,
            sampleRate: 16_000,
            sampleCount: 8_000,
            discontinuity: true
        )
        sampler.observe(
            committedSamples: 40_000,
            atHostNanoseconds: origin + 40_000 * 62_500 + 250_000_000
        )
        report = sampler.report(polling: false)
        XCTAssertFalse(report.timelineIntact)
        XCTAssertEqual(report.committedLatency.count, 1, "a broken timeline stops producing figures")
        XCTAssertEqual(report.rejectedAfterTimelineBreak, 1)
    }

    func testLatencySamplerTreatsAShortFrameAsABreakOnlyWhenTheLaneKeepsGoing() throws {
        func sampler(withSuccessor: Bool) -> CaptureLatencySampler {
            let sampler = CaptureLatencySampler()
            sampler.noteLaneStates([laneStatus(.microphone, state: "capturing")])
            sampler.observeAcknowledgedFrame(
                lane: .microphone,
                captureTimestampNS: 1_000_000_000,
                sampleRate: 16_000,
                sampleCount: 8_000,
                discontinuity: false
            )
            sampler.observeAcknowledgedFrame(
                lane: .microphone,
                captureTimestampNS: 1_500_000_000,
                sampleRate: 16_000,
                sampleCount: 3_200,
                discontinuity: false
            )
            if withSuccessor {
                sampler.observeAcknowledgedFrame(
                    lane: .microphone,
                    captureTimestampNS: 1_700_000_000,
                    sampleRate: 16_000,
                    sampleCount: 8_000,
                    discontinuity: false
                )
            }
            return sampler
        }

        XCTAssertTrue(
            sampler(withSuccessor: false).report(polling: false).timelineIntact,
            "the meeting's trailing partial frame ends the stream; it is not a hole in it"
        )
        XCTAssertFalse(
            sampler(withSuccessor: true).report(polling: false).timelineIntact,
            "a short frame the lane then continues past is a hole in the middle of the timeline"
        )
    }

    func testLatencySamplerWaitsForEveryContributingLaneThenFreezesTheOrigin() throws {
        let sampler = CaptureLatencySampler()
        sampler.noteLaneStates([
            laneStatus(.microphone, state: "capturing"),
            laneStatus(.system, state: "capturing")
        ])
        sampler.observeAcknowledgedFrame(
            lane: .microphone,
            captureTimestampNS: 1_000_000_000,
            sampleRate: 16_000,
            sampleCount: 8_000,
            discontinuity: false
        )
        sampler.observe(committedSamples: 8_000, atHostNanoseconds: 20_000_000_000)
        sampler.observe(committedSamples: 16_000, atHostNanoseconds: 21_000_000_000)
        XCTAssertFalse(
            sampler.report(polling: false).mixerOriginResolved,
            "resolving on one lane would anchor the whole measurement to the wrong instant"
        )
        XCTAssertEqual(sampler.report(polling: false).committedLatency.count, 0)

        sampler.observeAcknowledgedFrame(
            lane: .system,
            captureTimestampNS: 1_500_000_000,
            sampleRate: 16_000,
            sampleCount: 8_000,
            discontinuity: false
        )
        let origin: UInt64 = 1_500_000_000
        sampler.observe(
            committedSamples: 24_000,
            atHostNanoseconds: origin + 24_000 * 62_500 + 500_000_000
        )
        // The system lane leaving does not move an origin the mixer has already frozen.
        sampler.noteLaneStates([
            laneStatus(.microphone, state: "capturing"),
            laneStatus(.system, state: "stopped")
        ])
        sampler.observe(
            committedSamples: 32_000,
            atHostNanoseconds: origin + 32_000 * 62_500 + 700_000_000
        )

        let report = sampler.report(polling: false)
        XCTAssertTrue(report.mixerOriginResolved)
        XCTAssertEqual(report.committedLatency.count, 1)
        XCTAssertEqual(report.committedLatency.maxMS, 700)
    }

    func testLatencyReportKeepsTheCommittedAndRenderComponentsSeparate() throws {
        let sampler = CaptureLatencySampler()
        sampler.noteLaneStates([laneStatus(.microphone, state: "capturing")])
        sampler.observeAcknowledgedFrame(
            lane: .microphone,
            captureTimestampNS: 1_000_000_000,
            sampleRate: 16_000,
            sampleCount: 8_000,
            discontinuity: false
        )
        let origin: UInt64 = 1_000_000_000
        var committed = 8_000
        sampler.observe(committedSamples: committed, atHostNanoseconds: origin + 8_000 * 62_500)
        for latencyMS in [1_200, 900, 1_500, 1_100] {
            committed += 8_000
            sampler.observe(
                committedSamples: committed,
                atHostNanoseconds: origin + UInt64(committed) * 62_500 + UInt64(latencyMS) * 1_000_000
            )
        }

        for milliseconds in [40, 60, 55, 90] {
            sampler.recordSnapshotFetch(nanoseconds: UInt64(milliseconds) * 1_000_000)
        }
        XCTAssertNil(
            sampler.report(polling: true).renderBoundMS,
            "the bound needs both routes; one of them is not a portal cycle"
        )
        for milliseconds in [30, 45, 35, 70] {
            sampler.recordEventsFetch(nanoseconds: UInt64(milliseconds) * 1_000_000)
        }

        let report = sampler.report(polling: true)
        XCTAssertEqual(report.portalCycleMS, 500)
        XCTAssertEqual(report.snapshotFetch.p95MS, 90)
        XCTAssertEqual(report.eventsFetch.p95MS, 70)
        XCTAssertEqual(report.renderBoundMS, 660)
        XCTAssertEqual(report.committedLatency.p95MS, 1_500)
        XCTAssertEqual(report.userVisibleMS, 2_160)
        XCTAssertEqual(
            report.userVisibleMS,
            try XCTUnwrap(report.committedLatency.p95MS) + (try XCTUnwrap(report.renderBoundMS)),
            "the gated number must stay the sum of the two recorded components"
        )
    }

    /// The gated latency number contains a term that asserts what the *server's* portal does, and
    /// the app schedules nothing from it. So the two values can drift apart in either direction and
    /// every existing assertion would still pass: moving this constant alone would take 500 ms off a
    /// reported number with no change to what a reader waits, and moving the portal's alone would
    /// hand a reader 500 ms the report never records. This node fails on either.
    func testPortalCycleContractMatchesTheServedPortalCadence() throws {
        let portal = try String(
            contentsOf: repositoryRoot().appendingPathComponent(
                "moss_transcribe_diarize/app/live_portal.py"
            ),
            encoding: .utf8
        )
        let declared = try matches(pattern: #"const pollDelayMs = (\d+);"#, in: portal)
        XCTAssertEqual(declared.count, 1, "the portal must declare its poll cadence exactly once")
        let servedMS = try XCTUnwrap(Double(try XCTUnwrap(declared.first)))

        // The declaration is only the cadence if it is also what schedules the next cycle; a
        // constant nothing reads would satisfy an equality check while the page polled at any rate.
        XCTAssertTrue(
            portal.contains("schedulePoll(pollDelayMs)"),
            "pollDelayMs must be what schedules the portal's next cycle"
        )

        // Compare against the number the report actually carries, not against the constant, so a
        // literal substituted into the report is caught as well as a moved constant.
        XCTAssertEqual(
            CaptureLatencySampler().report(polling: true).portalCycleMS,
            servedMS,
            "the reported render bound and the portal's actual poll schedule have drifted apart"
        )
    }

    func testLatencyProbePollsWithViewAuthorityAndEmitsOnlyAggregates() throws {
        let sessionStore = InMemoryCaptureSessionStore()
        try sessionStore.saveCaptureServerURL(URL(string: "https://moss.example")!)
        try sessionStore.saveCaptureSessionID("session-latency")
        try sessionStore.saveCaptureViewToken("view-token-secret")
        let client = RecordingLatencyHTTPClient()
        client.snapshotBody = try latencySnapshotBody(version: 7, committedSamples: 40_000)
        client.eventsBody = try latencyEventsBody(sequences: [3, 11, 8])
        let scheduler = FakeCaptureSchedulerAdapter()
        let sampler = CaptureLatencySampler()
        let probe = CaptureLatencyProbe(
            sampler: sampler,
            status: { CaptureStatus(running: true, sessionID: "session-latency", lanes: [], publishedFrameCount: 0, lastHealthSequence: nil) },
            sessionStore: sessionStore,
            clientProvider: RecordingCaptureHTTPClientProvider(client: client),
            certificatePin: StaticCaptureCertificatePinAdapter(pin: String(repeating: "a", count: 64)),
            clock: FakeCaptureClockAdapter(ticks: [0, 12_000_000, 0, 4_000_000, 0, 9_000_000, 0, 5_000_000]),
            hostTime: StaticCaptureHostTimeReader(nanoseconds: [30_000_000_000, 31_000_000_000]),
            scheduler: scheduler
        )

        _ = try probe.measure()
        scheduler.runScheduledOperation()

        XCTAssertEqual(client.requests.count, 2)
        let snapshotRequest = client.requests[0]
        let eventsRequest = client.requests[1]
        XCTAssertEqual(snapshotRequest.url?.path, "/api/live/sessions/session-latency/snapshot")
        XCTAssertNil(snapshotRequest.url?.query, "the first poll asks for the whole snapshot")
        XCTAssertEqual(eventsRequest.url?.path, "/api/live/sessions/session-latency/events")
        XCTAssertEqual(eventsRequest.url?.query, "since_seq=0")
        for request in client.requests {
            XCTAssertEqual(request.httpMethod, "GET")
            XCTAssertEqual(
                request.value(forHTTPHeaderField: "Authorization"),
                "Bearer view-token-secret"
            )
            XCTAssertFalse(
                try XCTUnwrap(request.url?.absoluteString).contains("view-token-secret"),
                "view authority belongs in the header, never in a URL a proxy or log would keep"
            )
            let carryingHeaders = (request.allHTTPHeaderFields ?? [:])
                .filter { $0.value.contains("view-token-secret") }
                .keys
                .sorted()
            XCTAssertEqual(
                carryingHeaders,
                ["Authorization"],
                "the token goes to exactly one place on the wire"
            )
            XCTAssertNil(request.httpBody)
        }

        // The cursors advance, so the second poll costs what the portal's steady state costs.
        scheduler.runScheduledOperation()
        XCTAssertEqual(client.requests.count, 4)
        XCTAssertEqual(client.requests[2].url?.query, "since_version=7")
        XCTAssertEqual(client.requests[3].url?.query, "since_seq=11")

        let dispatcher = ControlCommandDispatcher(
            controller: CaptureController.fakeForLocalDevelopment(),
            pairingExchange: StaticPairingExchange(result: CapturePairingResult(sessionID: "unused")),
            latencyProbe: probe
        )
        let response = try dispatcher.dispatch(ControlChannelRequest(command: "latency"))
        let encoded = String(decoding: try JSONEncoder().encode(response), as: UTF8.self)
        XCTAssertTrue(response.ok)
        XCTAssertEqual(response.latency?.schema, "moss-capture-latency.v1")
        XCTAssertEqual(response.latency?.snapshotFetch.count, 2)
        XCTAssertEqual(response.latency?.eventsFetch.count, 2)
        XCTAssertFalse(encoded.contains("view-token-secret"))
        XCTAssertFalse(encoded.contains("moss.example"))
        XCTAssertFalse(encoded.contains("session-latency"))
    }

    func testLatencyProbeIsDefaultOffAndAsksNothingUntilAFigureIsRequested() throws {
        let sessionStore = InMemoryCaptureSessionStore()
        try sessionStore.saveCaptureServerURL(URL(string: "https://moss.example")!)
        try sessionStore.saveCaptureSessionID("session-latency")
        try sessionStore.saveCaptureViewToken("view-token-secret")
        let client = RecordingLatencyHTTPClient()
        let scheduler = FakeCaptureSchedulerAdapter()
        let running = MutableFlag(value: false)
        let probe = CaptureLatencyProbe(
            sampler: CaptureLatencySampler(),
            status: {
                CaptureStatus(
                    running: running.value,
                    sessionID: "session-latency",
                    lanes: [],
                    publishedFrameCount: 0,
                    lastHealthSequence: nil
                )
            },
            sessionStore: sessionStore,
            clientProvider: RecordingCaptureHTTPClientProvider(client: client),
            certificatePin: StaticCaptureCertificatePinAdapter(pin: String(repeating: "a", count: 64)),
            clock: FakeCaptureClockAdapter(ticks: []),
            hostTime: StaticCaptureHostTimeReader(nanoseconds: []),
            scheduler: scheduler
        )

        XCTAssertTrue(scheduler.labels.isEmpty, "constructing the probe must not start polling")
        XCTAssertTrue(client.requests.isEmpty)

        let idle = try probe.measure()
        XCTAssertFalse(idle.polling, "there is no session to measure, so nothing is scheduled")
        XCTAssertTrue(scheduler.labels.isEmpty)

        running.value = true
        _ = try probe.measure()
        _ = try probe.measure()
        XCTAssertEqual(scheduler.labels, ["moss.capture.latency"], "asking twice must not poll twice")

        let noProbe = ControlCommandDispatcher(
            controller: CaptureController.fakeForLocalDevelopment(),
            pairingExchange: StaticPairingExchange(result: CapturePairingResult(sessionID: "unused"))
        )
        XCTAssertThrowsError(try noProbe.dispatch(ControlChannelRequest(command: "latency"))) { error in
            XCTAssertEqual(error as? CaptureSecurityError, .latencyProbeUnavailable)
        }
    }

    func testLatencyProbeStopsWithTheSessionAndStaysReadableAfterwards() throws {
        let sessionStore = InMemoryCaptureSessionStore()
        try sessionStore.saveCaptureServerURL(URL(string: "https://moss.example")!)
        try sessionStore.saveCaptureSessionID("session-latency")
        try sessionStore.saveCaptureViewToken("view-token-secret")
        let client = RecordingLatencyHTTPClient()
        client.snapshotBody = try latencySnapshotBody(version: 3, committedSamples: 8_000)
        client.eventsBody = try latencyEventsBody(sequences: [1])
        let scheduler = FakeCaptureSchedulerAdapter()
        let running = MutableFlag(value: true)
        let probe = CaptureLatencyProbe(
            sampler: CaptureLatencySampler(),
            status: {
                CaptureStatus(
                    running: running.value,
                    sessionID: "session-latency",
                    lanes: [],
                    publishedFrameCount: 0,
                    lastHealthSequence: nil
                )
            },
            sessionStore: sessionStore,
            clientProvider: RecordingCaptureHTTPClientProvider(client: client),
            certificatePin: StaticCaptureCertificatePinAdapter(pin: String(repeating: "a", count: 64)),
            clock: FakeCaptureClockAdapter(ticks: [0, 7_000_000, 0, 3_000_000]),
            hostTime: StaticCaptureHostTimeReader(nanoseconds: [50_000_000_000]),
            scheduler: scheduler
        )

        _ = try probe.measure()
        scheduler.runScheduledOperation()
        XCTAssertEqual(client.requests.count, 2)

        running.value = false
        scheduler.runScheduledOperation()
        XCTAssertEqual(client.requests.count, 2, "view authority dies with the session")

        let afterStop = try probe.measure()
        XCTAssertFalse(afterStop.polling)
        XCTAssertEqual(afterStop.snapshotFetch.maxMS, 7, "what was measured stays readable")
        XCTAssertEqual(client.requests.count, 2, "reading the result must not restart the poll")

        let stopping = RecordingLatencyProbe()
        let dispatcher = ControlCommandDispatcher(
            controller: try startedControllerForLatency(),
            pairingExchange: StaticPairingExchange(result: CapturePairingResult(sessionID: "unused")),
            latencyProbe: stopping
        )
        _ = try dispatcher.dispatch(ControlChannelRequest(command: "stop"))
        XCTAssertEqual(stopping.stopCount, 1)
        XCTAssertEqual(stopping.measureCount, 0)
    }

    func testAcknowledgedFrameObserverSeesOnlyAcceptedAudioFactsAndNeverPCM() throws {
        let observer = RecordingAcknowledgedFrameObserver()
        let frame = CaptureFrame(
            lane: .microphone,
            sequence: 0,
            sampleRate: 16_000,
            sampleCount: 8_000,
            captureTimestampNS: 4_200_000_000,
            deviceEpoch: 1,
            silent: false,
            discontinuity: false,
            pcm16: Data(repeating: 7, count: 16_000)
        )
        let refusing = CaptureController(
            source: FakeCaptureSourceAdapter(frames: [frame]),
            transport: AlwaysFailingCaptureTransport(),
            keyStore: FakeCaptureKeyStoreAdapter(),
            clock: FakeCaptureClockAdapter(),
            scheduler: FakeCaptureSchedulerAdapter(),
            health: FakeCaptureHealthAdapter(),
            frameObserver: observer
        )
        _ = try refusing.start(configuration: laneConfiguration())
        XCTAssertEqual(observer.sessionStarts, 1)
        XCTAssertTrue(
            observer.observations.isEmpty,
            "a retained frame has not entered the server's timeline yet"
        )

        let accepting = CaptureController(
            source: FakeCaptureSourceAdapter(frames: [frame]),
            transport: FakeCaptureTransportAdapter(),
            keyStore: FakeCaptureKeyStoreAdapter(),
            clock: FakeCaptureClockAdapter(),
            scheduler: FakeCaptureSchedulerAdapter(),
            health: FakeCaptureHealthAdapter(),
            frameObserver: observer
        )
        _ = try accepting.start(configuration: laneConfiguration())
        XCTAssertEqual(observer.sessionStarts, 2, "a new session forgets the previous timeline")
        XCTAssertEqual(observer.observations.count, 1)
        let observed = try XCTUnwrap(observer.observations.first)
        XCTAssertEqual(observed.lane, .microphone)
        XCTAssertEqual(observed.captureTimestampNS, 4_200_000_000)
        XCTAssertEqual(observed.sampleRate, 16_000)
        XCTAssertEqual(observed.sampleCount, 8_000)
        XCTAssertFalse(observed.discontinuity)

        let controllerSource = try String(
            contentsOf: packageRoot()
                .appendingPathComponent("Sources/MOSSCaptureCore/CaptureController.swift"),
            encoding: .utf8
        )
        let acknowledge = try XCTUnwrap(controllerSource.range(of: "outbox.acknowledge("))
        let observe = try XCTUnwrap(controllerSource.range(of: "frameObserver?.observeAcknowledgedFrame("))
        XCTAssertTrue(
            acknowledge.lowerBound < observe.lowerBound,
            "the observation follows the acknowledgement, so it only ever reports accepted audio"
        )
        let probeSource = try String(
            contentsOf: packageRoot()
                .appendingPathComponent("Sources/MOSSCaptureCore/CaptureLatencyProbe.swift"),
            encoding: .utf8
        )
        for forbidden in ["pcm16", "pcm_base64", "loadCaptureBearerToken", "transcript\""] {
            XCTAssertFalse(
                probeSource.contains(forbidden),
                "the measurement path must not be able to reach \(forbidden)"
            )
        }
    }

    private func laneStatus(
        _ lane: CaptureLane,
        state: String,
        failureCode: String? = nil
    ) -> CaptureLaneStatus {
        CaptureLaneStatus(
            lane: lane,
            sequence: 0,
            deviceEpoch: 1,
            state: state,
            failureCode: failureCode
        )
    }

    private func latencySnapshotBody(version: Int, committedSamples: Int) throws -> Data {
        try JSONSerialization.data(
            withJSONObject: [
                "snapshot": [
                    "session_id": "session-latency",
                    "session": [
                        "version": version,
                        "status": "active",
                        "committed_samples": committedSamples
                    ]
                ],
                "unchanged": false
            ]
        )
    }

    private func latencyEventsBody(sequences: [Int]) throws -> Data {
        try JSONSerialization.data(
            withJSONObject: [
                "events": sequences.map { sequence in
                    ["seq": sequence, "kind": "committed", "payload": ["transcript": "hello"]]
                }
            ]
        )
    }

    private func startedControllerForLatency() throws -> CaptureController {
        let controller = CaptureController(
            source: FakeCaptureSourceAdapter(frames: []),
            transport: FakeCaptureTransportAdapter(),
            keyStore: FakeCaptureKeyStoreAdapter(),
            clock: FakeCaptureClockAdapter(),
            scheduler: FakeCaptureSchedulerAdapter(),
            health: FakeCaptureHealthAdapter()
        )
        _ = try controller.start(configuration: laneConfiguration())
        return controller
    }
}

private final class InMemoryCaptureSessionStore: CaptureSessionStoreAdapter {
    private var serverURL: URL?
    private var sessionID: String?
    private var viewToken: String?

    func saveCaptureServerURL(_ serverURL: URL) throws {
        self.serverURL = serverURL
    }

    func saveCaptureSessionID(_ sessionID: String) throws {
        self.sessionID = sessionID
    }

    func saveCaptureViewToken(_ viewToken: String) throws {
        self.viewToken = viewToken
    }

    func loadCaptureServerURL() throws -> URL? {
        serverURL
    }

    func loadCaptureSessionID() throws -> String? {
        sessionID
    }

    func loadCaptureViewToken() throws -> String? {
        viewToken
    }
}

private final class RecordingLatencyHTTPClient: CaptureHTTPClient {
    private(set) var requests: [URLRequest] = []
    var snapshotBody = Data()
    var eventsBody = Data()
    var statusCode = 200

    func send(_ request: URLRequest) throws -> CaptureHTTPResponse {
        requests.append(request)
        let isSnapshot = request.url?.path.hasSuffix("/snapshot") ?? false
        return CaptureHTTPResponse(
            statusCode: statusCode,
            body: isSnapshot ? snapshotBody : eventsBody
        )
    }
}

private struct StaticCaptureHostTimeReader: CaptureHostTimeReading {
    private let readings: CaptureHostTimeReadings

    init(nanoseconds: [UInt64]) {
        readings = CaptureHostTimeReadings(nanoseconds: nanoseconds)
    }

    func hostNanoseconds() -> UInt64? {
        readings.next()
    }
}

private final class CaptureHostTimeReadings: @unchecked Sendable {
    private let lock = NSLock()
    private var nanoseconds: [UInt64]

    init(nanoseconds: [UInt64]) {
        self.nanoseconds = nanoseconds
    }

    func next() -> UInt64? {
        lock.lock()
        defer { lock.unlock() }
        return nanoseconds.isEmpty ? nil : nanoseconds.removeFirst()
    }
}

private final class MutableFlag {
    var value: Bool

    init(value: Bool) {
        self.value = value
    }
}

private final class RecordingLatencyProbe: CaptureLatencyProbing {
    private(set) var measureCount = 0
    private(set) var stopCount = 0

    func measure() throws -> CaptureLatencyReport {
        measureCount += 1
        return CaptureLatencyReport()
    }

    func stop() {
        stopCount += 1
    }
}

private final class RecordingAcknowledgedFrameObserver: CaptureAcknowledgedFrameObserving, @unchecked Sendable {
    struct Observation: Equatable {
        var lane: CaptureLane
        var captureTimestampNS: UInt64
        var sampleRate: Int
        var sampleCount: Int
        var discontinuity: Bool
    }

    private let lock = NSLock()
    private var starts = 0
    private var recorded: [Observation] = []

    var sessionStarts: Int {
        lock.lock()
        defer { lock.unlock() }
        return starts
    }

    var observations: [Observation] {
        lock.lock()
        defer { lock.unlock() }
        return recorded
    }

    func observeSessionStart() {
        lock.lock()
        starts += 1
        lock.unlock()
    }

    func observeAcknowledgedFrame(
        lane: CaptureLane,
        captureTimestampNS: UInt64,
        sampleRate: Int,
        sampleCount: Int,
        discontinuity: Bool
    ) {
        lock.lock()
        recorded.append(
            Observation(
                lane: lane,
                captureTimestampNS: captureTimestampNS,
                sampleRate: sampleRate,
                sampleCount: sampleCount,
                discontinuity: discontinuity
            )
        )
        lock.unlock()
    }
}

private final class AlwaysFailingCaptureTransport: CaptureTransportAdapter {
    func publish(frame: CaptureFrame, configuration: CaptureConfiguration) throws {
        throw CaptureHTTPTransportError.nonSuccessStatus(503)
    }
}

/// A source whose audio only becomes available once it has been stopped, which is how the real
/// source behaves for the trailing partial frame: the converters are flushed by the stop.
private final class TerminalTailCaptureSource: CaptureSourceAdapter {
    private let tail: [CaptureFrame]
    private var stopped = false
    private var handedOver = false

    init(tail: [CaptureFrame]) {
        self.tail = tail
    }

    func start(configuration: CaptureConfiguration) throws {}

    func pendingFrames() throws -> [CaptureFrame] {
        guard stopped, !handedOver else {
            return []
        }
        handedOver = true
        return tail
    }

    func status() -> [CaptureLaneStatus] {
        CaptureLane.allCases.map {
            CaptureLaneStatus(
                lane: $0,
                sequence: 0,
                deviceEpoch: 0,
                state: stopped ? "stopped" : "capturing"
            )
        }
    }

    func stop(deadline: Date) throws {
        stopped = true
    }
}

private final class RecordingNativeCaptureComponent:
    NativeAudioCaptureComponent,
    NativeLaneHealthReportingComponent
{
    private let buffersOnStart: [NativeCapturedAudioBuffer]
    private let startError: Error?
    private let emitLateFactOnStop: Bool
    private weak var healthSink: NativeLaneHealthFactSink?
    private var healthLane = CaptureLane.system
    private var healthGeneration: UInt64 = 0
    private(set) var startCount = 0
    private(set) var stopCount = 0
    private(set) var lateFactWasRejected: Bool?

    init(
        buffersOnStart: [NativeCapturedAudioBuffer] = [],
        startError: Error? = nil,
        emitLateFactOnStop: Bool = false
    ) {
        self.buffersOnStart = buffersOnStart
        self.startError = startError
        self.emitLateFactOnStop = emitLateFactOnStop
    }

    func attachHealthSink(
        _ sink: NativeLaneHealthFactSink,
        lane: CaptureLane,
        generation: UInt64
    ) {
        healthSink = sink
        healthLane = lane
        healthGeneration = generation
    }

    func start(queue: RealTimeNativeAudioBufferQueue) throws {
        startCount += 1
        if let startError {
            throw startError
        }
        for buffer in buffersOnStart {
            queue.enqueueFromRealtimeCallback(buffer)
        }
    }

    func stop() {
        stopCount += 1
        guard emitLateFactOnStop, let healthSink else {
            return
        }
        healthSink.enqueue(
            .unexpectedCaptureError("late component teardown callback"),
            lane: healthLane,
            generation: healthGeneration
        )
        lateFactWasRejected =
            (healthSink as? NativeLaneHealth)?.failure(for: healthLane) == nil
    }
}

/// Collects permission answers that arrive on whichever thread the requester chooses.
private final class RecordedPermissionAnswers: @unchecked Sendable {
    private let lock = NSLock()
    private var recorded: [NativeLanePermissionFact] = []

    var values: [NativeLanePermissionFact] {
        lock.lock()
        defer { lock.unlock() }
        return recorded
    }

    func append(_ decision: NativeLanePermissionFact) {
        lock.lock()
        recorded.append(decision)
        lock.unlock()
    }
}

/// A lane that owns an explicit permission request, like the real microphone. The answer is
/// delivered only when the test calls `answerPermissionRequest`, which is how macOS behaves: the
/// request returns immediately and the user replies whenever they reply.
private final class PermissionGatedNativeCaptureComponent:
    NativeAudioCaptureComponent,
    NativeLaneHealthReportingComponent,
    NativeLanePermissionRequesting
{
    private let buffersOnStart: [NativeCapturedAudioBuffer]
    private let startError: Error?
    private var authorizationState: NativeLanePermissionFact
    private var outstanding: [@Sendable (NativeLanePermissionFact) -> Void] = []
    private(set) var requestCount = 0
    private(set) var startCount = 0
    private(set) var stopCount = 0

    init(
        authorization: NativeLanePermissionFact,
        buffersOnStart: [NativeCapturedAudioBuffer] = [],
        startError: Error? = nil
    ) {
        self.authorizationState = authorization
        self.buffersOnStart = buffersOnStart
        self.startError = startError
    }

    var isPromptOutstanding: Bool {
        !outstanding.isEmpty
    }

    func authorization() -> NativeLanePermissionFact {
        authorizationState
    }

    func requestAuthorization(
        _ completion: @escaping @Sendable (NativeLanePermissionFact) -> Void
    ) {
        requestCount += 1
        outstanding.append(completion)
    }

    func answerPermissionRequest(_ decision: NativeLanePermissionFact) {
        authorizationState = decision
        let completions = outstanding
        outstanding.removeAll()
        for completion in completions {
            completion(decision)
        }
    }

    func attachHealthSink(
        _ sink: NativeLaneHealthFactSink,
        lane: CaptureLane,
        generation: UInt64
    ) {}

    func start(queue: RealTimeNativeAudioBufferQueue) throws {
        startCount += 1
        if let startError {
            throw startError
        }
        for buffer in buffersOnStart {
            queue.enqueueFromRealtimeCallback(buffer)
        }
    }

    func stop() {
        stopCount += 1
    }
}

private final class RecordingSystemAudioTapDriver: SystemAudioTapDriver {
    private let startError: Error?
    private(set) var events: [String] = []
    private var lifecycleHandler: ((SystemAudioTapDeviceObservation) -> Void)?
    private var removedLifecycleHandler: ((SystemAudioTapDeviceObservation) -> Void)?

    init(startError: Error? = nil) {
        self.startError = startError
    }

    func createProcessTap(description: CATapDescription) throws -> AudioObjectID {
        events.append("AudioHardwareCreateProcessTap")
        return AudioObjectID(101)
    }

    func createAggregateDevice(for description: CATapDescription) throws -> AudioObjectID {
        events.append("AudioHardwareCreateAggregateDevice")
        return AudioObjectID(202)
    }

    func installDeviceLifecycleListeners(
        on aggregateDeviceID: AudioObjectID,
        handler: @escaping (SystemAudioTapDeviceObservation) -> Void
    ) throws {
        events.append("AudioObjectAddPropertyListenerBlock")
        lifecycleHandler = handler
    }

    func removeDeviceLifecycleListeners(on aggregateDeviceID: AudioObjectID) {
        events.append("AudioObjectRemovePropertyListenerBlock")
        removedLifecycleHandler = lifecycleHandler
        lifecycleHandler = nil
    }

    func createIOProc(
        on aggregateDeviceID: AudioObjectID,
        queue: RealTimeNativeAudioBufferQueue,
        sampleRate: Int,
        deviceEpoch: UInt64
    ) throws {
        events.append("AudioDeviceCreateIOProcIDWithBlock")
    }

    func startDevice(_ aggregateDeviceID: AudioObjectID) throws {
        events.append("AudioDeviceStart")
        if let startError {
            throw startError
        }
    }

    func stopDevice(_ aggregateDeviceID: AudioObjectID) {
        events.append("AudioDeviceStop")
    }

    func destroyIOProc(on aggregateDeviceID: AudioObjectID) {
        events.append("AudioDeviceDestroyIOProcID")
    }

    func destroyAggregateDevice(_ aggregateDeviceID: AudioObjectID) {
        events.append("AudioHardwareDestroyAggregateDevice")
    }

    func destroyProcessTap(_ tapID: AudioObjectID) {
        events.append("AudioHardwareDestroyProcessTap")
    }

    func emit(_ observation: SystemAudioTapDeviceObservation) {
        lifecycleHandler?(observation)
    }

    func emitAfterRemoval(_ observation: SystemAudioTapDeviceObservation) {
        removedLifecycleHandler?(observation)
    }
}

private final class RecordingMicrophoneCaptureDriver: MicrophoneCaptureDriver {
    private(set) var events: [String] = []
    private var permission: NativeLanePermissionFact
    var currentDeviceID: AudioDeviceID
    var currentDeviceError: Error?
    var startError: Error?
    private var observationHandler: (@Sendable (MicrophoneCaptureEngineObservation) -> Void)?
    private var removedObservationHandler: (@Sendable (MicrophoneCaptureEngineObservation) -> Void)?
    private var outstandingPermissionRequests: [@Sendable (NativeLanePermissionFact) -> Void] = []

    init(
        permission: NativeLanePermissionFact,
        currentDeviceID: AudioDeviceID,
        startError: Error? = nil
    ) {
        self.permission = permission
        self.currentDeviceID = currentDeviceID
        self.startError = startError
    }

    func recordPermission() -> NativeLanePermissionFact {
        events.append("recordPermission")
        return permission
    }

    func requestRecordPermission(
        _ completion: @escaping @Sendable (NativeLanePermissionFact) -> Void
    ) {
        events.append("requestRecordPermission")
        outstandingPermissionRequests.append(completion)
    }

    func answerRecordPermissionRequest(_ decision: NativeLanePermissionFact) {
        permission = decision
        let completions = outstandingPermissionRequests
        outstandingPermissionRequests.removeAll()
        for completion in completions {
            completion(decision)
        }
    }

    func currentInputDeviceID() throws -> AudioDeviceID {
        events.append("kAudioOutputUnitProperty_CurrentDevice")
        if let currentDeviceError {
            throw currentDeviceError
        }
        return currentDeviceID
    }

    func installConfigurationChangeHandler(
        _ handler: @escaping @Sendable (MicrophoneCaptureEngineObservation) -> Void
    ) throws {
        events.append("AVAudioEngineConfigurationChange")
        observationHandler = handler
    }

    func removeConfigurationChangeHandler() {
        events.append("removeConfigurationChangeHandler")
        removedObservationHandler = observationHandler
        observationHandler = nil
    }

    func installTap(queue: RealTimeNativeAudioBufferQueue, deviceEpoch: UInt64) throws {
        events.append("installTap")
    }

    func startEngine() throws {
        events.append("AVAudioEngine.start")
        if let startError {
            throw startError
        }
    }

    func stopEngine() {
        events.append("AVAudioEngine.stop")
    }

    func removeTap() {
        events.append("removeTap")
    }

    func emit(_ observation: MicrophoneCaptureEngineObservation) {
        observationHandler?(observation)
    }

    func emitAfterRemoval(_ observation: MicrophoneCaptureEngineObservation) {
        removedObservationHandler?(observation)
    }
}

private final class RecordingMicrophoneCaptureReconciliationScheduler:
    MicrophoneCaptureReconciliationScheduling,
    @unchecked Sendable
{
    private let lock = NSLock()
    private var operations: [@Sendable () -> Void] = []

    var pendingCount: Int {
        lock.lock()
        let count = operations.count
        lock.unlock()
        return count
    }

    func schedule(_ operation: @escaping @Sendable () -> Void) {
        lock.lock()
        operations.append(operation)
        lock.unlock()
    }

    func runNext() {
        lock.lock()
        let operation = operations.removeFirst()
        lock.unlock()
        operation()
    }
}

private final class RecordingCaptureHTTPClient: CaptureHTTPClient {
    private(set) var requests: [URLRequest] = []
    var response = CaptureHTTPResponse(statusCode: 200)

    func send(_ request: URLRequest) throws -> CaptureHTTPResponse {
        requests.append(request)
        return response
    }
}

private final class RecordingCaptureHTTPClientProvider: CaptureHTTPClientProvider {
    let client: RecordingCaptureHTTPClient
    private let providedClient: CaptureHTTPClient
    private(set) var requestedPins: [String?] = []

    init() {
        let client = RecordingCaptureHTTPClient()
        self.client = client
        providedClient = client
    }

    init(client: CaptureHTTPClient) {
        self.client = RecordingCaptureHTTPClient()
        providedClient = client
    }

    func client(certificatePinSHA256Hex: String?) throws -> CaptureHTTPClient {
        requestedPins.append(certificatePinSHA256Hex)
        guard let certificatePinSHA256Hex, !certificatePinSHA256Hex.isEmpty else {
            throw CaptureHTTPTransportError.missingCertificatePin
        }
        return providedClient
    }
}

private final class QueuedCaptureHTTPClient: CaptureHTTPClient {
    private(set) var requests: [URLRequest] = []
    private var responses: [CaptureHTTPResponse]

    init(responses: [CaptureHTTPResponse]) {
        self.responses = responses
    }

    func send(_ request: URLRequest) throws -> CaptureHTTPResponse {
        requests.append(request)
        return responses.removeFirst()
    }
}

private final class RecordingCaptureTransportAdapter: CaptureTransportAdapter {
    private(set) var configurations: [CaptureConfiguration] = []

    func publish(frame: CaptureFrame, configuration: CaptureConfiguration) throws {
        configurations.append(configuration)
    }
}

private struct StaticCaptureCertificatePinAdapter: CaptureCertificatePinAdapter {
    var pin: String?

    func loadCaptureCertificatePin() throws -> String? {
        pin
    }
}

private final class RecordingCaptureCertificatePinStore: CaptureCertificatePinStoreAdapter {
    private(set) var savedPins: [String] = []

    func saveCaptureCertificatePin(_ pin: String) throws {
        savedPins.append(pin)
    }
}

private struct StaticCaptureDeviceIdentityAdapter: CaptureDeviceIdentityAdapter {
    var deviceID: String

    func loadDeviceID() throws -> String {
        deviceID
    }
}

private struct TestPairingResponseBody: Encodable {
    var deviceID: String
    var deviceToken: String

    enum CodingKeys: String, CodingKey {
        case deviceID = "device_id"
        case deviceToken = "device_token"
    }
}

private struct TestSessionResponseBody: Encodable {
    var id: String
    var ownerDeviceID: String
    var viewToken: String

    enum CodingKeys: String, CodingKey {
        case id
        case ownerDeviceID = "owner_device_id"
        case viewToken = "view_token"
    }
}

private final class FailOnceScheduledHealthAdapter: CaptureHealthAdapter {
    private(set) var attemptCount = 0

    func emit(
        status: CaptureStatus,
        configuration: CaptureConfiguration,
        sentMonotonicNS: UInt64
    ) throws {
        attemptCount += 1
        if attemptCount == 2 {
            throw NativeCaptureError.transportUnavailable("heartbeat")
        }
    }
}

private final class FailOnceHTTPTransportHealthAdapter: CaptureHealthAdapter {
    private(set) var attemptCount = 0

    func emit(
        status: CaptureStatus,
        configuration: CaptureConfiguration,
        sentMonotonicNS: UInt64
    ) throws {
        attemptCount += 1
        if attemptCount == 2 {
            throw CaptureHTTPTransportError.nonSuccessStatus(503)
        }
    }
}

/// A server that accepts the first heartbeat and then refuses the session, the way a released
/// session does. `refusedAttempts` narrows that to named attempts, so a test can also ask what
/// happens when the refusal is followed by an accepted request.
private final class ReleasedSessionHealthAdapter: CaptureHealthAdapter {
    private let refusedStatusCode: Int
    private let refusedAttempts: Set<Int>?
    private(set) var attemptCount = 0

    init(refusedStatusCode: Int, refusedAttempts: Set<Int>? = nil) {
        self.refusedStatusCode = refusedStatusCode
        self.refusedAttempts = refusedAttempts
    }

    func emit(
        status: CaptureStatus,
        configuration: CaptureConfiguration,
        sentMonotonicNS: UInt64
    ) throws {
        attemptCount += 1
        let refused = refusedAttempts.map { $0.contains(attemptCount) } ?? (attemptCount > 1)
        if refused {
            throw CaptureHTTPTransportError.nonSuccessStatus(refusedStatusCode)
        }
    }
}

private final class RecordingPairingExchange: CapturePairingExchangeAdapter {
    private(set) var serverURL: URL?
    private(set) var pairingPayload: Data?

    func pair(serverURL: URL, pairingPayload: Data) throws -> CapturePairingResult {
        self.serverURL = serverURL
        self.pairingPayload = pairingPayload
        return CapturePairingResult(sessionID: "session-from-pairing", captureBearerToken: "capture-token")
    }
}

private struct StaticPairingExchange: CapturePairingExchangeAdapter {
    var result: CapturePairingResult

    func pair(serverURL: URL, pairingPayload: Data) throws -> CapturePairingResult {
        result
    }
}

private final class TestErrorBox: @unchecked Sendable {
    private let lock = NSLock()
    private var error: Error?

    func store(_ error: Error) {
        lock.lock()
        self.error = error
        lock.unlock()
    }

    func load() -> Error? {
        lock.lock()
        defer { lock.unlock() }
        return error
    }
}

private struct SecretBearingControlError: Error, CustomStringConvertible {
    let secret: String

    var description: String {
        secret
    }
}

private final class LoggedLineBox: @unchecked Sendable {
    private let lock = NSLock()
    private var storage: [String] = []

    var lines: [String] {
        lock.lock()
        defer { lock.unlock() }
        return storage
    }

    func append(_ line: String) {
        lock.lock()
        storage.append(line)
        lock.unlock()
    }
}

private final class RecordingControlChannelFailureLog: ControlChannelFailureLogging, @unchecked Sendable {
    struct Record: Equatable {
        var command: String?
        var detail: ControlChannelErrorDetail
    }

    private let lock = NSLock()
    private var storage: [Record] = []

    var records: [Record] {
        lock.lock()
        defer { lock.unlock() }
        return storage
    }

    func recordUnclassifiedFailure(command: String?, detail: ControlChannelErrorDetail) {
        lock.lock()
        storage.append(Record(command: command, detail: detail))
        lock.unlock()
    }
}

private final class RecordingCaptureLaneFailureLog: CaptureLaneFailureLogging, @unchecked Sendable {
    private let lock = NSLock()
    private var storage: [CaptureLaneStatus] = []

    var records: [CaptureLaneStatus] {
        lock.lock()
        defer { lock.unlock() }
        return storage
    }

    func recordLaneFailure(_ status: CaptureLaneStatus) {
        lock.lock()
        storage.append(status)
        lock.unlock()
    }
}

private final class ThrowingCaptureHealthAdapter: CaptureHealthAdapter {
    private let error: Error

    init(error: Error) {
        self.error = error
    }

    func emit(
        status: CaptureStatus,
        configuration: CaptureConfiguration,
        sentMonotonicNS: UInt64
    ) throws {
        throw error
    }
}

private final class CaptureStatusBox: @unchecked Sendable {
    private let lock = NSLock()
    private var statuses: [CaptureStatus] = []

    func append(_ status: CaptureStatus) {
        lock.lock()
        statuses.append(status)
        lock.unlock()
    }

    func load() -> [CaptureStatus] {
        lock.lock()
        defer { lock.unlock() }
        return statuses
    }
}

private final class ScheduledPumpRunner: @unchecked Sendable {
    private let scheduler: ConcurrentCaptureScheduler

    init(scheduler: ConcurrentCaptureScheduler) {
        self.scheduler = scheduler
    }

    func run() {
        scheduler.runScheduledOperation()
    }
}

private final class ConcurrentEmptyCaptureSource: CaptureSourceAdapter, @unchecked Sendable {
    private let lock = NSLock()
    private var started = false

    func start(configuration: CaptureConfiguration) throws {
        lock.lock()
        started = true
        lock.unlock()
    }

    func pendingFrames() throws -> [CaptureFrame] {
        []
    }

    func status() -> [CaptureLaneStatus] {
        lock.lock()
        let isStarted = started
        lock.unlock()
        return CaptureLane.allCases.map {
            CaptureLaneStatus(
                lane: $0,
                sequence: 0,
                deviceEpoch: 0,
                state: isStarted ? "capturing" : "stopped"
            )
        }
    }

    func stop(deadline: Date) throws {
        lock.lock()
        started = false
        lock.unlock()
    }
}

private final class NoOpCaptureTransport: CaptureTransportAdapter, @unchecked Sendable {
    func publish(frame: CaptureFrame, configuration: CaptureConfiguration) throws {}
}

/// A transport whose answer is chosen per attempt, so a test can stage an outage, backpressure, an
/// unauthorized answer, or an answer that never came back. `attempts` records every request that
/// left the client — including the ones that then failed — and `accepted` only the answered ones,
/// which is the distinction an ambiguous result turns on.
private final class ProgrammableCaptureTransport: CaptureTransportAdapter, @unchecked Sendable {
    /// The lanes publish concurrently, so the record has to be synchronized; the answer is chosen
    /// inside the lock so an attempt is counted exactly once per request.
    private let lock = NSLock()
    private var programmedFailure: ((CaptureFrame, Int) -> Error?)?
    private var attemptedFrames: [CaptureFrame] = []
    private var acceptedFrames: [CaptureFrame] = []
    private var acceptedSessionIDs: [String] = []
    private var attemptsByIdentity: [String: Int] = [:]

    var failure: ((CaptureFrame, Int) -> Error?)? {
        get {
            lock.lock()
            defer { lock.unlock() }
            return programmedFailure
        }
        set {
            lock.lock()
            programmedFailure = newValue
            lock.unlock()
        }
    }

    var attempts: [CaptureFrame] {
        lock.lock()
        defer { lock.unlock() }
        return attemptedFrames
    }

    var accepted: [CaptureFrame] {
        lock.lock()
        defer { lock.unlock() }
        return acceptedFrames
    }

    var sessionIDs: [String] {
        lock.lock()
        defer { lock.unlock() }
        return acceptedSessionIDs
    }

    func publish(frame: CaptureFrame, configuration: CaptureConfiguration) throws {
        lock.lock()
        let identity = "\(frame.lane.rawValue):\(frame.sequence)"
        let attempt = attemptsByIdentity[identity, default: 0] + 1
        attemptsByIdentity[identity] = attempt
        attemptedFrames.append(frame)
        let answer = programmedFailure?(frame, attempt)
        if answer == nil {
            acceptedFrames.append(frame)
            acceptedSessionIDs.append(configuration.sessionID)
        }
        lock.unlock()
        if let answer {
            throw answer
        }
    }
}

private final class FakeScheduledPumpRunner: @unchecked Sendable {
    private let scheduler: FakeCaptureSchedulerAdapter

    init(scheduler: FakeCaptureSchedulerAdapter) {
        self.scheduler = scheduler
    }

    func run() {
        scheduler.runScheduledOperation()
    }
}

private final class CaptureControllerStopper: @unchecked Sendable {
    private let controller: CaptureController

    init(controller: CaptureController) {
        self.controller = controller
    }

    func stop(deadline: Date) -> CaptureStatus? {
        try? controller.stop(deadline: deadline)
    }
}

/// A transport that holds every lane's first request until every lane has one outstanding, and
/// records how wide the in-flight work ever got. A pump that drains the lanes one after another
/// cannot satisfy the rendezvous, so it is reported as a timeout rather than a slow pass.
private final class RendezvousCaptureTransport: CaptureTransportAdapter, @unchecked Sendable {
    private let condition = NSCondition()
    private let expectedLanes: Set<CaptureLane>
    private let rendezvousTimeout: TimeInterval
    private var inFlightByLane: [CaptureLane: Int] = [:]
    private var lanesArrived: Set<CaptureLane> = []
    private var widestConcurrency = 0
    private var widestConcurrencyByLane: [CaptureLane: Int] = [:]
    private var publishedFrames: [CaptureFrame] = []
    private var timedOut = false

    init(expectedLanes: Set<CaptureLane>, rendezvousTimeout: TimeInterval = 5) {
        self.expectedLanes = expectedLanes
        self.rendezvousTimeout = rendezvousTimeout
    }

    var maxConcurrentRequests: Int {
        condition.lock()
        defer { condition.unlock() }
        return widestConcurrency
    }

    func maxConcurrentRequests(lane: CaptureLane) -> Int {
        condition.lock()
        defer { condition.unlock() }
        return widestConcurrencyByLane[lane] ?? 0
    }

    func published(lane: CaptureLane) -> [CaptureFrame] {
        condition.lock()
        defer { condition.unlock() }
        return publishedFrames.filter { $0.lane == lane }
    }

    var rendezvousTimedOut: Bool {
        condition.lock()
        defer { condition.unlock() }
        return timedOut
    }

    func publish(frame: CaptureFrame, configuration: CaptureConfiguration) throws {
        condition.lock()
        let laneInFlight = inFlightByLane[frame.lane, default: 0] + 1
        inFlightByLane[frame.lane] = laneInFlight
        lanesArrived.insert(frame.lane)
        widestConcurrency = Swift.max(widestConcurrency, inFlightByLane.values.reduce(0, +))
        widestConcurrencyByLane[frame.lane] = Swift.max(
            widestConcurrencyByLane[frame.lane] ?? 0,
            laneInFlight
        )
        condition.broadcast()
        let deadline = Date(timeIntervalSinceNow: rendezvousTimeout)
        while lanesArrived != expectedLanes {
            guard condition.wait(until: deadline) else {
                timedOut = true
                break
            }
        }
        publishedFrames.append(frame)
        inFlightByLane[frame.lane] = laneInFlight - 1
        condition.unlock()
    }
}

/// A transport that parks every request until the test releases it, so a pass can be observed while
/// it is still in flight.
private final class GatedCaptureTransport: CaptureTransportAdapter, @unchecked Sendable {
    private let condition = NSCondition()
    private var attemptedFrames: [CaptureFrame] = []
    private var publishedFrames: [CaptureFrame] = []
    private var inFlight = 0
    private var released = false

    var attempts: [CaptureFrame] {
        condition.lock()
        defer { condition.unlock() }
        return attemptedFrames
    }

    var published: [CaptureFrame] {
        condition.lock()
        defer { condition.unlock() }
        return publishedFrames
    }

    func publish(frame: CaptureFrame, configuration: CaptureConfiguration) throws {
        condition.lock()
        attemptedFrames.append(frame)
        inFlight += 1
        condition.broadcast()
        while !released {
            condition.wait()
        }
        inFlight -= 1
        publishedFrames.append(frame)
        condition.unlock()
    }

    func waitUntilInFlight(_ count: Int, timeout: TimeInterval) -> Bool {
        condition.lock()
        defer { condition.unlock() }
        let deadline = Date(timeIntervalSinceNow: timeout)
        while inFlight < count {
            guard condition.wait(until: deadline) else {
                return false
            }
        }
        return true
    }

    func release() {
        condition.lock()
        released = true
        condition.broadcast()
        condition.unlock()
    }
}

/// A source that hands over live frames while it is running and one flushed tail after the stop,
/// readable from the pump thread and the stopping thread at the same time.
private final class ConcurrentTailCaptureSource: CaptureSourceAdapter, @unchecked Sendable {
    private let lock = NSLock()
    private let tail: [CaptureFrame]
    private let onTailHandover: () -> Void
    private var live: [CaptureFrame] = []
    private var stopped = false
    private var handedOverTail = false

    init(tail: [CaptureFrame], onTailHandover: @escaping () -> Void = {}) {
        self.tail = tail
        self.onTailHandover = onTailHandover
    }

    func enqueue(frames: [CaptureFrame]) {
        lock.lock()
        live.append(contentsOf: frames)
        lock.unlock()
    }

    func start(configuration: CaptureConfiguration) throws {}

    func pendingFrames() throws -> [CaptureFrame] {
        lock.lock()
        if stopped {
            guard !handedOverTail else {
                lock.unlock()
                return []
            }
            handedOverTail = true
            lock.unlock()
            onTailHandover()
            return tail
        }
        let frames = live
        live.removeAll()
        lock.unlock()
        return frames
    }

    func status() -> [CaptureLaneStatus] {
        lock.lock()
        let isStopped = stopped
        lock.unlock()
        return CaptureLane.allCases.map {
            CaptureLaneStatus(
                lane: $0,
                sequence: 0,
                deviceEpoch: 0,
                state: isStopped ? "stopped" : "capturing"
            )
        }
    }

    func stop(deadline: Date) throws {
        lock.lock()
        stopped = true
        lock.unlock()
    }
}

private final class IncrementingCaptureClock: CaptureClockAdapter, @unchecked Sendable {
    private let lock = NSLock()
    private var tick: UInt64 = 100

    func now() -> Date {
        Date(timeIntervalSince1970: 0)
    }

    func monotonicNanoseconds() -> UInt64 {
        lock.lock()
        defer { lock.unlock() }
        let current = tick
        tick += 1
        return current
    }
}

private final class ConcurrentCaptureScheduler: CaptureSchedulerAdapter, @unchecked Sendable {
    private let lock = NSLock()
    private var operation: (() -> Void)?

    func schedule(label: String, operation: @escaping () -> Void) -> CaptureCancellation {
        lock.lock()
        self.operation = operation
        lock.unlock()
        return FakeCaptureCancellation()
    }

    func runScheduledOperation() {
        lock.lock()
        let operation = operation
        lock.unlock()
        operation?()
    }
}

private final class ConcurrentCaptureHealth: CaptureHealthAdapter, @unchecked Sendable {
    private let lock = NSLock()
    private var emissions: [CaptureStatus] = []

    func emit(
        status: CaptureStatus,
        configuration: CaptureConfiguration,
        sentMonotonicNS: UInt64
    ) throws {
        lock.lock()
        emissions.append(status)
        lock.unlock()
    }

    func emissionCount() -> Int {
        lock.lock()
        defer { lock.unlock() }
        return emissions.count
    }
}

private final class CaptureStatusReader: @unchecked Sendable {
    private let controller: CaptureController

    init(controller: CaptureController) {
        self.controller = controller
    }

    func status() -> CaptureStatus {
        controller.status()
    }
}
