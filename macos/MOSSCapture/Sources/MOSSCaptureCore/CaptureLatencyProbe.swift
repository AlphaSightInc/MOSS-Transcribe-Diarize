import CoreAudio
import Foundation

/// How the app measures user-visible latency.
///
/// `LiveServiceEvent` carries no timestamp and the server cannot compare its clock with the Mac's,
/// so the only place the measurement can be made on one clock is inside the app, where the capture
/// instants, the polling and the view authority already live. The probe therefore stays here and
/// exposes aggregates only: the CLI asks for the measurement and never receives the token.
public enum CaptureLatencyContract {
    /// How often the probe asks the server how much audio it has committed. Four times the wire
    /// frame period, so an advance is attributed to within one poll rather than to within one frame.
    public static let pollInterval: TimeInterval = 0.25

    /// The portal fetches snapshot then events serially and schedules the next cycle this long
    /// after both complete, so committed text waits at most one cycle plus both fetches before it
    /// is on screen. That is the analytic half of the gated number.
    ///
    /// This is a **restatement** of the server's `pollDelayMs` in `live_portal.py`, not an
    /// independent knob: the app never schedules anything from it, so moving it alone would move a
    /// gated number without changing what any reader waits. The two are asserted equal from both
    /// sides — `testPortalCycleContractMatchesTheServedPortalCadence` here and
    /// `test_live_portal_poll_cadence_and_the_app_render_bound_are_one_number` in the Python suite.
    public static let portalCycleSeconds: Double = 0.5

    /// Fewer advances than this is a sample, not a distribution. The report says so instead of
    /// quoting a p95 nobody should trust.
    public static let minimumCommittedAdvances = 20

    static let wire = NativeLaneWireFormat.live

    /// The wire rate divides one second exactly, so a committed sample count maps to a capture
    /// instant with no rounding: the mapping contributes no error of its own to the measurement.
    static let nanosecondsPerCommittedSample = UInt64(1_000_000_000) / UInt64(wire.sampleRate)

    /// The measurement can only resolve an advance to the audio that closed it, so every figure
    /// carries this much quantisation. Reported next to the percentiles rather than subtracted.
    public static var frameQuantisationMS: Double {
        Double(wire.frameDurationNS) / 1_000_000
    }
}

/// Reads "now" in the same converted-nanosecond domain the wire frames carry.
///
/// Latency is a subtraction between a capture instant and a later instant, so both readings have to
/// come from one clock; a reading that cannot be converted returns `nil` and the poll is skipped
/// rather than measured against a fabricated time.
public protocol CaptureHostTimeReading {
    func hostNanoseconds() -> UInt64?
}

public struct SystemCaptureHostTimeReader: CaptureHostTimeReading {
    private let converter: MachHostTimeConverting

    public init() {
        self.init(converter: HostTimeNanosecondConverter())
    }

    init(converter: MachHostTimeConverting) {
        self.converter = converter
    }

    public func hostNanoseconds() -> UInt64? {
        converter.nanoseconds(forHostTicks: AudioGetCurrentHostTime())
    }
}

/// A distribution of observed durations, in milliseconds. Counts and numbers only — this is what
/// leaves the app.
public struct CaptureLatencyDistribution: Codable, Equatable, Sendable {
    public var count: Int
    public var p50MS: Double?
    public var p95MS: Double?
    public var maxMS: Double?

    public init(
        count: Int = 0,
        p50MS: Double? = nil,
        p95MS: Double? = nil,
        maxMS: Double? = nil
    ) {
        self.count = count
        self.p50MS = p50MS
        self.p95MS = p95MS
        self.maxMS = maxMS
    }

    /// Nearest-rank percentiles: no interpolation, so a reported figure is always a value that was
    /// actually observed and a small sample cannot be smoothed into looking better than it was.
    static func over(_ nanoseconds: [UInt64]) -> CaptureLatencyDistribution {
        let sorted = nanoseconds.sorted()
        return CaptureLatencyDistribution(
            count: sorted.count,
            p50MS: milliseconds(percentile(sorted, 0.50)),
            p95MS: milliseconds(percentile(sorted, 0.95)),
            maxMS: milliseconds(sorted.last)
        )
    }

    private static func percentile(_ sorted: [UInt64], _ fraction: Double) -> UInt64? {
        guard !sorted.isEmpty else {
            return nil
        }
        let rank = Int((fraction * Double(sorted.count)).rounded(.up))
        return sorted[min(max(rank, 1), sorted.count) - 1]
    }

