import Foundation
import Security

public protocol CaptureBearerTokenAdapter {
    func loadCaptureBearerToken() throws -> String?
}

public protocol CaptureCertificatePinAdapter {
    func loadCaptureCertificatePin() throws -> String?
}

extension KeychainCaptureSecretStore: CaptureCertificatePinAdapter {}

public protocol CaptureHTTPClient {
    @discardableResult
    func send(_ request: URLRequest) throws -> CaptureHTTPResponse
}

public struct CaptureHTTPResponse: Equatable, Sendable {
    public var statusCode: Int
    public var body: Data

    public init(statusCode: Int, body: Data = Data()) {
        self.statusCode = statusCode
        self.body = body
    }
}

public enum CaptureHTTPTransportError: Error, Equatable, Sendable {
    case missingCaptureBearer
    case missingCertificatePin
    case nonSuccessStatus(Int)
}

public final class URLSessionCaptureHTTPClient: CaptureHTTPClient {
    private let session: URLSession
    /// Only a session this client created may be torn down by it; an injected one belongs to its
    /// owner.
    private let ownsSession: Bool
    private let invalidation = CaptureHTTPClientInvalidationFlag()

    public init(certificatePinSHA256Hex: String) throws {
        let delegate = try PinnedCertificateURLSessionDelegate(expectedSHA256Hex: certificatePinSHA256Hex)
        let configuration = URLSessionConfiguration.ephemeral
        // One connection per lane plus one for the heartbeat. Concurrency above that would only
        // reorder a lane's own frames, which the server rejects.
        configuration.httpMaximumConnectionsPerHost = CaptureLane.allCases.count + 1
        session = URLSession(configuration: configuration, delegate: delegate, delegateQueue: nil)
        ownsSession = true
    }

    public init(session: URLSession) {
        self.session = session
        ownsSession = false
    }

    /// True once this client has been superseded. A session created here holds its pinning delegate
    /// strongly until it is invalidated, so a client that is dropped without this call leaks both
    /// for the life of the process.
    public var isInvalidated: Bool {
        invalidation.isSet
    }

    /// Releases the session and its pinning delegate, letting requests that are already in flight
    /// finish. Sending on an invalidated client fails rather than silently using a superseded pin.
    public func invalidate() {
        guard ownsSession, invalidation.set() else {
            return
        }
        session.finishTasksAndInvalidate()
    }

    public func send(_ request: URLRequest) throws -> CaptureHTTPResponse {
        guard !invalidation.isSet else {
            throw CaptureHTTPTransportError.missingCertificatePin
        }
        let semaphore = DispatchSemaphore(value: 0)
        let result = URLSessionResultBox()
        let task = session.dataTask(with: request) { data, response, error in
            defer { semaphore.signal() }
            if let error {
                result.store(.failure(error))
                return
            }
            let statusCode = (response as? HTTPURLResponse)?.statusCode ?? 0
            result.store(.success(CaptureHTTPResponse(statusCode: statusCode, body: data ?? Data())))
        }
        task.resume()
        semaphore.wait()
        return try result.load().get()
    }
}

public protocol CaptureHTTPClientProvider {
    func client(certificatePinSHA256Hex: String?) throws -> CaptureHTTPClient
}

/// Hands out one pinned client per pin, for as long as that pin is the current one.
///
/// The pin is re-read for every request so a rotation takes effect immediately, but a *session* is
/// not a per-request object: building one per frame means a fresh TLS handshake for every 0.5 s of
/// audio and — because a session retains its delegate until it is invalidated — one leaked session
/// and delegate per frame for the whole meeting. Caching by pin makes the transport reuse a warm
/// connection and keeps the process's session count at one per live pin, while a rotation still
/// supersedes the old session instead of leaving it usable.
public final class PinnedURLSessionCaptureHTTPClientProvider: CaptureHTTPClientProvider {
    private let makeClient: (String) throws -> URLSessionCaptureHTTPClient
    private let lock = NSLock()
    private var current: (pin: String, client: URLSessionCaptureHTTPClient)?

