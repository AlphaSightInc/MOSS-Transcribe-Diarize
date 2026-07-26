import AVFAudio
import Foundation

public struct MicrophoneCaptureSourceVector: Equatable, Sendable {
    public var engine: String
    public var input: String
    public var tap: String
    public var realtimeCallbackWork: [String]
}

public final class MicrophoneCapture {
    public static let sourceVector = MicrophoneCaptureSourceVector(
        engine: "AVAudioEngine",
        input: "inputNode",
        tap: "installTap",
        realtimeCallbackWork: ["copy native buffer", "enqueue monotonic first-sample time"]
    )

    private let engine: AVAudioEngine
    private let deviceEpoch: UInt64

    public init(engine: AVAudioEngine = AVAudioEngine(), deviceEpoch: UInt64 = 0) {
        self.engine = engine
        self.deviceEpoch = deviceEpoch
    }

    public func start(queue: RealTimeNativeAudioBufferQueue) throws {
        let inputNode = engine.inputNode
        let format = inputNode.inputFormat(forBus: 0)
        let deviceEpoch = self.deviceEpoch
        inputNode.installTap(onBus: 0, bufferSize: 1_024, format: format) { buffer, time in
            queue.enqueueFromRealtimeCallback(
                NativeCapturedAudioBuffer.copyFromAVAudioPCMBuffer(
                    lane: .microphone,
                    buffer: buffer,
                    time: time,
                    deviceEpoch: deviceEpoch
                )
            )
        }
        try engine.start()
    }

    public func stop() {
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
    }
}

extension NativeCapturedAudioBuffer {
    static func copyFromAVAudioPCMBuffer(
        lane: CaptureLane,
        buffer: AVAudioPCMBuffer,
        time: AVAudioTime,
        deviceEpoch: UInt64
    ) -> NativeCapturedAudioBuffer {
        let frameCount = Int(buffer.frameLength)
        let channelCount = Int(buffer.format.channelCount)
        var samples: [Float] = []
        if let channelData = buffer.floatChannelData {
            for channel in 0..<channelCount {
                samples.append(
                    contentsOf: UnsafeBufferPointer(
                        start: channelData[channel],
                        count: frameCount
                    )
                )
            }
        }
        return NativeCapturedAudioBuffer(
            lane: lane,
            sampleRate: Int(buffer.format.sampleRate),
            channelCount: Swift.max(channelCount, 1),
            frameCount: frameCount,
            firstSampleMonotonicNS: time.hostTime,
            deviceEpoch: deviceEpoch,
            discontinuity: false,
            samples: samples
        )
    }
}
