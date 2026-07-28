import AVFAudio
import CoreAudio
import Foundation

/// The shape live audio has on the wire, independent of whatever the devices produce.
///
/// Both lanes are converted to this one grid on the Mac, so the server mixer never resamples and
/// the request rate stops depending on Core Audio callback sizes.
struct NativeLaneWireFormat: Equatable, Sendable {
    var sampleRate: Int
    var frameSamples: Int

    /// Domain contract: 16 kHz mono, 8000 samples (0.5 s) per lane frame.
    static let live = NativeLaneWireFormat(sampleRate: 16_000, frameSamples: 8_000)

    var frameDurationNS: UInt64 {
        nanoseconds(forSamples: frameSamples)
    }

    /// The tolerance a capture instant may miss its predicted position by before the stream counts
    /// the seam as a break. One wire sample is far above the rounding of a tick-to-nanosecond
    /// conversion and far below any real dropout, which is at least one device callback long.
    var contiguityToleranceNS: UInt64 {
        Swift.max(nanoseconds(forSamples: 1), 1)
    }

    func nanoseconds(forSamples count: Int) -> UInt64 {
        Self.nanoseconds(forSamples: count, atSampleRate: sampleRate)
    }

    static func nanoseconds(forSamples count: Int, atSampleRate sampleRate: Int) -> UInt64 {
        guard count > 0, sampleRate > 0 else {
            return 0
        }
        return UInt64(count) * 1_000_000_000 / UInt64(sampleRate)
    }
}

/// Turns a Mach host-time reading into real nanoseconds.
///
/// `AVAudioTime.hostTime` and `AudioTimeStamp.mHostTime` are Mach ticks, not nanoseconds; on this
/// hardware family the timebase is far from 1:1, so publishing ticks as `capture_timestamp_ns`
/// collapses the server's timeline. A reading that cannot describe a capture instant returns `nil`
/// — the caller drops the audio rather than fabricating a time for it.
protocol MachHostTimeConverting: Sendable {
    func nanoseconds(forHostTicks ticks: UInt64) -> UInt64?
}

/// Production conversion: CoreAudio owns the timebase, so ask CoreAudio.
struct HostTimeNanosecondConverter: MachHostTimeConverting {
    func nanoseconds(forHostTicks ticks: UInt64) -> UInt64? {
        guard ticks != 0 else {
            return nil
        }
        return AudioConvertHostTimeToNanos(ticks)
    }
}

/// Conversion against an explicitly stated timebase, so the unit contract can be proven without
/// depending on the timebase of whichever Mac runs the check.
struct MachTimebaseHostTimeConverter: MachHostTimeConverting {
    var numerator: UInt64
    var denominator: UInt64

    func nanoseconds(forHostTicks ticks: UInt64) -> UInt64? {
        guard ticks != 0, denominator != 0 else {
            return nil
        }
        // Divide before multiplying so a long-running host's tick count survives the numerator, and
        // report a reading that still does not fit as unusable rather than wrapping it into a small
        // number that would pass for a valid capture instant.
        let (scaled, scaleOverflowed) = (ticks / denominator).multipliedReportingOverflow(by: numerator)
        guard !scaleOverflowed else {
            return nil
        }
        let fraction = (ticks % denominator) * numerator / denominator
        let (nanoseconds, sumOverflowed) = scaled.addingReportingOverflow(fraction)
        return sumOverflowed ? nil : nanoseconds
    }
}

enum NativeLaneResamplingError: Error, Equatable {
    case unsupportedFormat(inputSampleRate: Int, outputSampleRate: Int)
    case conversionFailed(String)
}

/// Converts one lane's mono audio to the wire sample rate, keeping filter state across chunks.
///
/// State has to live across calls: a sample-rate converter that is rebuilt per Core Audio callback
/// restarts its filter each time and prints the discontinuity into the audio.
protocol NativeLaneResampling: AnyObject {
    func resample(mono samples: [Float], inputSampleRate: Int) throws -> [Float]
    /// Emits whatever the converter still holds and ends the stream.
    func flush() throws -> [Float]
}

