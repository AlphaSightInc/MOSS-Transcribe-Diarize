import CoreAudio
import AVFAudio
import XCTest
@testable import MOSSCaptureCore

final class NativeAudioBufferLayoutTests: XCTestCase {
    func testNilHALInputPreservesEmptyDiscontinuityContract() {
        let captured = NativeCapturedAudioBuffer.copyFromAudioBufferList(
            lane: .system,
            sampleRate: 48_000,
            deviceEpoch: 7,
            inputData: nil,
            inputTime: nil
        )

        XCTAssertEqual(captured.channelCount, 1)
        XCTAssertEqual(captured.frameCount, 0)
        XCTAssertEqual(captured.firstSampleMonotonicNS, 0)
        XCTAssertTrue(captured.discontinuity)
        XCTAssertEqual(captured.samples, [])
    }

    func testEmptyHALBufferListFailsClosedAsDiscontinuity() {
        let captured = withAudioBufferList([]) { inputData in
            NativeCapturedAudioBuffer.copyFromAudioBufferList(
                lane: .system,
                sampleRate: 48_000,
                deviceEpoch: 7,
                inputData: inputData,
                inputTime: nil
            )
        }

        assertEmptyDiscontinuity(captured)
    }

    func testHALListWithNilDataBufferFailsClosedAsDiscontinuity() {
        let captured = withAudioBufferList([
            BufferSpec(channels: 1, samples: [0.25, 0.5]),
            BufferSpec(channels: 1, samples: [0.75, 1], dataPresent: false),
        ]) { inputData in
            NativeCapturedAudioBuffer.copyFromAudioBufferList(
                lane: .system,
                sampleRate: 48_000,
                deviceEpoch: 7,
                inputData: inputData,
                inputTime: nil
            )
        }

        assertEmptyDiscontinuity(captured)
    }

    func testHALBufferWithZeroChannelsFailsClosedAsDiscontinuity() {
        let captured = withAudioBufferList([
            BufferSpec(channels: 0, samples: [0.25, 0.5]),
        ]) { inputData in
            NativeCapturedAudioBuffer.copyFromAudioBufferList(
                lane: .system,
                sampleRate: 48_000,
                deviceEpoch: 7,
                inputData: inputData,
                inputTime: nil
            )
        }

        assertEmptyDiscontinuity(captured)
    }

    func testHALBufferWithNonFloatAlignedByteSizeFailsClosedAsDiscontinuity() {
        let captured = withAudioBufferList([
            BufferSpec(channels: 1, samples: [0.25, 0.5], dataByteSize: 5),
        ]) { inputData in
            NativeCapturedAudioBuffer.copyFromAudioBufferList(
                lane: .system,
                sampleRate: 48_000,
                deviceEpoch: 7,
                inputData: inputData,
                inputTime: nil
            )
        }

        assertEmptyDiscontinuity(captured)
    }

    func testEmptyHALBufferFailsClosedAsDiscontinuity() {
        let captured = withAudioBufferList([
            BufferSpec(channels: 1, samples: []),
        ]) { inputData in
            NativeCapturedAudioBuffer.copyFromAudioBufferList(
                lane: .system,
                sampleRate: 48_000,
                deviceEpoch: 7,
                inputData: inputData,
                inputTime: nil
            )
        }

        assertEmptyDiscontinuity(captured)
    }

    func testHALBufferWithPartialTrailingFrameFailsClosedAsDiscontinuity() {
        let captured = withAudioBufferList([
            BufferSpec(channels: 2, samples: [0.25, 0.75, 0.5]),
        ]) { inputData in
            NativeCapturedAudioBuffer.copyFromAudioBufferList(
                lane: .system,
                sampleRate: 48_000,
                deviceEpoch: 7,
                inputData: inputData,
                inputTime: nil
            )
        }

        assertEmptyDiscontinuity(captured)
    }

    func testInterleavedStereoHALBufferDownmixesPerFrame() {
        let captured = withAudioBufferList([
            BufferSpec(
                channels: 2,
                samples: [0.125, 0.875, 0.25, 0.75, 0.5, 0.625]
            )
        ]) { inputData in
            NativeCapturedAudioBuffer.copyFromAudioBufferList(
                lane: .system,
                sampleRate: 48_000,
                deviceEpoch: 7,
                inputData: inputData,
                inputTime: nil
            )
        }

        XCTAssertEqual(captured.channelCount, 2)
        XCTAssertEqual(captured.frameCount, 3)
        XCTAssertEqual(captured.samples, [0.125, 0.25, 0.5, 0.875, 0.75, 0.625])
        XCTAssertEqual(NativeLaneWireStream.downmix(captured), [0.5, 0.5, 0.5625])
    }

