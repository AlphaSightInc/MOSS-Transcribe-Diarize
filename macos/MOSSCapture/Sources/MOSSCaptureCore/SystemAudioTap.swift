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
    private var tapID = AudioObjectID(kAudioObjectUnknown)
    private var aggregateDeviceID = AudioObjectID(kAudioObjectUnknown)
    private var ioProcID: AudioDeviceIOProcID?

    public init(sampleRate: Int = 48_000, deviceEpoch: UInt64 = 0) {
        self.sampleRate = sampleRate
        self.deviceEpoch = deviceEpoch
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

    @available(macOS 14.2, *)
    public func start(queue: RealTimeNativeAudioBufferQueue) throws {
        let description = makeTapDescription()
        var createdTapID = AudioObjectID(kAudioObjectUnknown)
        let tapStatus = AudioHardwareCreateProcessTap(description, &createdTapID)
        guard tapStatus == noErr else {
            throw NativeCaptureError.osStatus("AudioHardwareCreateProcessTap", tapStatus)
        }
        tapID = createdTapID
        aggregateDeviceID = try createTransientAggregateDevice(for: description)
        try installHALCallback(on: aggregateDeviceID, queue: queue)
    }

    public func stop() {
        if let ioProcID {
            AudioDeviceDestroyIOProcID(aggregateDeviceID, ioProcID)
            self.ioProcID = nil
        }
        if aggregateDeviceID != AudioObjectID(kAudioObjectUnknown) {
            AudioHardwareDestroyAggregateDevice(aggregateDeviceID)
            aggregateDeviceID = AudioObjectID(kAudioObjectUnknown)
        }
        if tapID != AudioObjectID(kAudioObjectUnknown) {
            if #available(macOS 14.2, *) {
                AudioHardwareDestroyProcessTap(tapID)
            }
            tapID = AudioObjectID(kAudioObjectUnknown)
        }
    }

    private func createTransientAggregateDevice(for description: CATapDescription) throws -> AudioObjectID {
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

    private func installHALCallback(
        on aggregateDeviceID: AudioObjectID,
        queue: RealTimeNativeAudioBufferQueue
    ) throws {
        var createdIOProcID: AudioDeviceIOProcID?
        let sampleRate = self.sampleRate
        let deviceEpoch = self.deviceEpoch
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