/// One chunk of input, handed to the converter exactly once.
///
/// `AVAudioConverter` pulls its input from a block it may call more than once per conversion; the
/// second call has to say "nothing more now" or the same audio is converted twice.
private final class PendingConverterInput: @unchecked Sendable {
    private var buffer: AVAudioPCMBuffer?

    init(buffer: AVAudioPCMBuffer) {
        self.buffer = buffer
    }

    func take() -> AVAudioPCMBuffer? {
        defer { buffer = nil }
        return buffer
    }
}

/// `AVAudioConverter` gives the anti-aliased sample-rate conversion the server's linear
/// interpolation never had; running it on the Mac is what makes the server's mixer grid 1:1.
final class AVAudioConverterLaneResampler: NativeLaneResampling {
    private let outputSampleRate: Int
    private var converter: AVAudioConverter?
    private var inputFormat: AVAudioFormat?
    private var outputFormat: AVAudioFormat?

    init(outputSampleRate: Int) {
        self.outputSampleRate = outputSampleRate
    }

    func resample(mono samples: [Float], inputSampleRate: Int) throws -> [Float] {
        guard inputSampleRate > 0, outputSampleRate > 0 else {
            throw NativeLaneResamplingError.unsupportedFormat(
                inputSampleRate: inputSampleRate,
                outputSampleRate: outputSampleRate
            )
        }
        guard inputSampleRate != outputSampleRate else {
            // Already on the grid. Passing it through keeps the samples bit-exact and avoids
            // paying for a converter that would have nothing to do.
            return samples
        }
        guard !samples.isEmpty else {
            return []
        }
        let converter = try converter(forInputSampleRate: inputSampleRate)
        guard let inputFormat, let outputFormat else {
            throw NativeLaneResamplingError.conversionFailed("converter formats unavailable")
        }
        let input = try buffer(of: samples, format: inputFormat)
        let pendingInput = PendingConverterInput(buffer: input)
        return try drain(converter, outputFormat: outputFormat, sampleCountHint: samples.count) { _, status in
            guard let next = pendingInput.take() else {
                status.pointee = .noDataNow
                return nil
            }
            status.pointee = .haveData
            return next
        }
    }

    func flush() throws -> [Float] {
        guard let converter, let outputFormat else {
            return []
        }
        return try drain(converter, outputFormat: outputFormat, sampleCountHint: 0) { _, status in
            status.pointee = .endOfStream
            return nil
        }
    }

    private func converter(forInputSampleRate inputSampleRate: Int) throws -> AVAudioConverter {
        if let converter, Int(inputFormat?.sampleRate ?? 0) == inputSampleRate {
            return converter
        }
        guard
            let input = AVAudioFormat(
                commonFormat: .pcmFormatFloat32,
                sampleRate: Double(inputSampleRate),
                channels: 1,
                interleaved: false
            ),
            let output = AVAudioFormat(
                commonFormat: .pcmFormatFloat32,
                sampleRate: Double(outputSampleRate),
                channels: 1,
                interleaved: false
            ),
            let created = AVAudioConverter(from: input, to: output)
        else {
            throw NativeLaneResamplingError.unsupportedFormat(
                inputSampleRate: inputSampleRate,
                outputSampleRate: outputSampleRate
            )
        }
        created.sampleRateConverterQuality = AVAudioQuality.high.rawValue
        converter = created
        inputFormat = input
        outputFormat = output
        return created
    }

    private func buffer(of samples: [Float], format: AVAudioFormat) throws -> AVAudioPCMBuffer {
        guard
            let buffer = AVAudioPCMBuffer(
                pcmFormat: format,
                frameCapacity: AVAudioFrameCount(samples.count)
            ),
            let channel = buffer.floatChannelData
        else {
            throw NativeLaneResamplingError.conversionFailed("input buffer allocation failed")
        }
        buffer.frameLength = AVAudioFrameCount(samples.count)
        samples.withUnsafeBufferPointer { source in
            channel[0].update(from: source.baseAddress!, count: samples.count)
        }
        return buffer
    }