    public convenience init() {
        self.init(makeClient: { pin in
            try URLSessionCaptureHTTPClient(certificatePinSHA256Hex: pin)
        })
    }

    init(makeClient: @escaping (String) throws -> URLSessionCaptureHTTPClient) {
        self.makeClient = makeClient
    }

    public func client(certificatePinSHA256Hex: String?) throws -> CaptureHTTPClient {
        guard let certificatePinSHA256Hex, !certificatePinSHA256Hex.isEmpty else {
            throw CaptureHTTPTransportError.missingCertificatePin
        }
        lock.lock()
        defer { lock.unlock() }
        if let current, current.pin == certificatePinSHA256Hex {
            return current.client
        }
        let client = try makeClient(certificatePinSHA256Hex)
        current?.client.invalidate()
        current = (certificatePinSHA256Hex, client)
        return client
    }
}

private final class CaptureHTTPClientInvalidationFlag: @unchecked Sendable {
    private let lock = NSLock()
    private var invalidated = false

    var isSet: Bool {
        lock.lock()
        defer { lock.unlock() }
        return invalidated
    }

    /// Returns true the first time only, so the session is torn down exactly once.
    func set() -> Bool {
        lock.lock()
        defer { lock.unlock() }
        guard !invalidated else {
            return false
        }
        invalidated = true
        return true
    }
}

public final class PinnedCertificateURLSessionDelegate: NSObject, URLSessionDelegate {
    private let expectedSHA256Hex: String
    private let validator: FullCertificatePinValidator

    public init(
        expectedSHA256Hex: String,
        validator: FullCertificatePinValidator = FullCertificatePinValidator()
    ) throws {
        try validator.validate(expectedSHA256Hex: expectedSHA256Hex)
        self.expectedSHA256Hex = expectedSHA256Hex
        self.validator = validator
    }

    public func validate(serverTrust: SecTrust) throws {
        guard let chain = SecTrustCopyCertificateChain(serverTrust) as? [SecCertificate],
              let certificate = chain.first else {
            throw CaptureSecurityError.invalidPinnedHash
        }
        try validator.validate(certificate: certificate, expectedSHA256Hex: expectedSHA256Hex)
    }

    public func urlSession(
        _ session: URLSession,
        didReceive challenge: URLAuthenticationChallenge,
        completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void
    ) {
        guard challenge.protectionSpace.authenticationMethod == NSURLAuthenticationMethodServerTrust,
              let serverTrust = challenge.protectionSpace.serverTrust else {
            completionHandler(.cancelAuthenticationChallenge, nil)
            return
        }
        do {
            try validate(serverTrust: serverTrust)
            completionHandler(.useCredential, URLCredential(trust: serverTrust))
        } catch {
            completionHandler(.cancelAuthenticationChallenge, nil)
        }
    }
}

private final class URLSessionResultBox: @unchecked Sendable {
    private let lock = NSLock()
    private var result: Result<CaptureHTTPResponse, Error>?

    func store(_ result: Result<CaptureHTTPResponse, Error>) {
        lock.lock()
        self.result = result
        lock.unlock()
    }

    func load() -> Result<CaptureHTTPResponse, Error> {
        lock.lock()
        defer { lock.unlock() }
        return result ?? .failure(CaptureHTTPTransportError.nonSuccessStatus(0))
    }
}

public final class CaptureV2HTTPTransportAdapter: CaptureTransportAdapter {
    private let client: (CaptureConfiguration) throws -> CaptureHTTPClient
    private let bearerToken: CaptureBearerTokenAdapter

    public init(client: CaptureHTTPClient, bearerToken: CaptureBearerTokenAdapter) {
        self.client = { _ in client }
        self.bearerToken = bearerToken
    }