    private static func milliseconds(_ nanoseconds: UInt64?) -> Double? {
        nanoseconds.map { Double($0) / 1_000_000 }
    }
}

/// Everything the measurement is allowed to emit.
///
/// Every field is a count, a flag or a duration. There is no transcript, no URL, no session
/// identifier and above all no token, so the report cannot leak view authority by construction
/// rather than by review.
public struct CaptureLatencyReport: Codable, Equatable, Sendable {
    public static let schemaName = "moss-capture-latency.v1"

    public var schema: String
    public var polling: Bool
    public var mixerOriginResolved: Bool
    public var timelineIntact: Bool
    public var sufficientSamples: Bool
    public var committedLatency: CaptureLatencyDistribution
    public var snapshotFetch: CaptureLatencyDistribution
    public var eventsFetch: CaptureLatencyDistribution
    public var frameQuantisationMS: Double
    public var portalCycleMS: Double
    /// `portal cycle + snapshot p95 + events p95` — nil until both routes have been measured.
    public var renderBoundMS: Double?
    /// The gated number: committed p95 plus the render bound. Both components stay in the report.
    public var userVisibleMS: Double?
    public var rejectedNegative: Int
    public var rejectedClockRegression: Int
    public var rejectedAfterTimelineBreak: Int
    public var fetchFailures: Int

    public init(
        schema: String = CaptureLatencyReport.schemaName,
        polling: Bool = false,
        mixerOriginResolved: Bool = false,
        timelineIntact: Bool = true,
        sufficientSamples: Bool = false,
        committedLatency: CaptureLatencyDistribution = CaptureLatencyDistribution(),
        snapshotFetch: CaptureLatencyDistribution = CaptureLatencyDistribution(),
        eventsFetch: CaptureLatencyDistribution = CaptureLatencyDistribution(),
        frameQuantisationMS: Double = CaptureLatencyContract.frameQuantisationMS,
        portalCycleMS: Double = CaptureLatencyContract.portalCycleSeconds * 1_000,
        renderBoundMS: Double? = nil,
        userVisibleMS: Double? = nil,
        rejectedNegative: Int = 0,
        rejectedClockRegression: Int = 0,
        rejectedAfterTimelineBreak: Int = 0,
        fetchFailures: Int = 0
    ) {
        self.schema = schema
        self.polling = polling
        self.mixerOriginResolved = mixerOriginResolved
        self.timelineIntact = timelineIntact
        self.sufficientSamples = sufficientSamples
        self.committedLatency = committedLatency
        self.snapshotFetch = snapshotFetch
        self.eventsFetch = eventsFetch
        self.frameQuantisationMS = frameQuantisationMS
        self.portalCycleMS = portalCycleMS
        self.renderBoundMS = renderBoundMS
        self.userVisibleMS = userVisibleMS
        self.rejectedNegative = rejectedNegative
        self.rejectedClockRegression = rejectedClockRegression
        self.rejectedAfterTimelineBreak = rejectedAfterTimelineBreak
        self.fetchFailures = fetchFailures
    }
}

/// The latency arithmetic, with no network and no clock of its own.
///
/// It holds two things the server cannot tell the Mac: which capture instant the mixer's timeline
/// starts from, and whether that timeline is still intact. Everything else is a subtraction.
public final class CaptureLatencySampler: CaptureAcknowledgedFrameObserving, @unchecked Sendable {
    private let lock = NSLock()
    private var firstCaptureNSByLane: [CaptureLane: UInt64] = [:]
    private var shortFrameByLane: [CaptureLane: Bool] = [:]
    private var contributingLanes: Set<CaptureLane> = []
    private var mixerOriginNS: UInt64?
    private var timelineIntact = true
    private var lastCommittedSamples: Int?
    private var lastObservedNS: UInt64?
    private var committedLatencyNS: [UInt64] = []
    private var snapshotFetchNS: [UInt64] = []
    private var eventsFetchNS: [UInt64] = []
    private var rejectedNegative = 0
    private var rejectedClockRegression = 0
    private var rejectedAfterTimelineBreak = 0
    private var fetchFailures = 0

    public init() {}

    /// A server session numbers its samples from zero and mixes a fresh timeline, so the previous
    /// session's origin and figures describe nothing here.
    public func observeSessionStart() {
        lock.lock()
        firstCaptureNSByLane = [:]
        shortFrameByLane = [:]
        contributingLanes = []
        mixerOriginNS = nil
        timelineIntact = true
        lastCommittedSamples = nil
        lastObservedNS = nil
        committedLatencyNS = []
        snapshotFetchNS = []
        eventsFetchNS = []
        rejectedNegative = 0
        rejectedClockRegression = 0
        rejectedAfterTimelineBreak = 0
        fetchFailures = 0
        lock.unlock()
    }

