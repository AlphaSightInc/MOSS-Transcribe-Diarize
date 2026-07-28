import CoreAudio
import Foundation

public struct SystemAudioTapSourceVector: Equatable, Sendable {
    public var tapDescription: String
    public var processTapFunction: String
    public var aggregateDevice: String
    public var halCallbackFunction: String
    public var realtimeCallbackWork: [String]
}

/// How System Audio Recording permission is resolved for the system lane.
///
/// macOS publishes neither a preflight nor a request API for it, and Screen Recording preflight
/// is a different permission for a different lane. The user-initiated recording start that
/// `SystemAudioTap.start(queue:)` performs — `AudioHardwareCreateProcessTap` followed by
/// `AudioDeviceStart` on the transient aggregate — *is* the request. The lane therefore asks
/// nothing at launch, prompts only from a user `start`, and learns its decision from that one
/// attempt.
enum SystemAudioPermission {
    /// Maps the outcome of one user-initiated recording start onto the lane's decision.
    /// A failure that is not permission-shaped leaves the decision unresolved (`nil`): the lane's
    /// typed failure already carries the device or OSStatus reason, and guessing "denied" from it
    /// would report a permission problem the user cannot fix.
    static func state(afterRecordingStart error: Error?) -> NativeLanePermissionState? {
        guard let error else {
            return .granted
        }
        guard let nativeError = error as? NativeCaptureError,
              case .permissionDenied = nativeError
        else {
            return nil
        }
        return .denied
    }
}

public enum NativeCaptureError: Error, Equatable {
    case unavailable(String)
    case osStatus(String, Int32)
    case permissionDenied(String)
    case deviceUnavailable(String)
    case transportUnavailable(String)
}

protocol SystemAudioTapDriver: AnyObject {
    func createProcessTap(description: CATapDescription) throws -> AudioObjectID
    func createAggregateDevice(for description: CATapDescription) throws -> AudioObjectID
    func installDeviceLifecycleListeners(
        on aggregateDeviceID: AudioObjectID,
        handler: @escaping (SystemAudioTapDeviceObservation) -> Void
    ) throws
    func removeDeviceLifecycleListeners(on aggregateDeviceID: AudioObjectID)
    func createIOProc(
        on aggregateDeviceID: AudioObjectID,
        queue: RealTimeNativeAudioBufferQueue,
        sampleRate: Int,
        deviceEpoch: UInt64
    ) throws
    func startDevice(_ aggregateDeviceID: AudioObjectID) throws
    func stopDevice(_ aggregateDeviceID: AudioObjectID)
    func destroyIOProc(on aggregateDeviceID: AudioObjectID)
    func destroyAggregateDevice(_ aggregateDeviceID: AudioObjectID)
    func destroyProcessTap(_ tapID: AudioObjectID)
}

enum SystemAudioTapDeviceObservation: Equatable {
    case isAlive(Bool)
    case isRunning(Bool)
    case configurationChanged
}

public final class SystemAudioTap {
    public static let sourceVector = SystemAudioTapSourceVector(
        tapDescription: "private unmuted CATapDescription",
        processTapFunction: "AudioHardwareCreateProcessTap",
        aggregateDevice: "private transient aggregate",
        halCallbackFunction: "AudioDeviceCreateIOProcIDWithBlock",
        realtimeCallbackWork: ["copy native buffer", "enqueue monotonic first-sample time"]
    )

    private let lock = NSLock()
    private let sampleRate: Int
    private let deviceEpoch: UInt64
    private let driver: SystemAudioTapDriver
    private weak var healthSink: NativeLaneHealthFactSink?
    private var healthLane = CaptureLane.system
    private var healthGeneration: UInt64 = 0
    private var tapID = AudioObjectID(kAudioObjectUnknown)
    private var aggregateDeviceID = AudioObjectID(kAudioObjectUnknown)
    private var lifecycleListenersInstalled = false
    private var ioProcInstalled = false
    private var ioStarted = false
    private var stopping = false

    public init(sampleRate: Int = 48_000, deviceEpoch: UInt64 = 0) {
        self.sampleRate = sampleRate
        self.deviceEpoch = deviceEpoch
        self.driver = CoreAudioSystemTapDriver()
    }