    public init(
        clientProvider: CaptureHTTPClientProvider = PinnedURLSessionCaptureHTTPClientProvider(),
        certificatePin: CaptureCertificatePinAdapter,
        bearerToken: CaptureBearerTokenAdapter
    ) {
        self.client = { _ in
            try clientProvider.client(certificatePinSHA256Hex: certificatePin.loadCaptureCertificatePin())
        }
        self.bearerToken = bearerToken
    }

    public func publish(frame: CaptureFrame, configuration: CaptureConfiguration) throws {
        let response = try client(configuration).send(
            try authorizedJSONRequest(
                url: liveURL(
                    base: configuration.serverURL,
                    sessionID: configuration.sessionID,
                    action: "frames"
                ),
                bearerToken: bearerToken.loadCaptureBearerToken(),
                body: StrictV2FramePayload(frame: frame)
            )
        )
        try requireSuccess(response)
    }
}

public final class CaptureHTTPHealthAdapter: CaptureHealthAdapter {
    private let client: (CaptureConfiguration) throws -> CaptureHTTPClient
    private let bearerToken: CaptureBearerTokenAdapter
    private let instanceID: String
    private let helperVersion: String

    public init(
        client: CaptureHTTPClient,
        bearerToken: CaptureBearerTokenAdapter,
        instanceID: String,
        helperVersion: String
    ) {
        self.client = { _ in client }
        self.bearerToken = bearerToken
        self.instanceID = instanceID
        self.helperVersion = helperVersion
    }

    public init(
        clientProvider: CaptureHTTPClientProvider = PinnedURLSessionCaptureHTTPClientProvider(),
        certificatePin: CaptureCertificatePinAdapter,
        bearerToken: CaptureBearerTokenAdapter,
        instanceID: String,
        helperVersion: String
    ) {
        self.client = { _ in
            try clientProvider.client(certificatePinSHA256Hex: certificatePin.loadCaptureCertificatePin())
        }
        self.bearerToken = bearerToken
        self.instanceID = instanceID
        self.helperVersion = helperVersion
    }

    public func emit(
        status: CaptureStatus,
        configuration: CaptureConfiguration,
        sentMonotonicNS: UInt64
    ) throws {
        let response = try client(configuration).send(
            try authorizedJSONRequest(
                url: liveURL(
                    base: configuration.serverURL,
                    sessionID: configuration.sessionID,
                    action: "heartbeat"
                ),
                bearerToken: bearerToken.loadCaptureBearerToken(),
                body: HelperHeartbeatPayload(
                    status: status,
                    instanceID: instanceID,
                    helperVersion: helperVersion,
                    sentMonotonicNS: sentMonotonicNS
                )
            )
        )
        try requireSuccess(response)
    }
}

public final class StaticCaptureBearerTokenAdapter: CaptureBearerTokenAdapter {
    private let token: String?

    public init(token: String?) {
        self.token = token
    }

    public func loadCaptureBearerToken() throws -> String? {
        token
    }
}

private struct StrictV2FramePayload: Encodable {
    var lane: String
    var sequence: UInt64
    var captureTimestampNS: UInt64
    var deviceEpoch: UInt64
    var silent: Bool
    var discontinuity: Bool
    var sampleRate: Int
    var sampleCount: Int
    var pcmBase64: String

    enum CodingKeys: String, CodingKey {
        case lane
        case sequence
        case captureTimestampNS = "capture_timestamp_ns"
        case deviceEpoch = "device_epoch"
        case silent
        case discontinuity
        case sampleRate = "sample_rate"
        case sampleCount = "sample_count"
        case pcmBase64 = "pcm_base64"
    }

    init(frame: CaptureFrame) {
        lane = frame.lane.rawValue
        sequence = frame.sequence
        captureTimestampNS = frame.captureTimestampNS
        deviceEpoch = frame.deviceEpoch
        silent = frame.silent
        discontinuity = frame.discontinuity
        sampleRate = frame.sampleRate
        sampleCount = frame.sampleCount
        pcmBase64 = frame.pcm16.base64EncodedString()
    }
}