    public func observeAcknowledgedFrame(
        lane: CaptureLane,
        captureTimestampNS: UInt64,
        sampleRate: Int,
        sampleCount: Int,
        discontinuity: Bool
    ) {
        lock.lock()
        defer { lock.unlock() }

        // A lane whose previous frame was short and which then produced another frame did not end
        // its stream there: the short frame is a hole in the middle of the timeline, not the
        // meeting's trailing partial. A trailing partial never gets a successor and never taints.
        if shortFrameByLane[lane] == true {
            timelineIntact = false
        }
        shortFrameByLane[lane] = sampleCount < CaptureLatencyContract.wire.frameSamples
        if discontinuity
            || sampleRate != CaptureLatencyContract.wire.sampleRate
            || sampleCount > CaptureLatencyContract.wire.frameSamples
        {
            timelineIntact = false
        }
        guard captureTimestampNS != 0 else {
            return
        }
        if firstCaptureNSByLane[lane] == nil {
            firstCaptureNSByLane[lane] = captureTimestampNS
        }
    }

    /// Which lanes the mixer is still waiting for. A lane the source has failed is excluded exactly
    /// as the server excludes a failed lane, so a denied system-audio run still resolves an origin
    /// from the lane that is really capturing.
    public func noteLaneStates(_ lanes: [CaptureLaneStatus]) {
        lock.lock()
        contributingLanes = Set(
            lanes
                .filter { $0.failureCode == nil && $0.state != "stopped" }
                .map(\.lane)
        )
        lock.unlock()
    }

    /// Records one observation of the server's committed sample count, taken at `now` on the
    /// capture clock.
    public func observe(committedSamples: Int, atHostNanoseconds now: UInt64) {
        lock.lock()
        defer { lock.unlock() }

        resolveOriginLocked()
        guard let origin = mixerOriginNS else {
            return
        }
        guard let previous = lastCommittedSamples else {
            // The first reading has not been seen to advance, so it says nothing about how long the
            // audio took to arrive — it is the baseline the next reading is measured against.
            lastCommittedSamples = committedSamples
            lastObservedNS = now
            return
        }
        guard committedSamples > previous else {
            return
        }
        defer {
            lastCommittedSamples = committedSamples
            lastObservedNS = now
        }
        guard timelineIntact else {
            rejectedAfterTimelineBreak += 1
            return
        }
        if let last = lastObservedNS, now < last {
            rejectedClockRegression += 1
            return
        }
        let committedEndCaptureNS =
            origin + UInt64(committedSamples) * CaptureLatencyContract.nanosecondsPerCommittedSample
        guard now >= committedEndCaptureNS else {
            rejectedNegative += 1
            return
        }
        committedLatencyNS.append(now - committedEndCaptureNS)
    }

    public func recordSnapshotFetch(nanoseconds: UInt64) {
        lock.lock()
        snapshotFetchNS.append(nanoseconds)
        lock.unlock()
    }

    public func recordEventsFetch(nanoseconds: UInt64) {
        lock.lock()
        eventsFetchNS.append(nanoseconds)
        lock.unlock()
    }

    public func recordFetchFailure() {
        lock.lock()
        fetchFailures += 1
        lock.unlock()
    }

    public func report(polling: Bool) -> CaptureLatencyReport {
        lock.lock()
        defer { lock.unlock() }
        resolveOriginLocked()

        let committed = CaptureLatencyDistribution.over(committedLatencyNS)
        let snapshot = CaptureLatencyDistribution.over(snapshotFetchNS)
        let events = CaptureLatencyDistribution.over(eventsFetchNS)
        var renderBoundMS: Double?
        if let snapshotP95 = snapshot.p95MS, let eventsP95 = events.p95MS {
            renderBoundMS = CaptureLatencyContract.portalCycleSeconds * 1_000 + snapshotP95 + eventsP95
        }
        var userVisibleMS: Double?
        if let renderBoundMS, let committedP95 = committed.p95MS {
            userVisibleMS = committedP95 + renderBoundMS
        }
        return CaptureLatencyReport(
            polling: polling,
            mixerOriginResolved: mixerOriginNS != nil,
            timelineIntact: timelineIntact,
            sufficientSamples: committed.count >= CaptureLatencyContract.minimumCommittedAdvances,
            committedLatency: committed,
            snapshotFetch: snapshot,
            eventsFetch: events,
            renderBoundMS: renderBoundMS,
            userVisibleMS: userVisibleMS,
            rejectedNegative: rejectedNegative,
            rejectedClockRegression: rejectedClockRegression,
            rejectedAfterTimelineBreak: rejectedAfterTimelineBreak,
            fetchFailures: fetchFailures
        )
    }

