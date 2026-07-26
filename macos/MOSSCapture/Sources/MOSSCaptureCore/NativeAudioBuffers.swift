import Foundation

public struct NativeCapturedAudioBuffer: Equatable {
    public var lane: CaptureLane
    public var sampleRate: Int
    public var channelCount: Int
    public var frameCount: Int
    public var firstSampleMonotonicNS: UInt64
    public var deviceEpoch: UInt64
    public var discontinuity: Bool
    public var samples: [Float]

    public init(
        lane: CaptureLane,
        sampleRate: Int,
        channelCount: Int,
        frameCount: Int,
        firstSampleMonotonicNS: UInt64,
        deviceEpoch: UInt64,
        discontinuity: Bool,
        samples: [Float]
    ) {
        self.lane = lane
        self.sampleRate = sampleRate
        self.channelCount = channelCount
        self.frameCount = frameCount
        self.firstSampleMonotonicNS = firstSampleMonotonicNS
        self.deviceEpoch = deviceEpoch
        self.discontinuity = discontinuity
        self.samples = samples
    }
}

public final class RealTimeNativeAudioBufferQueue {
    private let capacity: Int
    private let lock = NSLock()
    private var buffers: [NativeCapturedAudioBuffer] = []
    private var droppedBuffersByLane: [CaptureLane: UInt64] = [:]
    public private(set) var droppedBuffers: UInt64 = 0

    public init(capacity: Int) {
        precondition(capacity > 0)
        self.capacity = capacity
    }

    public func enqueueFromRealtimeCallback(_ buffer: NativeCapturedAudioBuffer) {
        lock.lock()
        if buffers.count == capacity {
            let dropped = buffers.removeFirst()
            droppedBuffers += 1
            droppedBuffersByLane[dropped.lane, default: 0] += 1
        }
        buffers.append(buffer)
        lock.unlock()
    }

    public func drain() -> [NativeCapturedAudioBuffer] {
        lock.lock()
        let drained = buffers
        buffers.removeAll(keepingCapacity: true)
        lock.unlock()
        return drained
    }

    public func droppedBuffersByLaneSnapshot() -> [CaptureLane: UInt64] {
        lock.lock()
        let snapshot = droppedBuffersByLane
        lock.unlock()
        return snapshot
    }
}

public final class NativeLaneFrameEmitter {
    private var nextSequence: [CaptureLane: UInt64] = [:]

    public init() {}

    public func frames(from buffers: [NativeCapturedAudioBuffer]) -> [CaptureFrame] {
        buffers.map { buffer in
            let sequence = nextSequence[buffer.lane, default: 0]
            nextSequence[buffer.lane] = sequence + 1
            let pcm16 = Self.monoPCM16(from: buffer)
            return CaptureFrame(
                lane: buffer.lane,
                sequence: sequence,
                sampleRate: buffer.sampleRate,
                sampleCount: buffer.frameCount,
                captureTimestampNS: buffer.firstSampleMonotonicNS,
                deviceEpoch: buffer.deviceEpoch,
                silent: Self.isSilent(buffer),
                discontinuity: buffer.discontinuity,
                pcm16: pcm16
            )
        }
    }

    private static func monoPCM16(from buffer: NativeCapturedAudioBuffer) -> Data {
        var pcm = Data()
        pcm.reserveCapacity(buffer.frameCount * MemoryLayout<Int16>.size)
        for frameIndex in 0..<buffer.frameCount {
            let mono = monoSample(in: buffer, frameIndex: frameIndex)
            let clamped = Swift.max(-1.0, Swift.min(1.0, mono))
            var sample = Int16((clamped * Float(Int16.max)).rounded()).littleEndian
            withUnsafeBytes(of: &sample) { bytes in
                pcm.append(contentsOf: bytes)
            }
        }
        return pcm
    }

    private static func monoSample(in buffer: NativeCapturedAudioBuffer, frameIndex: Int) -> Float {
        guard buffer.channelCount > 0, buffer.frameCount > 0 else {
            return 0
        }
        var total: Float = 0
        for channel in 0..<buffer.channelCount {
            let index = channel * buffer.frameCount + frameIndex
            if index < buffer.samples.count {
                total += buffer.samples[index]
            }
        }
        return total / Float(buffer.channelCount)
    }

    private static func isSilent(_ buffer: NativeCapturedAudioBuffer) -> Bool {
        buffer.samples.allSatisfy { abs($0) < 1.0 / 32_768.0 }
    }
}
