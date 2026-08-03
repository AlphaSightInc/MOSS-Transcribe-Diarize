import AudioToolbox
import AVFoundation
@preconcurrency import AVFAudio
import CoreAudio
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

    private let driver: MicrophoneCaptureDriver
    private let reconciliationScheduler: MicrophoneCaptureReconciliationScheduling
    private let lock = NSLock()
    private weak var healthSink: NativeLaneHealthFactSink?
    private var healthLane = CaptureLane.microphone
    private var healthGeneration: UInt64 = 0
    private var tapInstalled = false
    private var configurationHandlerInstalled = false
    private var engineStarted = false
    private var reconciliationPending = false
    private var stopping = false

    public init(engine: AVAudioEngine = AVAudioEngine(), deviceEpoch: UInt64 = 0) {
        _ = deviceEpoch
        self.driver = AVAudioEngineMicrophoneDriver(engine: engine)
        self.reconciliationScheduler = DispatchMicrophoneCaptureReconciliationScheduler()
    }

    init(
        driver: MicrophoneCaptureDriver,
        reconciliationScheduler: MicrophoneCaptureReconciliationScheduling =
            DispatchMicrophoneCaptureReconciliationScheduler()
    ) {
        self.driver = driver
        self.reconciliationScheduler = reconciliationScheduler
    }

    func attachHealthSink(_ sink: NativeLaneHealthFactSink, lane: CaptureLane, generation: UInt64) {
        lock.lock()
        healthSink = sink
        healthLane = lane
        healthGeneration = generation
        lock.unlock()
    }

    /// Non-blocking read of this lane's recording decision. Never touches `AVAudioEngine`.
    func authorization() -> NativeLanePermissionFact {
        driver.recordPermission()
    }

    /// The one user-initiated microphone permission transition. It returns immediately and the
    /// user's answer arrives later, on an arbitrary thread, so the caller's control loop stays
    /// responsive for the whole time the prompt is on screen.
    func requestAuthorization(
        _ completion: @escaping @Sendable (NativeLanePermissionFact) -> Void
    ) {
        driver.requestRecordPermission(completion)
    }

    public func start(queue: RealTimeNativeAudioBufferQueue) throws {
        setStopping(false)
        do {
            let permission = driver.recordPermission()
            emit(.permission(permission))
            guard permission == .granted else {
                // Anything short of a grant must stop here. `.undetermined` in particular may
                // never reach `AVAudioEngine.inputNode`: a process that cannot answer the TCC
                // prompt blocks forever inside `AVAudioEngineImpl::UpdateInputNode`, taking the
                // single-threaded control loop down with it. The permission coordinator asks for
                // the decision first and starts this lane only once it is `.granted`.
                throw NativeCaptureError.permissionDenied("microphone")
            }
            let currentDeviceID = try driver.currentInputDeviceID()
            try driver.installConfigurationChangeHandler { [weak self] observation in
                self?.handleEngineObservation(observation)
            }
            configurationHandlerInstalled = true
            try driver.installTap(queue: queue, deviceEpoch: UInt64(currentDeviceID))
            tapInstalled = true
            try driver.startEngine()
            setEngineStarted(true)
            emit(.deviceEpoch(UInt64(currentDeviceID)))
        } catch {
            stop()
            throw error
        }
    }

    public func stop() {
        setStopping(true)
        if configurationHandlerInstalled {
            driver.removeConfigurationChangeHandler()
            configurationHandlerInstalled = false
        }
        if tapInstalled {
            driver.removeTap()
            tapInstalled = false
        }
        if isEngineStarted() {
            driver.stopEngine()
            setEngineStarted(false)
        }
        setStopping(false)
    }

    private func handleEngineObservation(_ observation: MicrophoneCaptureEngineObservation) {
        switch observation {
        case .configurationChanged:
            setReconciliationPending(true)
            emit(.configurationChanged)
            reconciliationScheduler.schedule { [weak self] in
                self?.reconcileCurrentInputDevice()
            }
        case .engineRunning(false):
            if isEngineStarted() && !isStopping() && !isReconciliationPending() {
                emit(.ioStoppedAbnormally("microphone engine stopped unexpectedly"))
            }
        case .engineOverloaded:
            emit(.overload(count: 1))
        case .engineRunning(true):
            break
        }
    }

    private func reconcileCurrentInputDevice() {
        do {
            let deviceID = try driver.currentInputDeviceID()
            emit(.deviceEpoch(UInt64(deviceID)))
        } catch {
            emit(.reconciliationUnresolved(String(describing: error)))
        }
        setReconciliationPending(false)
    }

    private func emit(_ fact: NativeLaneFact) {
        let snapshot: (NativeLaneHealthFactSink?, CaptureLane, UInt64)
        lock.lock()
        snapshot = (healthSink, healthLane, healthGeneration)
        lock.unlock()
        snapshot.0?.enqueue(fact, lane: snapshot.1, generation: snapshot.2)
    }

    private func setStopping(_ value: Bool) {
        lock.lock()
        stopping = value
        lock.unlock()
    }

    private func isStopping() -> Bool {
        lock.lock()
        let value = stopping
        lock.unlock()
        return value
    }

    private func isEngineStarted() -> Bool {
        lock.lock()
        let value = engineStarted
        lock.unlock()
        return value
    }

    private func setEngineStarted(_ value: Bool) {
        lock.lock()
        engineStarted = value
        lock.unlock()
    }

    private func setReconciliationPending(_ value: Bool) {
        lock.lock()
        reconciliationPending = value
        lock.unlock()
    }

    private func isReconciliationPending() -> Bool {
        lock.lock()
        let value = reconciliationPending
        lock.unlock()
        return value
    }
}

extension MicrophoneCapture: @unchecked Sendable {}