    /// The mixer's timeline starts at the latest first capture instant among the lanes it mixes, and
    /// it does not move afterwards — so this resolves once and then freezes. It waits until every
    /// lane still expected to contribute has produced audio, because resolving early on one lane
    /// would anchor the whole measurement to the wrong instant.
    private func resolveOriginLocked() {
        guard mixerOriginNS == nil else {
            return
        }
        let expected = contributingLanes.isEmpty
            ? Set(firstCaptureNSByLane.keys)
            : contributingLanes
        guard !expected.isEmpty else {
            return
        }
        var origins: [UInt64] = []
        for lane in expected {
            guard let first = firstCaptureNSByLane[lane] else {
                return
            }
            origins.append(first)
        }
        mixerOriginNS = origins.max()
    }
}

/// What the control channel can ask for. Starting the measurement is part of asking for it: nothing
/// polls, and no view authority is read, until an operator requests a figure.
public protocol CaptureLatencyProbing: AnyObject {
    func measure() throws -> CaptureLatencyReport
    func stop()
}

/// Polls the live session with the app's own view authority and turns the answers into aggregates.
///
/// The token is loaded here, put into one request header, and dropped. It is never returned, never
/// placed in a URL, and never written anywhere the CLI can read.
public final class CaptureLatencyProbe: CaptureLatencyProbing, @unchecked Sendable {
    private let sampler: CaptureLatencySampler
    private let status: () -> CaptureStatus
    private let sessionStore: CaptureSessionStoreAdapter
    private let clientProvider: CaptureHTTPClientProvider
    private let certificatePin: CaptureCertificatePinAdapter
    private let clock: CaptureClockAdapter
    private let hostTime: CaptureHostTimeReading
    private let scheduler: CaptureSchedulerAdapter
    private let lock = NSLock()
    private var task: CaptureCancellation?
    private var sinceVersion: Int?
    private var sinceSeq = 0

    public init(
        sampler: CaptureLatencySampler,
        status: @escaping () -> CaptureStatus,
        sessionStore: CaptureSessionStoreAdapter,
        clientProvider: CaptureHTTPClientProvider,
        certificatePin: CaptureCertificatePinAdapter,
        clock: CaptureClockAdapter,
        hostTime: CaptureHostTimeReading = SystemCaptureHostTimeReader(),
        scheduler: CaptureSchedulerAdapter
    ) {
        self.sampler = sampler
        self.status = status
        self.sessionStore = sessionStore
        self.clientProvider = clientProvider
        self.certificatePin = certificatePin
        self.clock = clock
        self.hostTime = hostTime
        self.scheduler = scheduler
    }

    public func measure() throws -> CaptureLatencyReport {
        let current = status()
        lock.lock()
        if current.running, task == nil {
            task = scheduler.schedule(label: "moss.capture.latency") { [weak self] in
                self?.poll()
            }
        }
        let polling = task != nil
        lock.unlock()
        return sampler.report(polling: polling)
    }

    public func stop() {
        lock.lock()
        let task = self.task
        self.task = nil
        lock.unlock()
        task?.cancel()
    }

    private func poll() {
        let current = status()
        sampler.noteLaneStates(current.lanes)
        guard current.running else {
            // View authority dies with the session, so polling on would only accumulate refusals.
            stop()
            return
        }
        guard let session = try? viewSession() else {
            sampler.recordFetchFailure()
            return
        }
        guard let client = try? clientProvider.client(
            certificatePinSHA256Hex: try certificatePin.loadCaptureCertificatePin()
        ) else {
            sampler.recordFetchFailure()
            return
        }

        lock.lock()
        let requestedVersion = sinceVersion
        let requestedSeq = sinceSeq
        lock.unlock()

        guard let snapshot = fetchSnapshot(
            client: client,
            session: session,
            sinceVersion: requestedVersion
        ) else {
            return
        }
        if let observed = snapshot.session {
            lock.lock()
            sinceVersion = observed.version
            lock.unlock()
            if let now = hostTime.hostNanoseconds() {
                sampler.observe(committedSamples: observed.committedSamples, atHostNanoseconds: now)
            }
        }
        // The portal fetches events straight after the snapshot, so the render bound is only honest
        // if both fetches are measured the same way.
        if let highestSeq = fetchEvents(client: client, session: session, sinceSeq: requestedSeq) {
            lock.lock()
            sinceSeq = max(sinceSeq, highestSeq)
            lock.unlock()
        }
    }

