import Foundation

protocol NativeAudioCaptureComponent: AnyObject {
    func start(queue: RealTimeNativeAudioBufferQueue) throws
    func stop()
}

extension SystemAudioTap: NativeAudioCaptureComponent {}
extension MicrophoneCapture: NativeAudioCaptureComponent {}

public final class NativeDualCaptureSource: CaptureSourceAdapter {
    private let system: NativeAudioCaptureComponent
    private let microphone: NativeAudioCaptureComponent
    private let queue: RealTimeNativeAudioBufferQueue
    private let emitter: NativeLaneFrameEmitter
    private var started = false
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
        try system.start(queue: queue)
        do {
            try microphone.start(queue: queue)
            started = true
        } catch {
            system.stop()
            throw error
        }
    }

    public func pendingFrames() throws -> [CaptureFrame] {
        guard started else {
            return []
        }
        let frames = emitter.frames(from: queue.drain())
        for frame in frames {
            latestFrames[frame.lane] = frame
        }
        return frames
    }

    public func status() -> [CaptureLaneStatus] {
        CaptureLane.allCases.map { lane in
            let latest = latestFrames[lane]
            return CaptureLaneStatus(
                lane: lane,
                sequence: latest?.sequence ?? 0,
                deviceEpoch: latest?.deviceEpoch ?? 0,
                state: started ? "capturing" : "stopped"
            )
        }
    }

    public func stop(deadline: Date) throws {
        microphone.stop()
        system.stop()
        started = false
    }
}
