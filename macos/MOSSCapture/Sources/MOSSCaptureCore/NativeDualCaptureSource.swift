import Foundation

protocol NativeAudioCaptureComponent: AnyObject {
    func start(queue: RealTimeNativeAudioBufferQueue) throws
    func stop()
}

protocol NativeLaneHealthReportingComponent: AnyObject {
    func attachHealthSink(_ sink: NativeLaneHealthFactSink, lane: CaptureLane, generation: UInt64)
}

/// A lane that publishes an explicit, asynchronous permission request of its own.
///
/// Both members must return immediately: `authorization()` is a status read that never touches
/// capture hardware, and `requestAuthorization` starts the single user-facing transition and
/// delivers the answer later, on an arbitrary thread. A lane without such an API resolves its
/// permission through its recording start instead — see `SystemAudioPermission`.
protocol NativeLanePermissionRequesting: AnyObject {
    func authorization() -> NativeLanePermissionFact
    func requestAuthorization(_ completion: @escaping @Sendable (NativeLanePermissionFact) -> Void)
}

extension SystemAudioTap: NativeAudioCaptureComponent {}
extension SystemAudioTap: NativeLaneHealthReportingComponent {}
extension MicrophoneCapture: NativeAudioCaptureComponent {}
extension MicrophoneCapture: NativeLaneHealthReportingComponent {}
extension MicrophoneCapture: NativeLanePermissionRequesting {}

/// A lane identifier is a plain `String` enum with no payload and no mutable state; the
/// conformance lets one travel with a permission answer that comes back on whatever thread macOS
/// chooses. It is `@unchecked` only because the case-carrying declaration lives in another file.
extension CaptureLane: @unchecked Sendable {}

/// Where one lane's recording permission stands within the current capture generation.
enum NativeLanePermissionState: String, Equatable {
    /// One user-initiated request is outstanding: the lane is neither admitted nor failed, and
    /// the control loop must stay responsive for as long as the prompt is on screen.
    case pending
    case granted
    case denied
}

/// The outcome of trying to admit one lane during a user `start`.
enum NativeLaneAdmission {
    case capturing
    case awaitingPermission
    case failed(Error)
}

/// Owns the per-lane recording permission of the running capture generation.
///
/// The two lanes resolve permission through different macOS mechanisms — the microphone through
/// an explicit `AVCaptureDevice.requestAccess` transition, system audio through the user-initiated
/// recording start described by `SystemAudioPermission` — so state is kept per lane and never
/// collapsed into one process-wide answer. Every asynchronous answer carries the generation that
/// asked for it: an answer from a retired generation is dropped, so a grant that lands after
/// `stop`, or behind a `start` that admitted nothing, can neither begin capture nor change
/// reported status.
final class NativeLanePermissionCoordinator: @unchecked Sendable {
    private let lock = NSLock()
    private var generation: UInt64 = 0
    private var states: [CaptureLane: NativeLanePermissionState] = [:]

    /// Capture generations are 1-based, so zero means "no live generation" after `retire()`.
    func beginGeneration(_ generation: UInt64) {
        lock.lock()
        self.generation = generation
        states.removeAll(keepingCapacity: true)
        lock.unlock()
    }

    func retire() {
        lock.lock()
        generation = 0
        states.removeAll(keepingCapacity: true)
        lock.unlock()
    }

    func state(for lane: CaptureLane) -> NativeLanePermissionState? {
        lock.lock()
        defer { lock.unlock() }
        return states[lane]
    }

    func record(_ state: NativeLanePermissionState, for lane: CaptureLane, generation: UInt64) {
        lock.lock()
        if generation == self.generation {
            states[lane] = state
        }
        lock.unlock()
    }

    /// Issues the single user-initiated request for `lane`. A duplicate `start` inside the same
    /// generation finds the lane already pending and prompts no second time.
    func request(
        lane: CaptureLane,
        generation: UInt64,
        gate: NativeLanePermissionRequesting,
        answer: @escaping @Sendable (NativeLanePermissionFact) -> Void
    ) {
        lock.lock()
        guard generation == self.generation, states[lane] == nil else {
            lock.unlock()
            return
        }
        states[lane] = .pending
        lock.unlock()

        gate.requestAuthorization { [weak self] decision in
            guard let self else {
                return
            }
            self.lock.lock()
            let live = generation == self.generation && self.states[lane] == .pending
            if live {
                self.states[lane] = decision == .granted ? .granted : .denied
            }
            self.lock.unlock()
            guard live else {
                return
            }
            answer(decision)
        }
    }
}

