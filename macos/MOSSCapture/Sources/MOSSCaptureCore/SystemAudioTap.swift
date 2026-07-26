import CoreAudio
import Foundation

public struct SystemAudioTapSourceVector: Equatable, Sendable {
    public var tapDescription: String
    public var processTapFunction: String
    public var aggregateDevice: String
    public var halCallbackFunction: String
    public var realtimeCallbackWork: [String]
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

public final class SystemAudioTap {
    public static let sourceVector = SystemAudioTapSourceVector(
        tapDescription: "private unmuted CATapDescription",
        processTapFunction: "AudioHardwareCreateProcessTap",
        aggregateDevice: "private transient aggregate",
        halCallbackFunction: "AudioDeviceCreateIOProcIDWithBlock",
        realtimeCallbackWork: ["copy native buffer", "enqueue monotonic first-sample time"]
    )

    private let sampleRate: Int
    private let deviceEpoch: UInt64
    private let driver: SystemAudioTapDriver
    private var tapID = AudioObjectID(kAudioObjectUnknown)
    private var aggregateDeviceID = AudioObjectID(kAudioObjectUnknown)
    private var ioProcInstalled = false
    private var ioStarted = false

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

    public func start(queue: RealTimeNativeAudioBufferQueue) throws {
        let description = makeTapDescription()
        do {
            tapID = try driver.createProcessTap(description: description)
            aggregateDeviceID = try driver.createAggregateDevice(for: description)
            try driver.createIOProc(
                on: aggregateDeviceID,
                queue: queue,
                sampleRate: sampleRate,
                deviceEpoch: deviceEpoch
            )
            ioProcInstalled = true
            try driver.startDevice(aggregateDeviceID)
            ioStarted = true
        } catch {
            stop()
            throw error
        }
    }

    public func stop() {
        if ioStarted {
            driver.stopDevice(aggregateDeviceID)
            ioStarted = false
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
    }
}

private final class CoreAudioSystemTapDriver: SystemAudioTapDriver {
    private var ioProcID: AudioDeviceIOProcID?

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

        return NativeCapturedAudioBuffer(
            lane: lane,
            sampleRate: sampleRate,
            channelCount: Swift.max(channelCount, 1),
            frameCount: frameCount,
            firstSampleMonotonicNS: inputTime?.pointee.mHostTime ?? 0,
            deviceEpoch: deviceEpoch,
            discontinuity: false,
            samples: samples
        )
    }
}
