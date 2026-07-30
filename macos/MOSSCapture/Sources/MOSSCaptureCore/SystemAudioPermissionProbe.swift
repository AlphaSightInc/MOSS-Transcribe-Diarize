import AVFAudio
import CoreAudio
import Foundation

protocol SystemAudioPermissionProbing: AnyObject {
    func request(
        _ completion: @escaping @Sendable (
            Result<NativeLanePermissionFact, NativeCaptureError>
        ) -> Void
    )
    func cancel()
}

protocol SystemAudioPermissionProbeDriving: AnyObject {
    func measure(cancelled: @escaping @Sendable () -> Bool) throws -> Bool
}

/// Runs the blocking Core Audio permission transition away from the app's control loop.
///
/// A generation ticket suppresses a result that arrives after stop. The driver still unwinds its
/// Core Audio resources if macOS is blocked on a permission prompt when cancellation occurs.
final class SystemAudioPermissionProbe: SystemAudioPermissionProbing, @unchecked Sendable {
    private let lock = NSLock()
    private let driver: SystemAudioPermissionProbeDriving
    private let queue: DispatchQueue
    private var generation: UInt64 = 0

    convenience init() {
        self.init(
            driver: CoreAudioSystemAudioPermissionProbeDriver(),
            queue: DispatchQueue(label: "moss.capture.system-audio-permission")
        )
    }

    init(driver: SystemAudioPermissionProbeDriving, queue: DispatchQueue) {
        self.driver = driver
        self.queue = queue
    }

    func request(
        _ completion: @escaping @Sendable (
            Result<NativeLanePermissionFact, NativeCaptureError>
        ) -> Void
    ) {
        lock.lock()
        generation += 1
        let requestGeneration = generation
        lock.unlock()

        queue.async { [weak self] in
            guard let self else { return }
            let outcome: Result<NativeLanePermissionFact, NativeCaptureError>
            do {
                let signalObserved = try self.driver.measure {
                    self.isCancelled(requestGeneration)
                }
                outcome = .success(signalObserved ? .granted : .denied)
            } catch let error as NativeCaptureError {
                outcome = .failure(error)
            } catch {
                outcome = .failure(
                    .deviceUnavailable("system audio permission probe: \(error)")
                )
            }
            guard self.finish(requestGeneration) else { return }
            completion(outcome)
        }
    }

    func cancel() {
        lock.lock()
        generation += 1
        lock.unlock()
    }

    private func isCancelled(_ requestGeneration: UInt64) -> Bool {
        lock.lock()
        defer { lock.unlock() }
        return generation != requestGeneration
    }

    private func finish(_ requestGeneration: UInt64) -> Bool {
        lock.lock()
        defer { lock.unlock() }
        guard generation == requestGeneration else { return false }
        generation += 1
        return true
    }
}

/// The child mode of the app executable used by the permission probe.
///
/// It connects to Core Audio first, waits for the parent to install a process-specific muted tap,
/// then emits a deterministic tone. The tone never enters the production capture queue.
public enum SystemAudioPermissionSignal {
    public static let commandArgument = "--moss-system-audio-permission-probe"

    public static func run() throws {
        let engine = AVAudioEngine()
        let player = AVAudioPlayerNode()
        engine.attach(player)
        let format = engine.outputNode.outputFormat(forBus: 0)
        guard format.sampleRate > 0, format.channelCount > 0 else {
            throw NativeCaptureError.deviceUnavailable(
                "system audio permission probe has no output format"
            )
        }
        engine.connect(player, to: engine.mainMixerNode, format: format)
        engine.prepare()
        do {
            try engine.start()
        } catch {
            throw NativeCaptureError.deviceUnavailable(
                "system audio permission probe output could not start"
            )
        }

        let frameCount = AVAudioFrameCount(format.sampleRate)
        guard let buffer = AVAudioPCMBuffer(
            pcmFormat: format,
            frameCapacity: frameCount
        ), let channels = buffer.floatChannelData else {
            engine.stop()
            throw NativeCaptureError.deviceUnavailable(
                "system audio permission probe buffer allocation failed"
            )
        }
        buffer.frameLength = frameCount
        for channel in 0..<Int(format.channelCount) {
            for frame in 0..<Int(frameCount) {
                channels[channel][frame] =
                    0.03 * sin(2 * .pi * 997 * Float(frame) / Float(format.sampleRate))
            }
        }

        Thread.sleep(forTimeInterval: 1.2)
        player.scheduleBuffer(buffer)
        player.play()
        Thread.sleep(forTimeInterval: 1.3)
        player.stop()
        engine.stop()
    }
}