/// Every mutable field below is guarded by `lock`, so the source is safe to touch from both the
/// control loop and a permission answer delivered on an arbitrary thread.
public final class NativeDualCaptureSource: CaptureSourceAdapter, @unchecked Sendable {
    private let lock = NSLock()
    private let system: NativeAudioCaptureComponent
    private let microphone: NativeAudioCaptureComponent
    private let queue: RealTimeNativeAudioBufferQueue
    private let emitter: NativeLaneFrameEmitter
    private let health = NativeLaneHealth()
    private let permissions = NativeLanePermissionCoordinator()
    private var started = false
    private var activeGeneration: UInt64?
    private var reportedDroppedBuffers: [CaptureLane: UInt64] = [:]
    private var latestFrames: [CaptureLane: CaptureFrame] = [:]
    private var admissions: [CaptureLane: NativeLaneAdmission] = [:]

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
        lock.lock()
        let alreadyStarted = started
        lock.unlock()
        guard !alreadyStarted else {
            // A duplicate `start` adopts the running generation; it must never prompt the user
            // for a lane a second time or restart a lane that is already capturing.
            return
        }

        let generation = health.beginGeneration()
        permissions.beginGeneration(generation)
        lock.lock()
        latestFrames.removeAll(keepingCapacity: true)
        admissions.removeAll(keepingCapacity: true)
        activeGeneration = generation
        reportedDroppedBuffers.removeAll(keepingCapacity: true)
        started = true
        lock.unlock()

        attachHealthSink(to: system, lane: .system, generation: generation)
        attachHealthSink(to: microphone, lane: .microphone, generation: generation)

        let systemAdmission = admitSystemAudio(generation: generation)
        let microphoneAdmission = admitMicrophone(generation: generation)
        let capturing = [systemAdmission, microphoneAdmission].contains {
            if case .capturing = $0 { return true }
            return false
        }

