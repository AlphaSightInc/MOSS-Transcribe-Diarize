import Foundation
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
        XCTAssertEqual(health.emissions.first?.sentMonotonicNS, 100)
        XCTAssertEqual(scheduler.labels, ["moss.capture.health"])
        XCTAssertFalse(stopped.running)
        XCTAssertNil(controller.status().sessionID)
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

    private func packageRoot() -> URL {
        var url = URL(fileURLWithPath: #filePath)
        for _ in 0..<3 {
            url.deleteLastPathComponent()
        }
        return url
    }
}