enum MicrophoneCaptureEngineObservation: Equatable {
    case configurationChanged
    case engineRunning(Bool)
    case engineOverloaded
}

protocol MicrophoneCaptureDriver: AnyObject {
    func recordPermission() -> NativeLanePermissionFact
    func requestRecordPermission(
        _ completion: @escaping @Sendable (NativeLanePermissionFact) -> Void
    )
    func currentInputDeviceID() throws -> AudioDeviceID
    func installConfigurationChangeHandler(
        _ handler: @escaping @Sendable (MicrophoneCaptureEngineObservation) -> Void
    ) throws
    func removeConfigurationChangeHandler()
    func installTap(queue: RealTimeNativeAudioBufferQueue, deviceEpoch: UInt64) throws
    func startEngine() throws
    func stopEngine()
    func removeTap()
}

protocol MicrophoneCaptureReconciliationScheduling: Sendable {
    func schedule(_ operation: @escaping @Sendable () -> Void)
}

private struct DispatchMicrophoneCaptureReconciliationScheduler:
    MicrophoneCaptureReconciliationScheduling
{
    private let queue = DispatchQueue(label: "moss.capture.microphone.reconciliation")

    func schedule(_ operation: @escaping @Sendable () -> Void) {
        queue.async(execute: operation)
    }
}

private final class AVAudioEngineMicrophoneDriver: MicrophoneCaptureDriver {
    private static let configurationChangeNotification =
        Notification.Name("AVAudioEngineConfigurationChangeNotification")
    private let engine: AVAudioEngine
    private let notificationCenter: NotificationCenter
    private var configurationObserver: NSObjectProtocol?

    init(
        engine: AVAudioEngine,
        notificationCenter: NotificationCenter = .default
    ) {
        self.engine = engine
        self.notificationCenter = notificationCenter
    }

    func recordPermission() -> NativeLanePermissionFact {
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .notDetermined:
            return .undetermined
        case .authorized:
            return .granted
        case .denied, .restricted:
            return .denied
        @unknown default:
            return .undetermined
        }
    }

    func requestRecordPermission(
        _ completion: @escaping @Sendable (NativeLanePermissionFact) -> Void
    ) {
        AVCaptureDevice.requestAccess(for: .audio) { granted in
            completion(granted ? .granted : .denied)
        }
    }

    func currentInputDeviceID() throws -> AudioDeviceID {
        guard let audioUnit = engine.inputNode.audioUnit else {
            throw NativeCaptureError.deviceUnavailable("microphone input audio unit unavailable")
        }
        var deviceID = AudioDeviceID(kAudioObjectUnknown)
        var size = UInt32(MemoryLayout<AudioDeviceID>.size)
        let status = AudioUnitGetProperty(
            audioUnit,
            kAudioOutputUnitProperty_CurrentDevice,
            kAudioUnitScope_Global,
            0,
            &deviceID,
            &size
        )
        guard status == noErr, deviceID != AudioDeviceID(kAudioObjectUnknown) else {
            throw NativeCaptureError.osStatus("kAudioOutputUnitProperty_CurrentDevice", status)
        }
        return deviceID
    }

    func installConfigurationChangeHandler(
        _ handler: @escaping @Sendable (MicrophoneCaptureEngineObservation) -> Void
    ) throws {
        configurationObserver = notificationCenter.addObserver(
            forName: Self.configurationChangeNotification,
            object: engine,
            queue: nil
        ) { [weak engine] _ in
            handler(.configurationChanged)
            handler(.engineRunning(engine?.isRunning ?? false))
        }
    }

    func removeConfigurationChangeHandler() {
        if let configurationObserver {
            notificationCenter.removeObserver(configurationObserver)
            self.configurationObserver = nil
        }
    }

    func installTap(queue: RealTimeNativeAudioBufferQueue, deviceEpoch: UInt64) throws {
        let inputNode = engine.inputNode
        let format = inputNode.inputFormat(forBus: 0)
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
    }

    func startEngine() throws {
        do {
            try engine.start()
        } catch let error as NSError {
            throw NativeCaptureError.osStatus("AVAudioEngine.start", Int32(error.code))
        }
    }

    func stopEngine() {
        engine.stop()
    }

    func removeTap() {
        engine.inputNode.removeTap(onBus: 0)
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
        let failClosed = {
            NativeCapturedAudioBuffer(
                lane: lane,
                sampleRate: Int(buffer.format.sampleRate),
                channelCount: 1,
                frameCount: 0,
                firstSampleMonotonicNS: 0,
                deviceEpoch: deviceEpoch,
                discontinuity: true,
                samples: []
            )
        }
        guard channelCount > 0,
              frameCount > 0,
              frameCount <= Int(buffer.frameCapacity),
              buffer.stride > 0,
              buffer.format.commonFormat == .pcmFormatFloat32,
              let channelData = buffer.floatChannelData else {
            return failClosed()
        }
        var samples = [Float](repeating: 0, count: channelCount * frameCount)
        for channel in 0..<channelCount {
            for frame in 0..<frameCount {
                samples[channel * frameCount + frame] =
                    channelData[channel][frame * buffer.stride]
            }
        }
        return NativeCapturedAudioBuffer(
            lane: lane,
            sampleRate: Int(buffer.format.sampleRate),
            channelCount: Swift.max(channelCount, 1),
            frameCount: frameCount,
            // Raw Mach ticks. They are converted to nanoseconds off this thread; a reading the
            // engine did not fill in travels as zero and is rejected there rather than guessed at.
            firstSampleMonotonicNS: time.isHostTimeValid ? time.hostTime : 0,
            deviceEpoch: deviceEpoch,
            discontinuity: false,
            samples: samples
        )
    }
}
