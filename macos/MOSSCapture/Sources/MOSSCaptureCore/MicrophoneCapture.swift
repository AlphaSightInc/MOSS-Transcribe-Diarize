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
    private let lock = NSLock()
    private weak var healthSink: NativeLaneHealthFactSink?
    private var healthLane = CaptureLane.microphone
    private var healthGeneration: UInt64 = 0
    private var tapInstalled = false
    private var configurationHandlerInstalled = false
    private var engineStarted = false
    private var stopping = false

    public init(engine: AVAudioEngine = AVAudioEngine(), deviceEpoch: UInt64 = 0) {
        _ = deviceEpoch
        self.driver = AVAudioEngineMicrophoneDriver(engine: engine)
    }

    init(driver: MicrophoneCaptureDriver) {
        self.driver = driver
    }

    func attachHealthSink(_ sink: NativeLaneHealthFactSink, lane: CaptureLane, generation: UInt64) {
        lock.lock()
        healthSink = sink
        healthLane = lane
        healthGeneration = generation
        lock.unlock()
    }

    public func start(queue: RealTimeNativeAudioBufferQueue) throws {
        setStopping(false)
        do {
            let permission = driver.recordPermission()
            emit(.permission(permission))
            if permission == .denied {
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
            do {
                emit(.deviceEpoch(UInt64(try driver.currentInputDeviceID())))
            } catch {
                emit(.unexpectedCaptureError(String(describing: error)))
            }
        case .engineRunning(false):
            if isEngineStarted() && !isStopping() {
                emit(.ioStoppedAbnormally("microphone engine stopped unexpectedly"))
            }
        case .engineOverloaded:
            emit(.overload(count: 1))
        case .engineRunning(true):
            break
        }
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
}

extension MicrophoneCapture: @unchecked Sendable {}

enum MicrophoneCaptureEngineObservation: Equatable {
    case configurationChanged
    case engineRunning(Bool)
    case engineOverloaded
}

protocol MicrophoneCaptureDriver: AnyObject {
    func recordPermission() -> NativeLanePermissionFact
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
