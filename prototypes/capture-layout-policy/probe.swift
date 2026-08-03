import AVFoundation
import CoreAudio
import Foundation

private struct BufferSpec {
    var channels: Int
    var samples: [Float]
    var dataByteSize: Int? = nil
    var dataPresent = true
}

private enum CounterfactualPolicy: String {
    case truncate
    case zeroFill = "zero-fill"
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
        free(list.unsafeMutablePointer)
    }
    for (index, spec) in specs.enumerated() {
        let capacity = Swift.max(spec.samples.count, 1)
        let pointer = UnsafeMutablePointer<Float>.allocate(capacity: capacity)
        pointer.initialize(repeating: 0, count: capacity)
        for (sampleIndex, sample) in spec.samples.enumerated() {
            pointer[sampleIndex] = sample
        }
        storage.append((pointer, capacity))
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

private func productionCopy(_ input: UnsafePointer<AudioBufferList>) -> NativeCapturedAudioBuffer {
    NativeCapturedAudioBuffer.copyFromAudioBufferList(
        lane: .system,
        sampleRate: 48_000,
        deviceEpoch: 1,
        inputData: input,
        inputTime: nil
    )
}

private func counterfactualCopy(
    _ input: UnsafePointer<AudioBufferList>,
    policy: CounterfactualPolicy
) -> NativeCapturedAudioBuffer? {
    let buffers = UnsafeMutableAudioBufferListPointer(
        UnsafeMutablePointer(mutating: input)
    )
    var normalized: [(AudioBuffer, Int, Int)] = []
    for buffer in buffers {
        guard let data = buffer.mData else { continue }
        let channels = Swift.max(1, Int(buffer.mNumberChannels))
        let samples = Int(buffer.mDataByteSize) / MemoryLayout<Float>.stride
        let frames = samples / channels
        guard frames > 0 else { continue }
        normalized.append((buffer, channels, frames))
        _ = data
    }
    guard !normalized.isEmpty else { return nil }
    let frameCount: Int
    switch policy {
    case .truncate:
        frameCount = normalized.map(\.2).min()!
    case .zeroFill:
        frameCount = normalized.map(\.2).max()!
    }
    let channelCount = normalized.reduce(0) { $0 + $1.1 }
    var samples = [Float](repeating: 0, count: channelCount * frameCount)
    var channelOffset = 0
    for (buffer, channels, frames) in normalized {
        let source = buffer.mData!.assumingMemoryBound(to: Float.self)
        for frame in 0..<Swift.min(frames, frameCount) {
            for channel in 0..<channels {
                samples[(channelOffset + channel) * frameCount + frame] =
                    source[frame * channels + channel]
            }
        }
        channelOffset += channels
    }
    return NativeCapturedAudioBuffer(
        lane: .system,
        sampleRate: 48_000,
        channelCount: channelCount,
        frameCount: frameCount,
        firstSampleMonotonicNS: 0,
        deviceEpoch: 1,
        discontinuity: false,
        samples: samples
    )
}

private func format(_ samples: [Float]) -> String {
    "[" + samples.map { String(format: "%.3f", $0) }.joined(separator: ",") + "]"
}

private func require(_ condition: @autoclosure () -> Bool, _ message: String) {
    guard condition() else {
        FileHandle.standardError.write(Data("PROBE FAILURE: \(message)\n".utf8))
        exit(3)
    }
}

private func recordMalformed(
    name: String,
    specs: [BufferSpec]
) {
    withAudioBufferList(specs) { input in
        let captured = productionCopy(input)
        require(captured.discontinuity, "\(name) did not fail closed")
        require(captured.frameCount == 0 && captured.samples.isEmpty, "\(name) fabricated audio")
        print("case=\(name) production=empty-discontinuity frames=0 samples=[]")
    }
}

print("question=malformed HAL callback policy at production copy/downmix seam")

withAudioBufferList([
    BufferSpec(channels: 1, samples: [0.25, 0.5, 0.75]),
    BufferSpec(channels: 1, samples: [0.75, 0.5, 0.25]),
]) { input in
    let production = productionCopy(input)
    let productionMix = NativeLaneWireStream.downmix(production)
    require(!production.discontinuity, "valid rectangle was rejected")
    require(productionMix == [0.5, 0.5, 0.5], "valid downmix changed")
    for policy in [CounterfactualPolicy.truncate, .zeroFill] {
        let candidate = counterfactualCopy(input, policy: policy)!
        require(NativeLaneWireStream.downmix(candidate) == productionMix, "valid \(policy.rawValue) differs")
    }
    print("case=valid-equal production=accepted downmix=\(format(productionMix)) all_policies_equal=true")
}

withAudioBufferList([
    BufferSpec(channels: 1, samples: [1, 1, 1]),
    BufferSpec(channels: 1, samples: [1, 1]),
]) { input in
    let production = productionCopy(input)
    let truncated = counterfactualCopy(input, policy: .truncate)!
    let padded = counterfactualCopy(input, policy: .zeroFill)!
    let truncateMix = NativeLaneWireStream.downmix(truncated)
    let paddedMix = NativeLaneWireStream.downmix(padded)
    require(production.discontinuity && production.samples.isEmpty, "unequal frames were accepted")
    require(truncateMix == [1, 1], "truncate result unexpected")
    require(paddedMix == [1, 1, 0.5], "zero-fill corruption not reproduced")
    print(
        "case=unequal-frames production=empty-discontinuity " +
        "truncate_downmix=\(format(truncateMix)) truncate_lost_valid_frames=1 " +
        "zero_fill_downmix=\(format(paddedMix)) zero_fill_tail_error=-0.500"
    )
}

recordMalformed(
    name: "partial-interleaved-frame",
    specs: [BufferSpec(channels: 2, samples: [0.25, 0.75, 0.5])]
)
recordMalformed(
    name: "nil-data-member",
    specs: [
        BufferSpec(channels: 1, samples: [0.5]),
        BufferSpec(channels: 1, samples: [0.5], dataPresent: false),
    ]
)
recordMalformed(
    name: "zero-channel-member",
    specs: [BufferSpec(channels: 0, samples: [0.5])]
)
recordMalformed(
    name: "non-float-aligned-bytes",
    specs: [BufferSpec(channels: 1, samples: [0.5, 0.5], dataByteSize: 5)]
)

if let format = AVAudioFormat(
    commonFormat: .pcmFormatInt16,
    sampleRate: 48_000,
    channels: 2,
    interleaved: false
), let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: 3) {
    buffer.frameLength = 3
    let captured = NativeCapturedAudioBuffer.copyFromAVAudioPCMBuffer(
        lane: .microphone,
        buffer: buffer,
        time: AVAudioTime(hostTime: 1),
        deviceEpoch: 1
    )
    require(captured.discontinuity && captured.samples.isEmpty, "non-Float mic fabricated silence")
    print("case=non-float-microphone production=empty-discontinuity frames=0 samples=[]")
} else {
    require(false, "could not allocate real non-Float AVAudioPCMBuffer")
}

print("verdict=FAIL_CLOSED_WINS reason=truncate_drops_valid_frames;zero-fill-invents-0.500-tail;malformed-layout-has-no-truthful-rectangle")