    func testPlanarMonoHALBuffersPreserveExistingChannelLayout() {
        let captured = withAudioBufferList([
            BufferSpec(channels: 1, samples: [0.125, 0.25, 0.5]),
            BufferSpec(channels: 1, samples: [0.875, 0.75, 0.625]),
        ]) { inputData in
            NativeCapturedAudioBuffer.copyFromAudioBufferList(
                lane: .system,
                sampleRate: 48_000,
                deviceEpoch: 7,
                inputData: inputData,
                inputTime: nil
            )
        }

        XCTAssertEqual(captured.channelCount, 2)
        XCTAssertEqual(captured.frameCount, 3)
        XCTAssertEqual(captured.samples, [0.125, 0.25, 0.5, 0.875, 0.75, 0.625])
        XCTAssertEqual(NativeLaneWireStream.downmix(captured), [0.5, 0.5, 0.5625])
    }

    func testHybridHALBufferListNormalizesThreeChannels() {
        let captured = withAudioBufferList([
            BufferSpec(channels: 2, samples: [0, 0.75, 0.25, 0.5, 0.5, 0.25]),
            BufferSpec(channels: 1, samples: [0.75, 0.75, 0.75]),
        ]) { inputData in
            NativeCapturedAudioBuffer.copyFromAudioBufferList(
                lane: .system,
                sampleRate: 48_000,
                deviceEpoch: 7,
                inputData: inputData,
                inputTime: nil
            )
        }

        XCTAssertEqual(captured.channelCount, 3)
        XCTAssertEqual(captured.frameCount, 3)
        XCTAssertEqual(
            captured.samples,
            [0, 0.25, 0.5, 0.75, 0.5, 0.25, 0.75, 0.75, 0.75]
        )
        XCTAssertEqual(NativeLaneWireStream.downmix(captured), [0.5, 0.5, 0.5])
    }

    func testUnequalHALBufferFrameCountsFailClosedAsDiscontinuity() {
        let captured = withAudioBufferList([
            BufferSpec(
                channels: 2,
                samples: [0.125, 0.875, 0.25, 0.75, 0.5, 0.625]
            ),
            BufferSpec(channels: 1, samples: [0.5, 0.25]),
        ]) { inputData in
            NativeCapturedAudioBuffer.copyFromAudioBufferList(
                lane: .system,
                sampleRate: 48_000,
                deviceEpoch: 7,
                inputData: inputData,
                inputTime: nil
            )
        }

        assertEmptyDiscontinuity(captured)
    }

    func testMicrophoneInterleavedAndDeinterleavedBuffersCopyIdentically() throws {
        let channels: [[Float]] = [
            [0.125, 0.25, 0.5],
            [0.875, 0.75, 0.625],
        ]
        let interleaved = try makePCMBuffer(channels: channels, interleaved: true)
        let deinterleaved = try makePCMBuffer(channels: channels, interleaved: false)
        let time = AVAudioTime(hostTime: 17)

        let interleavedCopy = NativeCapturedAudioBuffer.copyFromAVAudioPCMBuffer(
            lane: .microphone,
            buffer: interleaved,
            time: time,
            deviceEpoch: 9
        )
        let deinterleavedCopy = NativeCapturedAudioBuffer.copyFromAVAudioPCMBuffer(
            lane: .microphone,
            buffer: deinterleaved,
            time: time,
            deviceEpoch: 9
        )

        XCTAssertEqual(interleavedCopy, deinterleavedCopy)
        XCTAssertEqual(interleavedCopy.samples, channels.flatMap { $0 })
        XCTAssertEqual(NativeLaneWireStream.downmix(interleavedCopy), [0.5, 0.5, 0.5625])
    }

    func testMicrophoneNonFloatBufferFailsClosedWithoutFabricatingSilence() throws {
        guard
            let format = AVAudioFormat(
                commonFormat: .pcmFormatInt16,
                sampleRate: 48_000,
                channels: 2,
                interleaved: false
            ),
            let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: 3),
            let channelData = buffer.int16ChannelData
        else {
            throw NativeAudioBufferLayoutTestError.allocationFailed
        }
        buffer.frameLength = 3
        channelData[0][0] = 1_000
        channelData[1][0] = -1_000