private final class CoreAudioSystemAudioPermissionProbeDriver:
    SystemAudioPermissionProbeDriving
{
    private let helperExecutable: () throws -> URL

    init(
        helperExecutable: @escaping () throws -> URL = {
            guard let executable = Bundle.main.executableURL else {
                throw NativeCaptureError.deviceUnavailable(
                    "system audio permission probe helper is missing"
                )
            }
            return executable
        }
    ) {
        self.helperExecutable = helperExecutable
    }

    func measure(cancelled: @escaping @Sendable () -> Bool) throws -> Bool {
        guard #available(macOS 14.2, *) else {
            throw NativeCaptureError.unavailable("macOS 14.2 process taps required")
        }

        let observation = SystemAudioPermissionProbeObservation()
        let globalDescription = CATapDescription()
        globalDescription.name = "MOSS System Audio Permission Probe"
        globalDescription.uuid = UUID()
        globalDescription.isPrivate = true
        globalDescription.isMixdown = true
        globalDescription.isMono = false
        globalDescription.isExclusive = true
        globalDescription.muteBehavior = .unmuted
        let globalTap = try SystemAudioPermissionProbeTap(
            description: globalDescription,
            observation: observation
        )
        guard !cancelled() else { return false }

        let helper = Process()
        helper.executableURL = try helperExecutable()
        helper.arguments = [SystemAudioPermissionSignal.commandArgument]
        do {
            try helper.run()
        } catch {
            throw NativeCaptureError.deviceUnavailable(
                "system audio permission probe helper could not start"
            )
        }
        defer {
            if helper.isRunning {
                helper.terminate()
                helper.waitUntilExit()
            }
        }

        let processObject = try waitForProcessAudioObject(
            pid: helper.processIdentifier,
            cancelled: cancelled
        )
        let muteDescription = CATapDescription(
            stereoMixdownOfProcesses: [processObject]
        )
        muteDescription.name = "MOSS System Audio Permission Probe Mute"
        muteDescription.uuid = UUID()
        muteDescription.isPrivate = true
        muteDescription.muteBehavior = .muted
        let muteTap = try SystemAudioPermissionProbeTap(
            description: muteDescription,
            observation: nil
        )

        let exitDeadline = Date().addingTimeInterval(5)
        while helper.isRunning, !cancelled(), Date() < exitDeadline {
            Thread.sleep(forTimeInterval: 0.01)
        }
        if cancelled() {
            return false
        }
        guard !helper.isRunning else {
            throw NativeCaptureError.deviceUnavailable(
                "system audio permission probe helper timed out"
            )
        }
        guard helper.terminationStatus == 0 else {
            throw NativeCaptureError.deviceUnavailable(
                "system audio permission probe helper failed"
            )
        }
        Thread.sleep(forTimeInterval: 0.2)
        return withExtendedLifetime((globalTap, muteTap)) {
            observation.signalObserved()
        }
    }

    private func waitForProcessAudioObject(
        pid: pid_t,
        cancelled: @escaping @Sendable () -> Bool
    ) throws -> AudioObjectID {
        let deadline = Date().addingTimeInterval(1)
        while !cancelled(), Date() < deadline {
            let objectID = try processAudioObject(pid: pid)
            if objectID != AudioObjectID(kAudioObjectUnknown) {
                return objectID
            }
            Thread.sleep(forTimeInterval: 0.01)
        }
        throw NativeCaptureError.deviceUnavailable(
            "system audio permission probe helper did not register with Core Audio"
        )
    }

    private func processAudioObject(pid: pid_t) throws -> AudioObjectID {
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyTranslatePIDToProcessObject,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        var requestedPID = pid
        var processObject = AudioObjectID(kAudioObjectUnknown)
        var outputSize = UInt32(MemoryLayout<AudioObjectID>.size)
        let status = withUnsafePointer(to: &requestedPID) { qualifier in
            AudioObjectGetPropertyData(
                AudioObjectID(kAudioObjectSystemObject),
                &address,
                UInt32(MemoryLayout<pid_t>.size),
                qualifier,
                &outputSize,
                &processObject
            )
        }
        guard status == noErr else {
            throw NativeCaptureError.osStatus(
                "kAudioHardwarePropertyTranslatePIDToProcessObject",
                status
            )
        }
        return processObject
    }
}