    init(
        sampleRate: Int = 48_000,
        deviceEpoch: UInt64 = 0,
        driver: SystemAudioTapDriver
    ) {
        self.sampleRate = sampleRate
        self.deviceEpoch = deviceEpoch
        self.driver = driver
    }

    public func makeTapDescription(name: String = "MOSS System Audio Tap") -> CATapDescription {
        let description = CATapDescription()
        description.name = name
        description.uuid = UUID()
        description.isPrivate = true
        description.isMixdown = true
        description.isMono = false
        description.isExclusive = true
        description.muteBehavior = .unmuted
        return description
    }

    func attachHealthSink(_ sink: NativeLaneHealthFactSink, lane: CaptureLane, generation: UInt64) {
        lock.lock()
        healthSink = sink
        healthLane = lane
        healthGeneration = generation
        lock.unlock()
    }

    public func start(queue: RealTimeNativeAudioBufferQueue) throws {
        let description = makeTapDescription()
        setStopping(false)
        do {
            tapID = try driver.createProcessTap(description: description)
            aggregateDeviceID = try driver.createAggregateDevice(for: description)
            try driver.installDeviceLifecycleListeners(on: aggregateDeviceID) { [weak self] observation in
                self?.handleDeviceObservation(observation)
            }
            lifecycleListenersInstalled = true
            try driver.createIOProc(
                on: aggregateDeviceID,
                queue: queue,
                sampleRate: sampleRate,
                deviceEpoch: deviceEpoch
            )
            ioProcInstalled = true
            try driver.startDevice(aggregateDeviceID)
            setIOStarted(true)
            emit(.deviceEpoch(deviceEpoch))
        } catch {
            stop()
            throw error
        }
    }

    public func stop() {
        setStopping(true)
        if isIOStarted() {
            driver.stopDevice(aggregateDeviceID)
            setIOStarted(false)
        }
        if lifecycleListenersInstalled {
            driver.removeDeviceLifecycleListeners(on: aggregateDeviceID)
            lifecycleListenersInstalled = false
        }
        if ioProcInstalled {
            driver.destroyIOProc(on: aggregateDeviceID)
            ioProcInstalled = false
        }
        if aggregateDeviceID != AudioObjectID(kAudioObjectUnknown) {
            driver.destroyAggregateDevice(aggregateDeviceID)
            aggregateDeviceID = AudioObjectID(kAudioObjectUnknown)
        }
        if tapID != AudioObjectID(kAudioObjectUnknown) {
            driver.destroyProcessTap(tapID)
            tapID = AudioObjectID(kAudioObjectUnknown)
        }
        setStopping(false)
    }

