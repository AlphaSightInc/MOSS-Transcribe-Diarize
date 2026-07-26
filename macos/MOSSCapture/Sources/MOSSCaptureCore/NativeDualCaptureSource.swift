import Foundation

protocol NativeAudioCaptureComponent: AnyObject {
    func start(queue: RealTimeNativeAudioBufferQueue) throws
    func stop()
}

protocol NativeLaneHealthReportingComponent: AnyObject {
    func attachHealthSink(_ sink: NativeLaneHealthFactSink, lane: CaptureLane, generation: UInt64)
}

extension SystemAudioTap: NativeAudioCaptureComponent {}
extension SystemAudioTap: NativeLaneHealthReportingComponent {}
extension MicrophoneCapture: NativeAudioCaptureComponent {}
extension MicrophoneCapture: NativeLaneHealthReportingComponent {}

public final class NativeDualCaptureSource: CaptureSourceAdapter {
    private let lock = NSLock()
    private let system: NativeAudioCaptureComponent
    private let microphone: NativeAudioCaptureComponent
    private let queue: RealTimeNativeAudioBufferQueue
    private let emitter: NativeLaneFrameEmitter
    private let health = NativeLaneHealth()
    private var started = false
    private var activeGeneration: UInt64?
    private var reportedDroppedBuffers: [CaptureLane: UInt64] = [:]
    private var latestFrames: [CaptureLane: CaptureFrame] = [:]

    public convenience init(queueCapacity: Int = 128) {
        self.init(
            system: SystemAudioTap(),
            microphone: MicrophoneCapture(),
            queue: RealTimeNativeAudioBufferQueue(capacity: queueCapacity),
            emitter: NativeLaneFrameEmitter()
        )
    }

    init(
        system: NativeAudioCaptureComponent,
        microphone: NativeAudioCaptureComponent,
        queue: RealTimeNativeAudioBufferQueue,
        emitter: NativeLaneFrameEmitter = NativeLaneFrameEmitter()
    ) {
        self.system = system
        self.microphone = microphone
        self.queue = queue
        self.emitter = emitter
    }

    public func start(configuration: CaptureConfiguration) throws {
        guard #available(macOS 14.2, *) else {
            throw NativeCaptureError.unavailable("macOS 14.2 process taps required")
        }
        let generation = health.beginGeneration()
        lock.lock()
        latestFrames.removeAll(keepingCapacity: true)
        activeGeneration = generation
        reportedDroppedBuffers.removeAll(keepingCapacity: true)
        lock.unlock()

        let systemError = start(system, lane: .system, generation: generation)
        let microphoneError = start(microphone, lane: .microphone, generation: generation)
        let admittedLaneCount = [systemError, microphoneError].filter { $0 == nil }.count

        guard admittedLaneCount > 0 else {
            system.stop()
            microphone.stop()
            lock.lock()
            started = false
            lock.unlock()
            throw systemError ?? microphoneError ?? NativeCaptureError.deviceUnavailable("no native lanes admitted")
        }

        lock.lock()
        started = true
        lock.unlock()
    }

    public func pendingFrames() throws -> [CaptureFrame] {
        lock.lock()
        let isStarted = started
        lock.unlock()
        guard isStarted else {
            return []
        }
        let frames = emitter.frames(from: queue.drain())
        lock.lock()
        let generation = activeGeneration
        for frame in frames {
            latestFrames[frame.lane] = frame
        }
        lock.unlock()
        if let generation {
            enqueueCounterFacts(for: frames, generation: generation)
        }
        return frames
    }

    public func status() -> [CaptureLaneStatus] {
        lock.lock()
        let isStarted = started
        let framesByLane = latestFrames
        lock.unlock()
        return health.statuses(running: isStarted).map { status in
            let latest = framesByLane[status.lane]
            let state = isStarted && status.state == "stopped" ? "recovering" : status.state
            return CaptureLaneStatus(
                lane: status.lane,
                sequence: latest?.sequence ?? status.sequence,
                deviceEpoch: latest?.deviceEpoch ?? status.deviceEpoch,
                state: state,
                droppedFrames: status.droppedFrames,
                discontinuities: status.discontinuities,
                failureCode: status.failureCode
            )
        }
    }

    public func stop(deadline: Date) throws {
        health.invalidateGeneration()
        microphone.stop()
        system.stop()
        lock.lock()
        started = false
        activeGeneration = nil
        lock.unlock()
    }

    private func start(
        _ component: NativeAudioCaptureComponent,
        lane: CaptureLane,
        generation: UInt64
    ) -> Error? {
        (component as? NativeLaneHealthReportingComponent)?
            .attachHealthSink(health, lane: lane, generation: generation)
        do {
            try component.start(queue: queue)
            health.enqueue(.admitted, lane: lane, generation: generation)
            return nil
        } catch {
            if let nativeError = error as? NativeCaptureError {
                health.enqueue(.startFailed(nativeError), lane: lane, generation: generation)
            } else {
                health.enqueue(.unexpectedCaptureError(String(describing: error)), lane: lane, generation: generation)
            }
            return error
        }
    }

    private func enqueueCounterFacts(for frames: [CaptureFrame], generation: UInt64) {
        let droppedByLane = queue.droppedBuffersByLaneSnapshot()
        let discontinuitiesByLane = Dictionary(
            grouping: frames.filter(\.discontinuity),
            by: \.lane
        ).mapValues { UInt64($0.count) }
        var facts: [(CaptureLane, NativeLaneFact)] = []
        lock.lock()
        for lane in CaptureLane.allCases {
            let discontinuities = discontinuitiesByLane[lane, default: 0]
            if discontinuities > 0 {
                facts.append((lane, .discontinuity(count: discontinuities)))
            }
            let lastReportedDropped = reportedDroppedBuffers[lane, default: 0]
            let dropped = droppedByLane[lane, default: 0]
            if dropped > lastReportedDropped {
                facts.append((lane, .bufferOverrun(droppedBuffers: dropped - lastReportedDropped)))
                reportedDroppedBuffers[lane] = dropped
            }
        }
        lock.unlock()
        for (lane, fact) in facts {
            health.enqueue(fact, lane: lane, generation: generation)
        }
    }
}