    private func drain(
        _ converter: AVAudioConverter,
        outputFormat: AVAudioFormat,
        sampleCountHint: Int,
        input: @escaping AVAudioConverterInputBlock
    ) throws -> [Float] {
        let ratio = outputFormat.sampleRate / Swift.max(inputFormat?.sampleRate ?? 1, 1)
        // Headroom for the converter's own retained samples, so a whole chunk can come out at once.
        let capacity = AVAudioFrameCount(Double(sampleCountHint) * ratio) + 4_096
        guard let output = AVAudioPCMBuffer(pcmFormat: outputFormat, frameCapacity: capacity) else {
            throw NativeLaneResamplingError.conversionFailed("output buffer allocation failed")
        }
        var produced: [Float] = []
        while true {
            output.frameLength = 0
            var conversionError: NSError?
            let status = converter.convert(to: output, error: &conversionError, withInputFrom: input)
            if let conversionError {
                throw NativeLaneResamplingError.conversionFailed(conversionError.localizedDescription)
            }
            let count = Int(output.frameLength)
            if count > 0, let channel = output.floatChannelData {
                produced.append(contentsOf: UnsafeBufferPointer(start: channel[0], count: count))
            }
            // `.haveData` means the output buffer filled before the input ran out, so ask again.
            // A zero-length answer ends the loop either way: nothing more is coming.
            guard status == .haveData, count > 0 else {
                return produced
            }
        }
    }
}

/// One wire-format frame's worth of converted audio, before it is sequenced and encoded.
struct NativeLaneWireChunk: Equatable {
    var lane: CaptureLane
    var captureTimestampNS: UInt64
    var deviceEpoch: UInt64
    var discontinuity: Bool
    var samples: [Float]
}

/// Carries one lane from native buffers to exactly-sized wire frames on a converted-nanosecond
/// timeline.
///
/// Two invariants drive everything here. Frames are exact — a partial frame is only ever emitted by
/// the terminal `flush()`, so the server sees one steady cadence. And timestamps are re-derived
/// from every buffer's own converted host time rather than accumulated from the frame cadence, so a
/// meeting-length run tracks the capture device's clock instead of drifting away from it.
final class NativeLaneWireStream {
    private let lane: CaptureLane
    private let wireFormat: NativeLaneWireFormat
    private let hostTime: MachHostTimeConverting
    private let resampler: NativeLaneResampling
    private var pending: [Float] = []
    private var pendingStartNS: UInt64 = 0
    private var pendingDiscontinuity = false
    private var expectedNextCaptureNS: UInt64?
    private var deviceEpoch: UInt64 = 0
    private var hasDeviceEpoch = false
    private(set) var rejectedBuffers: UInt64 = 0

    init(
        lane: CaptureLane,
        wireFormat: NativeLaneWireFormat,
        hostTime: MachHostTimeConverting,
        resampler: NativeLaneResampling
    ) {
        self.lane = lane
        self.wireFormat = wireFormat
        self.hostTime = hostTime
        self.resampler = resampler
    }

