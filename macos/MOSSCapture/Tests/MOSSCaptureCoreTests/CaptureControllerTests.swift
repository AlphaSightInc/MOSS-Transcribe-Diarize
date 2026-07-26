import CryptoKit
import CoreAudio
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
        XCTAssertEqual(transport.publishedFrames.map(\.lane), [.system, .microphone])
        XCTAssertEqual(transport.publishedFrames.map(\.sequence), [0, 0])
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

        XCTAssertEqual(
            transport.publishedFrames.map(\.lane),
            [CaptureLane.system, CaptureLane.microphone, CaptureLane.system, CaptureLane.microphone]
        )
        XCTAssertEqual(transport.publishedFrames.map(\.sequence), [0, 0, 1, 1])
        XCTAssertEqual(transport.publishedFrames.map(\.captureTimestampNS), [10, 20, 30, 40])
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
            queue: RealTimeNativeAudioBufferQueue(capacity: 8)
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
            queue: RealTimeNativeAudioBufferQueue(capacity: 8)
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
            queue: RealTimeNativeAudioBufferQueue(capacity: 8)
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
            queue: RealTimeNativeAudioBufferQueue(capacity: 2)
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
        XCTAssertEqual(systemStatus.state, "failed")
        XCTAssertEqual(systemStatus.failureCode, "macos_buffer_overrun")
        XCTAssertEqual(systemStatus.droppedFrames, 1)
        XCTAssertEqual(systemStatus.discontinuities, 1)
        XCTAssertEqual(microphoneStatus.state, "capturing")
        XCTAssertNil(microphoneStatus.failureCode)
        XCTAssertEqual(microphoneStatus.droppedFrames, 0)
        XCTAssertEqual(microphoneStatus.discontinuities, 0)
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
            queue: RealTimeNativeAudioBufferQueue(capacity: 8)
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
            queue: RealTimeNativeAudioBufferQueue(capacity: 8)
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
        driver.emit(.isAlive(false))

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

    func testMicrophoneCaptureUndeterminedPermissionIsPendingNotDenied() throws {
        let driver = RecordingMicrophoneCaptureDriver(permission: .undetermined, currentDeviceID: 64)
        let microphone = MicrophoneCapture(driver: driver)
        let health = NativeLaneHealth()
        let generation = health.beginGeneration()
        microphone.attachHealthSink(health, lane: .microphone, generation: generation)

        try microphone.start(queue: RealTimeNativeAudioBufferQueue(capacity: 4))
        health.enqueue(.admitted, lane: .microphone, generation: generation)

        let status = try XCTUnwrap(
            health.statuses(running: true).first { $0.lane == .microphone }
        )
        XCTAssertEqual(status.state, "capturing")
        XCTAssertNil(status.failureCode)
        XCTAssertNil(health.failure(for: .microphone))
        microphone.stop()
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
        let microphone = MicrophoneCapture(driver: driver)
        let health = NativeLaneHealth()
        let generation = health.beginGeneration()
        microphone.attachHealthSink(health, lane: .microphone, generation: generation)

        try microphone.start(queue: RealTimeNativeAudioBufferQueue(capacity: 4))
        health.enqueue(.admitted, lane: .microphone, generation: generation)
        driver.currentDeviceID = 77
        driver.emit(.configurationChanged)

        let status = try XCTUnwrap(
            health.statuses(running: true).first { $0.lane == .microphone }
        )
        XCTAssertEqual(status.state, "capturing")
        XCTAssertEqual(status.deviceEpoch, 77)
        XCTAssertNil(status.failureCode)
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
        driver.emit(.engineRunning(false))

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

        let emitter = NativeLaneFrameEmitter()
        let frames = emitter.frames(from: queue.drain())

        XCTAssertEqual(queue.droppedBuffers, 1)
        XCTAssertEqual(frames.map(\.lane), [.microphone, .system])
        XCTAssertEqual(frames.map(\.sequence), [0, 0])
        XCTAssertEqual(frames.map(\.deviceEpoch), [7, 1])
        XCTAssertEqual(frames.map(\.captureTimestampNS), [11, 12])
        XCTAssertEqual(frames.map(\.silent), [true, false])
        XCTAssertEqual(frames.map(\.discontinuity), [false, true])
        XCTAssertEqual(frames.map(\.sampleCount), [1, 1])
        XCTAssertEqual(frames.map(\.pcm16.count), [2, 2])

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
        XCTAssertEqual(nextSystem.first?.sequence, 1)
    }

    func testNativeLaneHealthStableCodeVocabularyIsClosed() throws {
        XCTAssertEqual(
            NativeLaneFailureCode.allCases.map(\.rawValue),
            [
                "macos_permission_denied",
                "macos_device_unavailable",
                "macos_io_stopped_abnormally",
                "macos_callback_stalled",
                "macos_buffer_overrun",
                "macos_unexpected_capture_error",
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
        let currentGeneration = health.beginGeneration()
        health.enqueue(.admitted, lane: .system, generation: currentGeneration)

        let system = try XCTUnwrap(
            health.statuses(running: true).first { $0.lane == .system }
        )
        XCTAssertEqual(system.state, "capturing")
        XCTAssertNil(system.failureCode)
        XCTAssertNil(health.failure(for: .system))
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
            (.bufferOverrun(droppedBuffers: 1), .bufferOverrun),
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
        XCTAssertEqual(exchange.serverURL, serverURL)
        XCTAssertEqual(exchange.pairingPayload, payload)
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

    private func packageRoot() -> URL {
        var url = URL(fileURLWithPath: #filePath)
        for _ in 0..<3 {
            url.deleteLastPathComponent()
        }
        return url
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
        let fileDescriptor = socket(AF_UNIX, SOCK_STREAM, 0)
        XCTAssertGreaterThanOrEqual(fileDescriptor, 0)
        defer { close(fileDescriptor) }

        try connectRawSocket(fileDescriptor, socketPath: socketPath)
        try writeRawPayload(payload, to: fileDescriptor)
        if halfCloseWrite {
            shutdown(fileDescriptor, SHUT_WR)
        }
        let body = try readRawFrame(from: fileDescriptor)
        return try JSONDecoder().decode(ControlChannelResponse.self, from: body)
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

    private func jsonBody(_ request: URLRequest) throws -> [String: Any] {
        let data = try XCTUnwrap(request.httpBody)
        let object = try JSONSerialization.jsonObject(with: data)
        return try XCTUnwrap(object as? [String: Any])
    }
}

private final class RecordingNativeCaptureComponent: NativeAudioCaptureComponent {
    private let buffersOnStart: [NativeCapturedAudioBuffer]
    private let startError: Error?
    private(set) var startCount = 0
    private(set) var stopCount = 0

    init(
        buffersOnStart: [NativeCapturedAudioBuffer] = [],
        startError: Error? = nil
    ) {
        self.buffersOnStart = buffersOnStart
        self.startError = startError
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
    }
}

private final class RecordingSystemAudioTapDriver: SystemAudioTapDriver {
    private let startError: Error?
    private(set) var events: [String] = []
    private var lifecycleHandler: ((SystemAudioTapDeviceObservation) -> Void)?

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
}

private final class RecordingMicrophoneCaptureDriver: MicrophoneCaptureDriver {
    private(set) var events: [String] = []
    private var permission: NativeLanePermissionFact
    var currentDeviceID: AudioDeviceID
    var startError: Error?
    private var observationHandler: (@Sendable (MicrophoneCaptureEngineObservation) -> Void)?

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

    func currentInputDeviceID() throws -> AudioDeviceID {
        events.append("kAudioOutputUnitProperty_CurrentDevice")
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
}

private final class RecordingCaptureHTTPClient: CaptureHTTPClient {
    private(set) var requests: [URLRequest] = []
    var response = CaptureHTTPResponse(statusCode: 200)

    func send(_ request: URLRequest) throws -> CaptureHTTPResponse {
        requests.append(request)
        return response
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

private final class RecordingPairingExchange: CapturePairingExchangeAdapter {
    private(set) var serverURL: URL?
    private(set) var pairingPayload: Data?

    func pair(serverURL: URL, pairingPayload: Data) throws -> CapturePairingResult {
        self.serverURL = serverURL
        self.pairingPayload = pairingPayload
        return CapturePairingResult(sessionID: "session-from-pairing", captureBearerToken: "capture-token")
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