private struct HelperHeartbeatPayload: Encodable {
    var schema = "moss-live-helper-health.v1"
    var instanceID: String
    var sequence: UInt64
    var sentMonotonicNS: UInt64
    var helperVersion: String
    var state: String
    var lanes: [String: HelperLanePayload]

    enum CodingKeys: String, CodingKey {
        case schema
        case instanceID = "instance_id"
        case sequence
        case sentMonotonicNS = "sent_monotonic_ns"
        case helperVersion = "helper_version"
        case state
        case lanes
    }

    init(
        status: CaptureStatus,
        instanceID: String,
        helperVersion: String,
        sentMonotonicNS: UInt64
    ) {
        self.instanceID = instanceID
        sequence = status.lastHealthSequence ?? 0
        self.sentMonotonicNS = sentMonotonicNS
        self.helperVersion = helperVersion
        state = status.running ? "capturing" : "stopped"
        lanes = Dictionary(
            uniqueKeysWithValues: status.reportedLanes().map { laneStatus in
                (
                    laneStatus.lane.rawValue,
                    HelperLanePayload(
                        state: laneStatus.state,
                        deviceEpoch: laneStatus.deviceEpoch,
                        droppedFrames: laneStatus.droppedFrames,
                        discontinuities: laneStatus.discontinuities,
                        failureCode: laneStatus.failureCode
                    )
                )
            }
        )
    }
}

private struct HelperLanePayload: Encodable {
    var state: String
    var deviceEpoch: UInt64
    var droppedFrames: UInt64
    var discontinuities: UInt64
    var failureCode: String?

    enum CodingKeys: String, CodingKey {
        case state
        case deviceEpoch = "device_epoch"
        case droppedFrames = "dropped_frames"
        case discontinuities
        case failureCode = "failure_code"
    }

    init(
        state: String,
        deviceEpoch: UInt64,
        droppedFrames: UInt64 = 0,
        discontinuities: UInt64 = 0,
        failureCode: String? = nil
    ) {
        self.state = state
        self.deviceEpoch = deviceEpoch
        self.droppedFrames = droppedFrames
        self.discontinuities = discontinuities
        self.failureCode = failureCode
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(state, forKey: .state)
        try container.encode(deviceEpoch, forKey: .deviceEpoch)
        try container.encode(droppedFrames, forKey: .droppedFrames)
        try container.encode(discontinuities, forKey: .discontinuities)
        if let failureCode {
            try container.encode(failureCode, forKey: .failureCode)
        } else {
            try container.encodeNil(forKey: .failureCode)
        }
    }
}

/// The one place the live session route shape is written, so the measurement probe cannot drift
/// from the transport it measures.
func liveURL(base: URL, sessionID: String, action: String) -> URL {
    base
        .appendingPathComponent("api")
        .appendingPathComponent("live")
        .appendingPathComponent("sessions")
        .appendingPathComponent(sessionID)
        .appendingPathComponent(action)
}

private func authorizedJSONRequest<T: Encodable>(
    url: URL,
    bearerToken: String?,
    body: T
) throws -> URLRequest {
    guard let bearerToken, !bearerToken.isEmpty else {
        throw CaptureHTTPTransportError.missingCaptureBearer
    }
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.setValue("Bearer \(bearerToken)", forHTTPHeaderField: "Authorization")
    request.setValue("application/json", forHTTPHeaderField: "Accept")
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    request.httpBody = try JSONEncoder().encode(body)
    return request
}

private func requireSuccess(_ response: CaptureHTTPResponse) throws {
    guard (200..<300).contains(response.statusCode) else {
        throw CaptureHTTPTransportError.nonSuccessStatus(response.statusCode)
    }
}