    func append(_ buffer: NativeCapturedAudioBuffer) -> [NativeLaneWireChunk] {
        if buffer.discontinuity {
            breakTimeline()
        }
        guard buffer.frameCount > 0, buffer.sampleRate > 0 else {
            // No audio to carry. A zero-length buffer is the driver reporting a gap, not a sample.
            return []
        }
        guard let capturedNS = hostTime.nanoseconds(forHostTicks: buffer.firstSampleMonotonicNS) else {
            // The audio is real but its capture instant is not, and a fabricated timestamp would
            // corrupt the server's timeline more quietly than a hole does.
            rejectedBuffers += 1
            breakTimeline()
            return []
        }
        let converted: [Float]
        do {
            converted = try resampler.resample(
                mono: Self.downmix(buffer),
                inputSampleRate: buffer.sampleRate
            )
        } catch {
            rejectedBuffers += 1
            breakTimeline()
            return []
        }
        if hasDeviceEpoch, buffer.deviceEpoch != deviceEpoch {
            breakTimeline()
        }
        if let expected = expectedNextCaptureNS, !isContiguous(capturedNS, expected: expected) {
            breakTimeline()
        }

        // Anchor whatever is still pending immediately ahead of this buffer. Re-deriving the anchor
        // from each buffer is what keeps the wire timeline on the device's clock across a meeting.
        let pendingDurationNS = wireFormat.nanoseconds(forSamples: pending.count)
        pendingStartNS = capturedNS >= pendingDurationNS ? capturedNS - pendingDurationNS : 0
        pending.append(contentsOf: converted)
        deviceEpoch = buffer.deviceEpoch
        hasDeviceEpoch = true
        expectedNextCaptureNS = capturedNS
            + NativeLaneWireFormat.nanoseconds(
                forSamples: buffer.frameCount,
                atSampleRate: buffer.sampleRate
            )
        return drainWholeFrames()
    }

    /// Ends the stream: releases the converter's remaining samples and the trailing partial frame.
    func flush() -> [NativeLaneWireChunk] {
        if let tail = try? resampler.flush(), !tail.isEmpty {
            pending.append(contentsOf: tail)
        }
        var chunks = drainWholeFrames()
        if !pending.isEmpty {
            chunks.append(chunk(samples: pending))
            pending.removeAll(keepingCapacity: true)
        }
        expectedNextCaptureNS = nil
        return chunks
    }

    private func drainWholeFrames() -> [NativeLaneWireChunk] {
        var chunks: [NativeLaneWireChunk] = []
        while pending.count >= wireFormat.frameSamples {
            let samples = Array(pending.prefix(wireFormat.frameSamples))
            pending.removeFirst(wireFormat.frameSamples)
            chunks.append(chunk(samples: samples))
            pendingStartNS = pendingStartNS &+ wireFormat.frameDurationNS
        }
        return chunks
    }

    private func chunk(samples: [Float]) -> NativeLaneWireChunk {
        let discontinuity = pendingDiscontinuity
        pendingDiscontinuity = false
        return NativeLaneWireChunk(
            lane: lane,
            captureTimestampNS: pendingStartNS,
            deviceEpoch: deviceEpoch,
            discontinuity: discontinuity,
            samples: samples
        )
    }

    /// Marks the next frame this lane emits as spliced across a break, and stops predicting the
    /// next capture instant from a timeline that no longer runs.
    private func breakTimeline() {
        pendingDiscontinuity = true
        expectedNextCaptureNS = nil
    }

    private func isContiguous(_ capturedNS: UInt64, expected: UInt64) -> Bool {
        let drift = capturedNS >= expected ? capturedNS - expected : expected - capturedNS
        return drift <= wireFormat.contiguityToleranceNS
    }

    /// Mixes the native channels down to mono ahead of conversion, so the converter always runs
    /// one channel into one channel whatever the device presents.
    static func downmix(_ buffer: NativeCapturedAudioBuffer) -> [Float] {
        let frameCount = buffer.frameCount
        guard frameCount > 0 else {
            return []
        }
        let channelCount = Swift.max(buffer.channelCount, 1)
        if channelCount == 1 {
            guard buffer.samples.count < frameCount else {
                return Array(buffer.samples[0..<frameCount])
            }
            return buffer.samples + [Float](repeating: 0, count: frameCount - buffer.samples.count)
        }
        var mono = [Float](repeating: 0, count: frameCount)
        for frameIndex in 0..<frameCount {
            var total: Float = 0
            for channel in 0..<channelCount {
                let index = channel * frameCount + frameIndex
                if index < buffer.samples.count {
                    total += buffer.samples[index]
                }
            }
            mono[frameIndex] = total / Float(channelCount)
        }
        return mono
    }
}