    private func handleDeviceObservation(_ observation: SystemAudioTapDeviceObservation) {
        let shouldReportAbnormalStop: Bool
        lock.lock()
        shouldReportAbnormalStop = ioStarted && !stopping
        lock.unlock()

        switch observation {
        case .isAlive(false):
            emit(.deviceUnavailable("system tap aggregate device is not alive"))
        case .isRunning(false):
            if shouldReportAbnormalStop {
                emit(.ioStoppedAbnormally("system tap aggregate device stopped unexpectedly"))
            }
        case .configurationChanged:
            emit(.deviceEpoch(deviceEpoch))
        case .isAlive(true), .isRunning(true):
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

    private func isIOStarted() -> Bool {
        lock.lock()
        let value = ioStarted
        lock.unlock()
        return value
    }

    private func setIOStarted(_ value: Bool) {
        lock.lock()
        ioStarted = value
        lock.unlock()
    }
}

private final class CoreAudioSystemTapDriver: SystemAudioTapDriver {
    private var ioProcID: AudioDeviceIOProcID?
    private let listenerQueue = DispatchQueue(label: "moss.capture.system-tap.lifecycle")
    private var listenerBlocks: [AudioObjectPropertySelector: AudioObjectPropertyListenerBlock] = [:]

    func createProcessTap(description: CATapDescription) throws -> AudioObjectID {
        guard #available(macOS 14.2, *) else {
            throw NativeCaptureError.unavailable("macOS 14.2 process taps required")
        }
        var createdTapID = AudioObjectID(kAudioObjectUnknown)
        let status = AudioHardwareCreateProcessTap(description, &createdTapID)
        guard status == noErr else {
            throw NativeCaptureError.osStatus("AudioHardwareCreateProcessTap", status)
        }
        return createdTapID
    }

    func createAggregateDevice(for description: CATapDescription) throws -> AudioObjectID {
        let tapUID = description.uuid.uuidString
        let aggregateUID = "moss.capture.aggregate.\(UUID().uuidString)"
        let tap: [String: Any] = [
            kAudioSubTapUIDKey: tapUID,
            kAudioSubTapDriftCompensationKey: true
        ]
        let aggregate: [String: Any] = [
            kAudioAggregateDeviceUIDKey: aggregateUID,
            kAudioAggregateDeviceNameKey: "MOSS Transient Capture Aggregate",
            kAudioAggregateDeviceIsPrivateKey: true,
            kAudioAggregateDeviceIsStackedKey: false,
            kAudioAggregateDeviceTapListKey: [tap],
            kAudioAggregateDeviceTapAutoStartKey: false
        ]
        var deviceID = AudioObjectID(kAudioObjectUnknown)
        let status = AudioHardwareCreateAggregateDevice(aggregate as CFDictionary, &deviceID)
        guard status == noErr else {
            throw NativeCaptureError.osStatus("AudioHardwareCreateAggregateDevice", status)
        }
        return deviceID
    }

    func installDeviceLifecycleListeners(
        on aggregateDeviceID: AudioObjectID,
        handler: @escaping (SystemAudioTapDeviceObservation) -> Void
    ) throws {
        let listenerSpecs: [(AudioObjectPropertySelector, SystemAudioTapDeviceObservation?)] = [
            (kAudioDevicePropertyDeviceIsAlive, nil),
            (kAudioDevicePropertyDeviceIsRunning, nil),
            (kAudioDevicePropertyDeviceHasChanged, .configurationChanged),
        ]
        for (selector, fixedObservation) in listenerSpecs {
            var address = AudioObjectPropertyAddress(
                mSelector: selector,
                mScope: kAudioObjectPropertyScopeGlobal,
                mElement: kAudioObjectPropertyElementMain
            )
            let block: AudioObjectPropertyListenerBlock = { [weak self] count, addresses in
                guard let self else {
                    return
                }
                let changed = UnsafeBufferPointer(start: addresses, count: Int(count))
                guard changed.contains(where: { $0.mSelector == selector }) else {
                    return
                }
                if let fixedObservation {
                    handler(fixedObservation)
                } else if selector == kAudioDevicePropertyDeviceIsAlive {
                    handler(.isAlive(self.readBooleanProperty(selector, on: aggregateDeviceID) ?? false))
                } else if selector == kAudioDevicePropertyDeviceIsRunning {
                    handler(.isRunning(self.readBooleanProperty(selector, on: aggregateDeviceID) ?? false))
                }
            }
            let status = AudioObjectAddPropertyListenerBlock(
                aggregateDeviceID,
                &address,
                listenerQueue,
                block
            )
            guard status == noErr else {
                removeDeviceLifecycleListeners(on: aggregateDeviceID)
                throw NativeCaptureError.osStatus("AudioObjectAddPropertyListenerBlock", status)
            }
            listenerBlocks[selector] = block
        }
    }

    func removeDeviceLifecycleListeners(on aggregateDeviceID: AudioObjectID) {
        for (selector, block) in listenerBlocks {
            var address = AudioObjectPropertyAddress(
                mSelector: selector,
                mScope: kAudioObjectPropertyScopeGlobal,
                mElement: kAudioObjectPropertyElementMain
            )
            AudioObjectRemovePropertyListenerBlock(
                aggregateDeviceID,
                &address,
                listenerQueue,
                block
            )
        }
        listenerBlocks.removeAll(keepingCapacity: true)
    }

    func createIOProc(
        on aggregateDeviceID: AudioObjectID,
        queue: RealTimeNativeAudioBufferQueue,
        sampleRate: Int,
        deviceEpoch: UInt64
    ) throws {
        var createdIOProcID: AudioDeviceIOProcID?
        let status = AudioDeviceCreateIOProcIDWithBlock(
            &createdIOProcID,
            aggregateDeviceID,
            nil
        ) { _, inputData, inputTime, _, _ in
            let buffer = NativeCapturedAudioBuffer.copyFromAudioBufferList(
                lane: .system,
                sampleRate: sampleRate,
                deviceEpoch: deviceEpoch,
                inputData: inputData,
                inputTime: inputTime
            )
            queue.enqueueFromRealtimeCallback(buffer)
        }
        guard status == noErr else {
            throw NativeCaptureError.osStatus("AudioDeviceCreateIOProcIDWithBlock", status)
        }
        ioProcID = createdIOProcID
    }

    func startDevice(_ aggregateDeviceID: AudioObjectID) throws {
        let status = AudioDeviceStart(aggregateDeviceID, ioProcID)
        guard status == noErr else {
            throw NativeCaptureError.osStatus("AudioDeviceStart", status)
        }
    }

    func stopDevice(_ aggregateDeviceID: AudioObjectID) {
        _ = AudioDeviceStop(aggregateDeviceID, ioProcID)
    }

    func destroyIOProc(on aggregateDeviceID: AudioObjectID) {
        if let ioProcID {
            AudioDeviceDestroyIOProcID(aggregateDeviceID, ioProcID)
            self.ioProcID = nil
        }
    }

    func destroyAggregateDevice(_ aggregateDeviceID: AudioObjectID) {
        AudioHardwareDestroyAggregateDevice(aggregateDeviceID)
    }

    func destroyProcessTap(_ tapID: AudioObjectID) {
        if #available(macOS 14.2, *) {
            AudioHardwareDestroyProcessTap(tapID)
        }
    }