private final class SystemAudioPermissionProbeObservation: @unchecked Sendable {
    private let lock = NSLock()
    private var observed = false

    func observe(_ inputData: UnsafePointer<AudioBufferList>?) {
        lock.lock()
        defer { lock.unlock() }
        guard !observed, let inputData else { return }
        withUnsafePointer(to: inputData.pointee.mBuffers) { firstBuffer in
            let buffers = UnsafeBufferPointer(
                start: firstBuffer,
                count: Int(inputData.pointee.mNumberBuffers)
            )
            for buffer in buffers {
                guard let data = buffer.mData else { continue }
                let count = Int(buffer.mDataByteSize) / MemoryLayout<Float>.stride
                let samples = data.assumingMemoryBound(to: Float.self)
                if UnsafeBufferPointer(start: samples, count: count).contains(where: { $0 != 0 }) {
                    observed = true
                    return
                }
            }
        }
    }

    func signalObserved() -> Bool {
        lock.lock()
        defer { lock.unlock() }
        return observed
    }
}

private final class SystemAudioPermissionProbeTap {
    private var tapID = AudioObjectID(kAudioObjectUnknown)
    private var aggregateDeviceID = AudioObjectID(kAudioObjectUnknown)
    private var ioProcID: AudioDeviceIOProcID?
    private var started = false

    init(
        description: CATapDescription,
        observation: SystemAudioPermissionProbeObservation?
    ) throws {
        guard #available(macOS 14.2, *) else {
            throw NativeCaptureError.unavailable("macOS 14.2 process taps required")
        }
        do {
            var createdTapID = AudioObjectID(kAudioObjectUnknown)
            var status = AudioHardwareCreateProcessTap(description, &createdTapID)
            guard status == noErr else {
                throw NativeCaptureError.osStatus(
                    "AudioHardwareCreateProcessTap",
                    status
                )
            }
            tapID = createdTapID

            let aggregate: [String: Any] = [
                kAudioAggregateDeviceUIDKey:
                    "moss.permission-probe.\(UUID().uuidString)",
                kAudioAggregateDeviceNameKey: "MOSS Permission Probe Aggregate",
                kAudioAggregateDeviceIsPrivateKey: true,
                kAudioAggregateDeviceIsStackedKey: false,
                kAudioAggregateDeviceTapListKey: [[
                    kAudioSubTapUIDKey: description.uuid.uuidString,
                    kAudioSubTapDriftCompensationKey: true,
                ]],
                kAudioAggregateDeviceTapAutoStartKey: false,
            ]
            status = AudioHardwareCreateAggregateDevice(
                aggregate as CFDictionary,
                &aggregateDeviceID
            )
            guard status == noErr else {
                throw NativeCaptureError.osStatus(
                    "AudioHardwareCreateAggregateDevice",
                    status
                )
            }

            status = AudioDeviceCreateIOProcIDWithBlock(
                &ioProcID,
                aggregateDeviceID,
                nil
            ) { _, inputData, _, _, _ in
                observation?.observe(inputData)
            }
            guard status == noErr else {
                throw NativeCaptureError.osStatus(
                    "AudioDeviceCreateIOProcIDWithBlock",
                    status
                )
            }
            status = AudioDeviceStart(aggregateDeviceID, ioProcID)
            guard status == noErr else {
                throw NativeCaptureError.osStatus("AudioDeviceStart", status)
            }
            started = true
        } catch {
            stop()
            throw error
        }
    }

    deinit {
        stop()
    }

    private func stop() {
        if started {
            _ = AudioDeviceStop(aggregateDeviceID, ioProcID)
            started = false
        }
        if let ioProcID {
            _ = AudioDeviceDestroyIOProcID(aggregateDeviceID, ioProcID)
            self.ioProcID = nil
        }
        if aggregateDeviceID != AudioObjectID(kAudioObjectUnknown) {
            _ = AudioHardwareDestroyAggregateDevice(aggregateDeviceID)
            aggregateDeviceID = AudioObjectID(kAudioObjectUnknown)
        }
        if tapID != AudioObjectID(kAudioObjectUnknown) {
            if #available(macOS 14.2, *) {
                _ = AudioHardwareDestroyProcessTap(tapID)
            }
            tapID = AudioObjectID(kAudioObjectUnknown)
        }
    }
}
