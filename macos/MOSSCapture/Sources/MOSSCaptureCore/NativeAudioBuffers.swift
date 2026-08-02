import Foundation

/// Per-lane raw callback headroom paired with the capture pump's bounded transport turn.
public enum NativeCaptureQueueContract {
    public static let capacityPerLane = 1_024
}

public struct NativeCapturedAudioBuffer: Equatable {
    public var lane: CaptureLane
    public var sampleRate: Int
    public var channelCount: Int
    public var frameCount: Int
    public var firstSampleMonotonicNS: UInt64
    public var deviceEpoch: UInt64
    public var discontinuity: Bool
    /// ALWAYS exact rectangular channel-major: channel `c` occupies
    /// `[c * frameCount, (c + 1) * frameCount)`.
    public var samples: [Float]

    /// Production constructors emit exact rectangular channel-major `samples`. Caller-built values
    /// may still be malformed; downstream downmix retains defensive bounds behavior for them.
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
    private var bufferedBuffersByLane: [CaptureLane: Int] = [:]
    private var droppedBuffersByLane: [CaptureLane: UInt64] = [:]
    public private(set) var droppedBuffers: UInt64 = 0

    public init(capacity: Int) {
        precondition(capacity > 0)
        self.capacity = capacity
    }

    public func enqueueFromRealtimeCallback(_ buffer: NativeCapturedAudioBuffer) {
        lock.lock()
        if bufferedBuffersByLane[buffer.lane, default: 0] == capacity {
            droppedBuffers += 1
            droppedBuffersByLane[buffer.lane, default: 0] += 1
            lock.unlock()
            return
        }
        buffers.append(buffer)
        bufferedBuffersByLane[buffer.lane, default: 0] += 1
        lock.unlock()
    }

    public func drain() -> [NativeCapturedAudioBuffer] {
        lock.lock()
        let drained = buffers
        buffers.removeAll(keepingCapacity: true)
        bufferedBuffersByLane.removeAll(keepingCapacity: true)
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

/// Turns the native buffers a lane produced into wire frames.
///
/// Everything that is not safe on a Core Audio callback thread happens here: the channel mixdown,
/// the anti-aliased conversion to the canonical rate, the Mach-tick to nanosecond conversion, and
/// the coalescing into exactly-sized frames. The callbacks themselves only copy and enqueue.
///
/// The sequence numbers stamped here are a source-local production count. `CaptureFrameOutbox`
/// owns the identity a frame keeps on the wire.
public final class NativeLaneFrameEmitter {
    private let wireFormat: NativeLaneWireFormat
    private let hostTime: MachHostTimeConverting
    private let makeResampler: (NativeLaneWireFormat) -> NativeLaneResampling
    private var streams: [CaptureLane: NativeLaneWireStream] = [:]
    private var nextSequence: [CaptureLane: UInt64] = [:]
    private var reportedRejections: [CaptureLane: UInt64] = [:]

    public convenience init() {
        self.init(wireFormat: .live)
    }

    init(
        wireFormat: NativeLaneWireFormat = .live,
        hostTime: MachHostTimeConverting = HostTimeNanosecondConverter(),
        makeResampler: @escaping (NativeLaneWireFormat) -> NativeLaneResampling = { format in
            AVAudioConverterLaneResampler(outputSampleRate: format.sampleRate)
        }
    ) {
        self.wireFormat = wireFormat
        self.hostTime = hostTime
        self.makeResampler = makeResampler
    }

    public func frames(from buffers: [NativeCapturedAudioBuffer]) -> [CaptureFrame] {
        buffers.flatMap { buffer in
            stream(for: buffer.lane).append(buffer).map(frame(from:))
        }
    }

    /// Ends every lane's stream and releases its trailing partial frame. Capture is over by the
    /// time this runs, so audio shorter than a whole frame either leaves now or is lost.
    public func flush() -> [CaptureFrame] {
        let tail = CaptureLane.allCases.flatMap { lane in
            streams[lane].map { $0.flush().map(frame(from:)) } ?? []
        }
        // AVAudioConverter cannot accept a second stream after end-of-stream. A later meeting must
        // therefore construct fresh lane streams instead of reusing the converters just flushed.
        streams.removeAll(keepingCapacity: true)
        nextSequence.removeAll(keepingCapacity: true)
        reportedRejections.removeAll(keepingCapacity: true)
        return tail
    }

    /// Buffers dropped because their capture instant was unusable, counted per lane since the last
    /// call. The audio is gone, so the loss is reported rather than papered over with a made-up
    /// timestamp; the lane's next frame also carries `discontinuity`.
    func drainRejectedBufferCounts() -> [CaptureLane: UInt64] {
        var counts: [CaptureLane: UInt64] = [:]
        for (lane, stream) in streams {
            let total = stream.rejectedBuffers
            let reported = reportedRejections[lane, default: 0]
            if total > reported {
                counts[lane] = total - reported
                reportedRejections[lane] = total
            }
        }
        return counts
    }

    private func stream(for lane: CaptureLane) -> NativeLaneWireStream {
        if let stream = streams[lane] {
            return stream
        }
        let stream = NativeLaneWireStream(
            lane: lane,
            wireFormat: wireFormat,
            hostTime: hostTime,
            resampler: makeResampler(wireFormat)
        )
        streams[lane] = stream
        return stream
    }

    private func frame(from chunk: NativeLaneWireChunk) -> CaptureFrame {
        let sequence = nextSequence[chunk.lane, default: 0]
        nextSequence[chunk.lane] = sequence + 1
        return CaptureFrame(
            lane: chunk.lane,
            sequence: sequence,
            sampleRate: wireFormat.sampleRate,
            sampleCount: chunk.samples.count,
            captureTimestampNS: chunk.captureTimestampNS,
            deviceEpoch: chunk.deviceEpoch,
            silent: Self.isSilent(chunk.samples),
            discontinuity: chunk.discontinuity,
            pcm16: Self.pcm16(from: chunk.samples)
        )
    }

    private static func pcm16(from samples: [Float]) -> Data {
        var pcm = Data()
        pcm.reserveCapacity(samples.count * MemoryLayout<Int16>.size)
        for sample in samples {
            let clamped = Swift.max(-1.0, Swift.min(1.0, sample))
            var encoded = Int16((clamped * Float(Int16.max)).rounded()).littleEndian
            withUnsafeBytes(of: &encoded) { bytes in
                pcm.append(contentsOf: bytes)
            }
        }
        return pcm
    }

    private static func isSilent(_ samples: [Float]) -> Bool {
        samples.allSatisfy { abs($0) < 1.0 / 32_768.0 }
    }
}