    private func readBooleanProperty(
        _ selector: AudioObjectPropertySelector,
        on objectID: AudioObjectID
    ) -> Bool? {
        var address = AudioObjectPropertyAddress(
            mSelector: selector,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        var value: UInt32 = 0
        var size = UInt32(MemoryLayout<UInt32>.size)
        let status = AudioObjectGetPropertyData(objectID, &address, 0, nil, &size, &value)
        guard status == noErr else {
            return nil
        }
        return value != 0
    }
}

extension NativeCapturedAudioBuffer {
    static func copyFromAudioBufferList(
        lane: CaptureLane,
        sampleRate: Int,
        deviceEpoch: UInt64,
        inputData: UnsafePointer<AudioBufferList>?,
        inputTime: UnsafePointer<AudioTimeStamp>?
    ) -> NativeCapturedAudioBuffer {
        guard let inputData else {
            return NativeCapturedAudioBuffer(
                lane: lane,
                sampleRate: sampleRate,
                channelCount: 1,
                frameCount: 0,
                firstSampleMonotonicNS: 0,
                deviceEpoch: deviceEpoch,
                discontinuity: true,
                samples: []
            )
        }

        var samples: [Float] = []
        var channelCount = 0
        var frameCount = 0
        withUnsafePointer(to: inputData.pointee.mBuffers) { firstBuffer in
            let buffers = UnsafeBufferPointer(
                start: firstBuffer,
                count: Int(inputData.pointee.mNumberBuffers)
            )
            for buffer in buffers {
                let count = Int(buffer.mDataByteSize) / MemoryLayout<Float>.stride
                guard count > 0, let data = buffer.mData else {
                    continue
                }
                let channels = Swift.max(1, Int(buffer.mNumberChannels))
                channelCount += channels
                frameCount = Swift.max(frameCount, count / channels)
                let floats = data.assumingMemoryBound(to: Float.self)
                samples.append(contentsOf: UnsafeBufferPointer(start: floats, count: count))
            }
        }

        // Raw Mach ticks, converted to nanoseconds off this thread. A timestamp the HAL did not
        // mark valid travels as zero, which the conversion stage refuses instead of inventing a
        // capture instant for.
        var hostTicks: UInt64 = 0
        if let inputTime, inputTime.pointee.mFlags.contains(.hostTimeValid) {
            hostTicks = inputTime.pointee.mHostTime
        }

        return NativeCapturedAudioBuffer(
            lane: lane,
            sampleRate: sampleRate,
            channelCount: Swift.max(channelCount, 1),
            frameCount: frameCount,
            firstSampleMonotonicNS: hostTicks,
            deviceEpoch: deviceEpoch,
            discontinuity: false,
            samples: samples
        )
    }
}