        guard capturing else {
            // Nothing is recording. Retire the permission generation before teardown so an answer
            // that lands after this failure cannot start a lane behind a `start` that threw. The
            // health generation stays live: `status` must still explain why each lane failed.
            permissions.retire()
            system.stop()
            microphone.stop()
            lock.lock()
            started = false
            activeGeneration = nil
            lock.unlock()
            throw startFailure(system: systemAdmission, microphone: microphoneAdmission)
        }
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
            var state = isStarted && status.state == "stopped" ? "recovering" : status.state
            if status.failureCode == nil, permissions.state(for: status.lane) == .pending {
                // The user has not answered this lane's prompt yet. That is neither a failure nor
                // a recovery: the lane joins the running capture if and when the answer grants it.
                state = NativeLanePermissionState.pending.rawValue
            }
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
        // Retire the permission generation before any teardown so an answer that arrives during or
        // after `stop` — including a grant the user gives to a prompt that is still on screen —
        // cannot restart a lane.
        permissions.retire()
        health.invalidateGeneration()
        microphone.stop()
        system.stop()
        lock.lock()
        started = false
        activeGeneration = nil
        admissions.removeAll(keepingCapacity: true)
        lock.unlock()
    }

    /// System Audio Recording has no request API of its own, so the user-initiated recording start
    /// performed here is both the request and the admission; this lane never sits pending.
    private func admitSystemAudio(generation: UInt64) -> NativeLaneAdmission {
        let admission = admit(system, lane: .system, generation: generation)
        var startError: Error?
        if case .failed(let error) = admission {
            startError = error
        }
        if let state = SystemAudioPermission.state(afterRecordingStart: startError) {
            permissions.record(state, for: .system, generation: generation)
        }
        return admission
    }

    /// The microphone publishes an explicit request, so an undetermined lane is asked — never
    /// started. Starting it first would touch `AVAudioEngine.inputNode` behind an unanswered
    /// prompt and block the control loop indefinitely.
    private func admitMicrophone(generation: UInt64) -> NativeLaneAdmission {
        guard let gate = microphone as? NativeLanePermissionRequesting else {
            return admit(microphone, lane: .microphone, generation: generation)
        }
        let authorization = gate.authorization()
        health.enqueue(.permission(authorization), lane: .microphone, generation: generation)
        switch authorization {
        case .granted:
            permissions.record(.granted, for: .microphone, generation: generation)
            return admit(microphone, lane: .microphone, generation: generation)
        case .denied:
            permissions.record(.denied, for: .microphone, generation: generation)
            return fail(
                NativeCaptureError.permissionDenied("microphone"),
                lane: .microphone,
                generation: generation
            )
        case .undetermined:
            permissions.request(
                lane: .microphone,
                generation: generation,
                gate: gate
            ) { [weak self] decision in
                self?.resolveMicrophonePermission(decision, generation: generation)
            }
            // An answer that arrives before `requestAuthorization` returns has already admitted or
            // failed the lane; otherwise the lane is pending and `start` must not wait for it.
            return recordedAdmission(for: .microphone) ?? .awaitingPermission
        }
    }

    private func resolveMicrophonePermission(
        _ decision: NativeLanePermissionFact,
        generation: UInt64
    ) {
        health.enqueue(.permission(decision), lane: .microphone, generation: generation)
        guard isLive(generation: generation) else {
            return
        }
        guard decision == .granted else {
            _ = fail(
                NativeCaptureError.permissionDenied("microphone"),
                lane: .microphone,
                generation: generation
            )
            return
        }
        _ = admit(microphone, lane: .microphone, generation: generation)
    }

    private func startFailure(
        system: NativeLaneAdmission,
        microphone: NativeLaneAdmission
    ) -> Error {
        // A lane still waiting on the user is the actionable reason: the operator answers the
        // prompt and starts again. Report it ahead of another lane's incidental device error.
        for (lane, admission) in [(CaptureLane.system, system), (CaptureLane.microphone, microphone)] {
            if case .awaitingPermission = admission {
                return NativeCaptureError.permissionDenied("\(lane.rawValue) permission not granted yet")
            }
        }
        for admission in [system, microphone] {
            if case .failed(let error) = admission {
                return error
            }
        }
        return NativeCaptureError.deviceUnavailable("no native lanes admitted")
    }

    private func attachHealthSink(
        to component: NativeAudioCaptureComponent,
        lane: CaptureLane,
        generation: UInt64
    ) {
        (component as? NativeLaneHealthReportingComponent)?
            .attachHealthSink(health, lane: lane, generation: generation)
    }

    private func admit(
        _ component: NativeAudioCaptureComponent,
        lane: CaptureLane,
        generation: UInt64
    ) -> NativeLaneAdmission {
        do {
            try component.start(queue: queue)
            health.enqueue(.admitted, lane: lane, generation: generation)
            return record(.capturing, for: lane)
        } catch {
            return fail(error, lane: lane, generation: generation)
        }
    }

    private func fail(
        _ error: Error,
        lane: CaptureLane,
        generation: UInt64
    ) -> NativeLaneAdmission {
        if let nativeError = error as? NativeCaptureError {
            health.enqueue(.startFailed(nativeError), lane: lane, generation: generation)
        } else {
            health.enqueue(.unexpectedCaptureError(String(describing: error)), lane: lane, generation: generation)
        }
        return record(.failed(error), for: lane)
    }

    @discardableResult
    private func record(_ admission: NativeLaneAdmission, for lane: CaptureLane) -> NativeLaneAdmission {
        lock.lock()
        admissions[lane] = admission
        lock.unlock()
        return admission
    }

    private func recordedAdmission(for lane: CaptureLane) -> NativeLaneAdmission? {
        lock.lock()
        defer { lock.unlock() }
        return admissions[lane]
    }

    private func isLive(generation: UInt64) -> Bool {
        lock.lock()
        defer { lock.unlock() }
        return started && activeGeneration == generation
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
