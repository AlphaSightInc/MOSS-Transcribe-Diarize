import Foundation
import XCTest
@testable import MOSSCaptureCore

final class CaptureSignalLevelTests: XCTestCase {
    func testTrackerReportsExactWirePCMLevelsAndSessionState() throws {
        let tracker = CaptureSignalLevelTracker()

        tracker.observe(frame(samples: Array(repeating: 0, count: 8_000), sequence: 0))
        tracker.observe(
            frame(samples: Array(repeating: amplitude(dbfs: -12), count: 8_000), sequence: 1)
        )
        tracker.observe(
            CaptureFrame(
                lane: .microphone,
                sequence: 2,
                sampleRate: 16_000,
                sampleCount: 3,
                captureTimestampNS: 0,
                deviceEpoch: 1,
                silent: false,
                discontinuity: false,
                pcm16: Data([1, 0, 2, 0, 3])
            )
        )

        let level = try XCTUnwrap(tracker.snapshot()[.microphone])
        XCTAssertEqual(level.analyzedFrames, 2)
        XCTAssertEqual(level.analyzedSamples, 16_000)
        XCTAssertEqual(level.silentFrames, 1)
        XCTAssertEqual(level.malformedFrames, 1)
        XCTAssertEqual(try XCTUnwrap(level.lastFrameRMSDBFS), -12, accuracy: 0.001)
        XCTAssertEqual(try XCTUnwrap(level.maxFrameRMSDBFS), -12, accuracy: 0.001)
        XCTAssertEqual(try XCTUnwrap(level.sessionPeakDBFS), -12, accuracy: 0.001)
    }

    func testTrackerKeepsLaneStateSeparateAndResetDropsThePreviousSession() throws {
        let tracker = CaptureSignalLevelTracker()
        tracker.observe(frame(lane: .system, samples: Array(repeating: Int16.max, count: 8_000)))
        tracker.observe(frame(lane: .microphone, samples: Array(repeating: 0, count: 8_000)))

        let before = tracker.snapshot()
        XCTAssertEqual(try XCTUnwrap(before[.system]?.maxFrameRMSDBFS), 0, accuracy: 0.001)
        XCTAssertNil(before[.microphone]?.maxFrameRMSDBFS)
        XCTAssertEqual(before[.microphone]?.silentFrames, 1)

        tracker.reset()
        XCTAssertEqual(tracker.snapshot(), [:])
    }

    func testControlChannelLaneProjectsAggregateLevelsWithoutAudio() throws {
        let signal = CaptureLaneSignalLevel(
            analyzedFrames: 4,
            analyzedSamples: 32_000,
            silentFrames: 1,
            malformedFrames: 0,
            lastFrameRMSDBFS: -21.25,
            maxFrameRMSDBFS: -12.5,
            sessionPeakDBFS: -3.0
        )
        let projected = ControlChannelLaneStatus(
            status: CaptureLaneStatus(
                lane: .microphone,
                sequence: 3,
                deviceEpoch: 7,
                state: CaptureLaneStates.capturing,
                signalLevel: signal
            )
        )

        XCTAssertEqual(projected.signalLevel, signal)
        let json = try JSONSerialization.jsonObject(with: JSONEncoder().encode(projected))
            as? [String: Any]
        XCTAssertEqual(json?["lane"] as? String, "microphone")
        XCTAssertNil(json?["pcm16"])
        XCTAssertNil(json?["samples"])
        XCTAssertEqual(
            (json?["signalLevel"] as? [String: Any])?["analyzedFrames"] as? Int,
            4
        )
    }

    private func frame(
        lane: CaptureLane = .microphone,
        samples: [Int16],
        sequence: UInt64 = 0
    ) -> CaptureFrame {
        var data = Data(capacity: samples.count * MemoryLayout<Int16>.size)
        for sample in samples {
            var encoded = sample.littleEndian
            withUnsafeBytes(of: &encoded) { data.append(contentsOf: $0) }
        }
        return CaptureFrame(
            lane: lane,
            sequence: sequence,
            sampleRate: 16_000,
            sampleCount: samples.count,
            captureTimestampNS: 0,
            deviceEpoch: 1,
            silent: samples.allSatisfy { $0 == 0 },
            discontinuity: false,
            pcm16: data
        )
    }

    private func amplitude(dbfs: Double) -> Int16 {
        Int16((pow(10.0, dbfs / 20.0) * 32_768.0).rounded())
    }
}