        let captured = NativeCapturedAudioBuffer.copyFromAVAudioPCMBuffer(
            lane: .microphone,
            buffer: buffer,
            time: AVAudioTime(hostTime: 17),
            deviceEpoch: 9
        )

        assertEmptyDiscontinuity(captured)
    }

    func testMicrophoneZeroFrameBufferFailsClosedAsDiscontinuity() throws {
        guard
            let format = AVAudioFormat(
                commonFormat: .pcmFormatFloat32,
                sampleRate: 48_000,
                channels: 2,
                interleaved: false
            ),
            let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: 1)
        else {
            throw NativeAudioBufferLayoutTestError.allocationFailed
        }
        buffer.frameLength = 0

        let captured = NativeCapturedAudioBuffer.copyFromAVAudioPCMBuffer(
            lane: .microphone,
            buffer: buffer,
            time: AVAudioTime(hostTime: 17),
            deviceEpoch: 9
        )

        assertEmptyDiscontinuity(captured)
    }

    func testSeededHALLayoutMatrixDownmixesOriginalPerFrameMeans() {
        var generator = SeededGenerator(seed: 0x4D4F_5353_4C41_594F)
        for frameCount in [1, 2, 7, 31] {
            for channelCount in 1...4 {
                let channels = (0..<channelCount).map { _ in
                    (0..<frameCount).map { _ in
                        Float(generator.next() % 2_049) / 1_024 - 1
                    }
                }
                let expectedDownmix = (0..<frameCount).map { frame in
                    channels.reduce(Float.zero) { $0 + $1[frame] } / Float(channelCount)
                }

                for split in channelPartitions(channelCount) {
                    let captured = withAudioBufferList(
                        bufferSpecs(channels: channels, partition: split)
                    ) { inputData in
                        NativeCapturedAudioBuffer.copyFromAudioBufferList(
                            lane: .system,
                            sampleRate: 48_000,
                            deviceEpoch: 7,
                            inputData: inputData,
                            inputTime: nil
                        )
                    }

                    XCTAssertEqual(captured.channelCount, channelCount, "split=\(split)")
                    XCTAssertEqual(captured.frameCount, frameCount, "split=\(split)")
                    XCTAssertEqual(captured.samples, channels.flatMap { $0 }, "split=\(split)")
                    XCTAssertEqual(
                        NativeLaneWireStream.downmix(captured),
                        expectedDownmix,
                        "split=\(split)"
                    )
                }
            }
        }
    }

    func testIdenticalInterleavedStereoMatchesMonoThroughLiveRateConversion() {
        let frameCount = 12_000
        let signal = (0..<frameCount).map { frame -> Float in
            let attack = Swift.min(Float(frame) / 480, 1)
            let release = Swift.min(Float(frameCount - frame) / 480, 1)
            let envelope = attack * release
            let time = Double(frame) / 48_000
            return envelope * (
                0.35 * Float(sin(2 * Double.pi * 173 * time))
                    + 0.15 * Float(sin(2 * Double.pi * 347 * time))
            )
        }
        let interleaved = signal.flatMap { [$0, $0] }
        let stereo = capturedSystemBuffer([
            BufferSpec(channels: 2, samples: interleaved)
        ])
        let mono = capturedSystemBuffer([
            BufferSpec(channels: 1, samples: signal)
        ])

        XCTAssertEqual(NativeLaneWireStream.downmix(stereo), signal)
        XCTAssertEqual(emittedFrames(from: stereo), emittedFrames(from: mono))
    }
}

private struct BufferSpec {
    var channels: Int
    var samples: [Float]
    var dataByteSize: Int? = nil
    var dataPresent = true
}

private func withAudioBufferList<Result>(
    _ specs: [BufferSpec],
    body: (UnsafePointer<AudioBufferList>) throws -> Result
) rethrows -> Result {
    let list = AudioBufferList.allocate(maximumBuffers: Swift.max(specs.count, 1))
    list.count = specs.count
    var storage: [(UnsafeMutablePointer<Float>, Int)] = []
    defer {
        for (pointer, count) in storage {
            pointer.deinitialize(count: count)
            pointer.deallocate()
        }
        list.unsafeMutablePointer.deallocate()
    }

    for (index, spec) in specs.enumerated() {
        let pointer = UnsafeMutablePointer<Float>.allocate(capacity: spec.samples.count)
        spec.samples.withUnsafeBufferPointer { source in
            if let baseAddress = source.baseAddress {
                pointer.initialize(from: baseAddress, count: source.count)
            }
        }
        storage.append((pointer, spec.samples.count))
        list[index] = AudioBuffer(
            mNumberChannels: UInt32(spec.channels),
            mDataByteSize: UInt32(
                spec.dataByteSize ?? spec.samples.count * MemoryLayout<Float>.stride
            ),
            mData: spec.dataPresent ? UnsafeMutableRawPointer(pointer) : nil
        )
    }
    return try body(list.unsafePointer)
}