    private struct ViewSession {
        var serverURL: URL
        var sessionID: String
        var viewToken: String
    }

    private struct ObservedSession {
        var version: Int
        var committedSamples: Int
    }

    private struct SnapshotObservation {
        var session: ObservedSession?
    }

    private func viewSession() throws -> ViewSession {
        guard let serverURL = try sessionStore.loadCaptureServerURL(),
              let sessionID = try sessionStore.loadCaptureSessionID(),
              !sessionID.isEmpty,
              let viewToken = try sessionStore.loadCaptureViewToken(),
              !viewToken.isEmpty
        else {
            throw CaptureSecurityError.portalHandoffUnavailable
        }
        return ViewSession(serverURL: serverURL, sessionID: sessionID, viewToken: viewToken)
    }

    private func fetchSnapshot(
        client: CaptureHTTPClient,
        session: ViewSession,
        sinceVersion: Int?
    ) -> SnapshotObservation? {
        var query: [URLQueryItem] = []
        if let sinceVersion {
            query.append(URLQueryItem(name: "since_version", value: String(sinceVersion)))
        }
        guard let response = timedFetch(
            client: client,
            session: session,
            action: "snapshot",
            query: query,
            record: sampler.recordSnapshotFetch(nanoseconds:)
        ) else {
            return nil
        }
        guard let payload = try? JSONDecoder().decode(SnapshotEnvelope.self, from: response.body) else {
            return SnapshotObservation(session: nil)
        }
        guard let session = payload.snapshot?.session else {
            // `unchanged` is the steady-state answer once the version stops moving; it is a
            // successful fetch with nothing new to measure.
            return SnapshotObservation(session: nil)
        }
        return SnapshotObservation(
            session: ObservedSession(version: session.version, committedSamples: session.committedSamples)
        )
    }

    private func fetchEvents(
        client: CaptureHTTPClient,
        session: ViewSession,
        sinceSeq: Int
    ) -> Int? {
        guard let response = timedFetch(
            client: client,
            session: session,
            action: "events",
            query: [URLQueryItem(name: "since_seq", value: String(sinceSeq))],
            record: sampler.recordEventsFetch(nanoseconds:)
        ) else {
            return nil
        }
        guard let payload = try? JSONDecoder().decode(EventsEnvelope.self, from: response.body) else {
            return nil
        }
        return payload.events.map(\.seq).max()
    }

    private func timedFetch(
        client: CaptureHTTPClient,
        session: ViewSession,
        action: String,
        query: [URLQueryItem],
        record: (UInt64) -> Void
    ) -> CaptureHTTPResponse? {
        var components = URLComponents(
            url: liveURL(base: session.serverURL, sessionID: session.sessionID, action: action),
            resolvingAgainstBaseURL: false
        )
        if !query.isEmpty {
            components?.queryItems = query
        }
        guard let url = components?.url else {
            sampler.recordFetchFailure()
            return nil
        }
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        // The only place view authority is ever written.
        request.setValue("Bearer \(session.viewToken)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        let started = clock.monotonicNanoseconds()
        guard let response = try? client.send(request) else {
            sampler.recordFetchFailure()
            return nil
        }
        let finished = clock.monotonicNanoseconds()
        guard (200..<300).contains(response.statusCode) else {
            sampler.recordFetchFailure()
            return nil
        }
        record(finished >= started ? finished - started : 0)
        return response
    }
}

private struct SnapshotEnvelope: Decodable {
    struct Snapshot: Decodable {
        struct Session: Decodable {
            var version: Int
            var committedSamples: Int

            enum CodingKeys: String, CodingKey {
                case version
                case committedSamples = "committed_samples"
            }
        }

        var session: Session
    }

    var snapshot: Snapshot?
}

/// Only the sequence numbers are decoded. The events carry the transcript, and the measurement has
/// no use for it — not decoding it is how it never ends up in the app's memory or its report.
private struct EventsEnvelope: Decodable {
    struct Event: Decodable {
        var seq: Int
    }

    var events: [Event]
}
