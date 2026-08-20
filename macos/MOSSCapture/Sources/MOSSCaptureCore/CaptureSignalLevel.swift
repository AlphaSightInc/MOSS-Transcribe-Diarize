import Foundation

/// Aggregate signal facts for one lane since the current capture started.
///
/// These values answer whether real signal reached the exact PCM bytes sent on the wire. They are
/// observations only: no threshold here labels a lane quiet, bad, or failed, and no audio is kept.
public struct CaptureLaneSignalLevel: Codable, Equatable, Sendable {
    public var analyzedFrames: UInt64
    public var analyzedSamples: UInt64
    public var silentFrames: UInt64
    public var malformedFrames: UInt64
    public var lastFrameRMSDBFS: Double?
    public var maxFrameRMSDBFS: Double?
    public var sessionPeakDBFS: Double?

    public init(
        analyzedFrames: UInt64 = 0,
        analyzedSamples: UInt64 = 0,
        silentFrames: UInt64 = 0,
        malformedFrames: UInt64 = 0,
        lastFrameRMSDBFS: Double? = nil,
        maxFrameRMSDBFS: Double? = nil,
        sessionPeakDBFS: Double? = nil
    ) {
        self.analyzedFrames = analyzedFrames
        self.analyzedSamples = analyzedSamples
        self.silentFrames = silentFrames
        self.malformedFrames = malformedFrames
        self.lastFrameRMSDBFS = lastFrameRMSDBFS
        self.maxFrameRMSDBFS = maxFrameRMSDBFS
        self.sessionPeakDBFS = sessionPeakDBFS
    }
}

/// Measures the canonical mono PCM16 frame, after native downmix/resampling and before transport.
/// Its lock keeps a concurrent local `status` request from reading a half-updated aggregate.
final class CaptureSignalLevelTracker: @unchecked Sendable {
    private let lock = NSLock()
    private var byLane: [CaptureLane: CaptureLaneSignalLevel] = [:]

    func reset() {
        lock.lock()
        byLane.removeAll(keepingCapacity: true)
        lock.unlock()
    }

    func observe(_ frames: [CaptureFrame]) {
        for frame in frames {
            observe(frame)
        }
    }

    func observe(_ frame: CaptureFrame) {
        guard let measured = Self.measure(frame) else {
            lock.lock()
            byLane[frame.lane, default: CaptureLaneSignalLevel()].malformedFrames += 1
            lock.unlock()
            return
        }

        lock.lock()
        var level = byLane[frame.lane, default: CaptureLaneSignalLevel()]
        level.analyzedFrames += 1
        level.analyzedSamples += UInt64(frame.sampleCount)
        level.lastFrameRMSDBFS = measured.rmsDBFS
        if measured.rmsDBFS == nil {
            level.silentFrames += 1
        }
        if let rmsDBFS = measured.rmsDBFS {
            level.maxFrameRMSDBFS = max(level.maxFrameRMSDBFS ?? -.infinity, rmsDBFS)
        }
        if let peakDBFS = measured.peakDBFS {
            level.sessionPeakDBFS = max(level.sessionPeakDBFS ?? -.infinity, peakDBFS)
        }
        byLane[frame.lane] = level
        lock.unlock()
    }

    func snapshot() -> [CaptureLane: CaptureLaneSignalLevel] {
        lock.lock()
        defer { lock.unlock() }
        return byLane
    }

    private static func measure(_ frame: CaptureFrame) -> (rmsDBFS: Double?, peakDBFS: Double?)? {
        let sampleWidth = MemoryLayout<Int16>.size
        guard frame.sampleCount > 0,
              !frame.pcm16.isEmpty,
              frame.pcm16.count.isMultiple(of: sampleWidth),
              frame.pcm16.count / sampleWidth == frame.sampleCount else {
            return nil
        }

        var squaredSum = 0.0
        var absolutePeak = 0.0
        frame.pcm16.withUnsafeBytes { raw in
            for offset in stride(from: 0, to: raw.count, by: sampleWidth) {
                let bits = UInt16(raw[offset]) | (UInt16(raw[offset + 1]) << 8)
                let sample = Double(Int16(bitPattern: bits))
                squaredSum += sample * sample
                absolutePeak = max(absolutePeak, abs(sample))
            }
        }
        let rms = sqrt(squaredSum / Double(frame.sampleCount))
        return (dbfs(rms), dbfs(absolutePeak))
    }

    /// Full scale is 32768 because PCM16 includes -32768. Digital zero is `nil`: JSON cannot carry
    /// negative infinity, and inventing a floor here would silently create a policy threshold.
    private static func dbfs(_ magnitude: Double) -> Double? {
        guard magnitude > 0 else { return nil }
        return 20.0 * log10(magnitude / 32_768.0)
    }
}