private func assertEmptyDiscontinuity(
    _ captured: NativeCapturedAudioBuffer,
    file: StaticString = #filePath,
    line: UInt = #line
) {
    XCTAssertEqual(captured.channelCount, 1, file: file, line: line)
    XCTAssertEqual(captured.frameCount, 0, file: file, line: line)
    XCTAssertEqual(captured.firstSampleMonotonicNS, 0, file: file, line: line)
    XCTAssertTrue(captured.discontinuity, file: file, line: line)
    XCTAssertEqual(captured.samples, [], file: file, line: line)
}

private func makePCMBuffer(
    channels: [[Float]],
    interleaved: Bool
) throws -> AVAudioPCMBuffer {
    let frameCount = channels.first?.count ?? 0
    guard channels.allSatisfy({ $0.count == frameCount }) else {
        throw NativeAudioBufferLayoutTestError.nonRectangularFixture
    }
    guard
        let format = AVAudioFormat(
            commonFormat: .pcmFormatFloat32,
            sampleRate: 48_000,
            channels: AVAudioChannelCount(channels.count),
            interleaved: interleaved
        ),
        let buffer = AVAudioPCMBuffer(
            pcmFormat: format,
            frameCapacity: AVAudioFrameCount(frameCount)
        ),
        let channelData = buffer.floatChannelData
    else {
        throw NativeAudioBufferLayoutTestError.allocationFailed
    }
    buffer.frameLength = AVAudioFrameCount(frameCount)
    for channel in channels.indices {
        for frame in 0..<frameCount {
            channelData[channel][frame * buffer.stride] = channels[channel][frame]
        }
    }
    return buffer
}

private func capturedSystemBuffer(_ specs: [BufferSpec]) -> NativeCapturedAudioBuffer {
    var timestamp = AudioTimeStamp()
    timestamp.mHostTime = 1_000_000_000
    timestamp.mFlags = .hostTimeValid
    return withAudioBufferList(specs) { inputData in
        withUnsafePointer(to: &timestamp) { inputTime in
            NativeCapturedAudioBuffer.copyFromAudioBufferList(
                lane: .system,
                sampleRate: 48_000,
                deviceEpoch: 7,
                inputData: inputData,
                inputTime: inputTime
            )
        }
    }
}

private func emittedFrames(from buffer: NativeCapturedAudioBuffer) -> [CaptureFrame] {
    let emitter = NativeLaneFrameEmitter(
        wireFormat: .live,
        hostTime: MachTimebaseHostTimeConverter(numerator: 1, denominator: 1)
    )
    return emitter.frames(from: [buffer]) + emitter.flush()
}

private enum NativeAudioBufferLayoutTestError: Error {
    case allocationFailed
    case nonRectangularFixture
}

private func channelPartitions(_ channelCount: Int) -> [[Int]] {
    var partitions = [[channelCount], [Int](repeating: 1, count: channelCount)]
    if channelCount > 1 {
        partitions.append([1, channelCount - 1])
        partitions.append([channelCount - 1, 1])
    }
    var seen = Set<String>()
    return partitions.filter { seen.insert($0.map(String.init).joined(separator: ",")).inserted }
}

private func bufferSpecs(channels: [[Float]], partition: [Int]) -> [BufferSpec] {
    var channelOffset = 0
    return partition.map { channelCount in
        let selected = channels[channelOffset..<(channelOffset + channelCount)]
        channelOffset += channelCount
        let frameCount = selected.first?.count ?? 0
        let interleaved = (0..<frameCount).flatMap { frame in
            selected.map { $0[frame] }
        }
        return BufferSpec(channels: channelCount, samples: interleaved)
    }
}

private struct SeededGenerator {
    private var state: UInt64

    init(seed: UInt64) {
        state = seed
    }

    mutating func next() -> UInt64 {
        state = state &* 6_364_136_223_846_793_005 &+ 1_442_695_040_888_963_407
        return state
    }
}
