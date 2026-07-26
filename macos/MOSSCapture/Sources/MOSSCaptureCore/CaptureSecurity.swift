import CryptoKit
import Darwin
import Foundation
import Security

public enum CaptureSecurityError: Error, Equatable {
    case keychainStatus(OSStatus)
    case missingSecret
    case pinMismatch
    case invalidPinnedHash
    case socketStatus(Int32)
    case invalidSocketPath
    case socketPathNotPrivate
    case peerCredentialUnavailable
    case peerUIDMismatch(expected: uid_t, actual: uid_t)
    case controlSecretMismatch
    case malformedRequest
    case oversizedRequest
    case trailingRequestBytes
    case unknownCommand(String)
    case missingPairingPayload
    case missingPairingServer
    case missingCaptureConfiguration
}

public final class KeychainCaptureSecretStore: CaptureKeyStoreAdapter, CaptureBearerTokenAdapter {
    public let service: String
    public let accessGroup: String?

    public init(
        service: String = "com.alphasight.moss.capture",
        accessGroup: String? = "com.alphasight.moss.capture.shared"
    ) {
        self.service = service
        self.accessGroup = accessGroup
    }

    public func saveControlSecret(_ secret: String) throws {
        try save(secret, account: "local-control-secret")
    }

    public func saveCaptureBearerToken(_ token: String) throws {
        try save(token, account: "capture-bearer")
    }

    public func loadControlSecret() throws -> String? {
        try load(account: "local-control-secret")
    }

    public func loadCaptureBearerToken() throws -> String? {
        try load(account: "capture-bearer")
    }

    private func save(_ value: String, account: String) throws {
        var attributes = baseQuery(account: account)
        SecItemDelete(attributes as CFDictionary)
        attributes[kSecValueData as String] = Data(value.utf8)
        attributes[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        let status = SecItemAdd(attributes as CFDictionary, nil)
        guard status == errSecSuccess else {
            throw CaptureSecurityError.keychainStatus(status)
        }
    }

    private func load(account: String) throws -> String? {
        var query = baseQuery(account: account)
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        if status == errSecItemNotFound {
            return nil
        }
        guard status == errSecSuccess else {
            throw CaptureSecurityError.keychainStatus(status)
        }
        guard let data = result as? Data else {
            return nil
        }
        return String(data: data, encoding: .utf8)
    }

    private func baseQuery(account: String) -> [String: Any] {
        var query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        if let accessGroup {
            query[kSecAttrAccessGroup as String] = accessGroup
        }
        return query
    }
}

public struct FullCertificatePinValidator {
    public init() {}

    public func validate(certificate: SecCertificate, expectedSHA256Hex: String) throws {
        guard expectedSHA256Hex.count == 64, expectedSHA256Hex.allSatisfy(\.isHexDigit) else {
            throw CaptureSecurityError.invalidPinnedHash
        }
        let certificateData = SecCertificateCopyData(certificate) as Data
        let digest = SHA256.hash(data: certificateData)
            .map { String(format: "%02x", $0) }
            .joined()
        guard digest.caseInsensitiveCompare(expectedSHA256Hex) == .orderedSame else {
            throw CaptureSecurityError.pinMismatch
        }
    }
}

public protocol ControlSecretAdapter {
    func loadControlSecret() throws -> String?
}

extension KeychainCaptureSecretStore: ControlSecretAdapter {}
extension FakeCaptureKeyStoreAdapter: ControlSecretAdapter {}

public struct ControlChannelRequest: Codable, Equatable {
    public var command: String
    public var label: String?
    public var serverURL: URL?
    public var sessionID: String?
    public var pairingPayload: Data?

    public init(
        command: String,
        label: String? = nil,
        serverURL: URL? = nil,
        sessionID: String? = nil,
        pairingPayload: Data? = nil
    ) {
        self.command = command
        self.label = label
        self.serverURL = serverURL
        self.sessionID = sessionID
        self.pairingPayload = pairingPayload
    }
}

public struct ControlChannelResponse: Codable, Equatable {
    public var ok: Bool
    public var running: Bool?
    public var sessionID: String?
    public var publishedFrameCount: Int?
    public var error: String?

    public init(
        ok: Bool,
        running: Bool? = nil,
        sessionID: String? = nil,
        publishedFrameCount: Int? = nil,
        error: String? = nil
    ) {
        self.ok = ok
        self.running = running
        self.sessionID = sessionID
        self.publishedFrameCount = publishedFrameCount
        self.error = error
    }

    public init(status: CaptureStatus) {
        self.init(
            ok: true,
            running: status.running,
            sessionID: status.sessionID,
            publishedFrameCount: status.publishedFrameCount
        )
    }
}

public final class SameUserUDSAuthenticator {
    private let secrets: ControlSecretAdapter
    private let expectedUID: uid_t

    public init(secrets: ControlSecretAdapter, expectedUID: uid_t = getuid()) {
        self.secrets = secrets
        self.expectedUID = expectedUID
    }

    public func validateSocketPermissions(_ permissions: UInt16) throws {
        guard permissions & 0o077 == 0 else {
            throw CaptureSecurityError.socketPathNotPrivate
        }
    }

    public func validate(peerUID: uid_t, presentedSecret: String) throws {
        guard peerUID == expectedUID else {
            throw CaptureSecurityError.peerUIDMismatch(expected: expectedUID, actual: peerUID)
        }
        guard let controlSecret = try secrets.loadControlSecret() else {
            throw CaptureSecurityError.missingSecret
        }
        guard constantTimeEquals(controlSecret, presentedSecret) else {
            throw CaptureSecurityError.controlSecretMismatch
        }
    }

    public func validatePeerCredentials(fileDescriptor: Int32, presentedSecret: String) throws {
        var credentials = xucred()
        var length = socklen_t(MemoryLayout<xucred>.stride)
        let status = getsockopt(fileDescriptor, 0, LOCAL_PEERCRED, &credentials, &length)
        guard status == 0 else {
            throw CaptureSecurityError.peerCredentialUnavailable
        }
        try validate(peerUID: credentials.cr_uid, presentedSecret: presentedSecret)
    }
}

public final class UnixDomainControlClient {
    public let socketPath: String
    private let secrets: ControlSecretAdapter
    private let maxFrameBytes: Int

    public init(socketPath: String, secrets: ControlSecretAdapter, maxFrameBytes: Int = 65_536) {
        self.socketPath = socketPath
        self.secrets = secrets
        self.maxFrameBytes = maxFrameBytes
    }

    public func encodeRequest(_ request: ControlChannelRequest) throws -> Data {
        guard let controlSecret = try secrets.loadControlSecret() else {
            throw CaptureSecurityError.missingSecret
        }
        return try encodeFrame(JSONEncoder().encode(Envelope(secret: controlSecret, request: request)))
    }

    public func sendRequest(_ request: ControlChannelRequest) throws -> ControlChannelResponse {
        let fileDescriptor = try openStreamSocket()
        defer { close(fileDescriptor) }

        try connect(fileDescriptor: fileDescriptor, socketPath: socketPath)
        try writeAll(try encodeRequest(request), to: fileDescriptor)
        let responseBody = try readFrame(from: fileDescriptor, maxFrameBytes: maxFrameBytes)
        return try JSONDecoder().decode(ControlChannelResponse.self, from: responseBody)
    }

    public func openStreamSocket() throws -> Int32 {
        let fileDescriptor = socket(AF_UNIX, SOCK_STREAM, 0)
        guard fileDescriptor >= 0 else {
            throw CaptureSecurityError.socketStatus(errno)
        }
        return fileDescriptor
    }

    private struct Envelope: Encodable {
        var secret: String
        var request: ControlChannelRequest
    }
}

public struct CapturePairingResult: Equatable {
    public var sessionID: String
    public var captureBearerToken: String?

    public init(sessionID: String, captureBearerToken: String? = nil) {
        self.sessionID = sessionID
        self.captureBearerToken = captureBearerToken
    }
}

public protocol CapturePairingExchangeAdapter {
    func pair(serverURL: URL, pairingPayload: Data) throws -> CapturePairingResult
}

public protocol CaptureBearerTokenStoreAdapter {
    func saveCaptureBearerToken(_ token: String) throws
}

extension KeychainCaptureSecretStore: CaptureBearerTokenStoreAdapter {}

public final class ControlCommandDispatcher {
    private let controller: CaptureController
    private let pairingExchange: CapturePairingExchangeAdapter
    private let captureTokenStore: CaptureBearerTokenStoreAdapter?
    private var pairedConfiguration: CaptureConfiguration?

    public init(
        controller: CaptureController,
        pairingExchange: CapturePairingExchangeAdapter,
        captureTokenStore: CaptureBearerTokenStoreAdapter? = nil
    ) {
        self.controller = controller
        self.pairingExchange = pairingExchange
        self.captureTokenStore = captureTokenStore
    }

    public func dispatch(_ request: ControlChannelRequest) throws -> ControlChannelResponse {
        switch request.command {
        case "pair":
            guard let serverURL = request.serverURL else {
                throw CaptureSecurityError.missingPairingServer
            }
            guard let pairingPayload = request.pairingPayload, !pairingPayload.isEmpty else {
                throw CaptureSecurityError.missingPairingPayload
            }
            let result = try pairingExchange.pair(serverURL: serverURL, pairingPayload: pairingPayload)
            if let token = result.captureBearerToken {
                try captureTokenStore?.saveCaptureBearerToken(token)
            }
            pairedConfiguration = CaptureConfiguration(
                sessionID: result.sessionID,
                serverURL: serverURL,
                label: request.label
            )
            return ControlChannelResponse(ok: true, running: controller.status().running, sessionID: result.sessionID)
        case "start":
            let configuration = try captureConfiguration(from: request)
            return ControlChannelResponse(status: try controller.start(configuration: configuration))
        case "status":
            return ControlChannelResponse(status: controller.status())
        case "stop":
            return ControlChannelResponse(status: try controller.stop(deadline: Date()))
        default:
            throw CaptureSecurityError.unknownCommand(request.command)
        }
    }

    private func captureConfiguration(from request: ControlChannelRequest) throws -> CaptureConfiguration {
        if let sessionID = request.sessionID, let serverURL = request.serverURL {
            return CaptureConfiguration(sessionID: sessionID, serverURL: serverURL, label: request.label)
        }
        if var pairedConfiguration {
            if let label = request.label {
                pairedConfiguration.label = label
            }
            return pairedConfiguration
        }
        throw CaptureSecurityError.missingCaptureConfiguration
    }
}

public final class UnixDomainControlServer {
    private let socketPath: String
    private let authenticator: SameUserUDSAuthenticator
    private let maxFrameBytes: Int
    private let handler: (ControlChannelRequest) throws -> ControlChannelResponse
    private var serverFileDescriptor: Int32 = -1
    private var stopped = false

    public init(
        socketPath: String,
        authenticator: SameUserUDSAuthenticator,
        maxFrameBytes: Int = 65_536,
        handler: @escaping (ControlChannelRequest) throws -> ControlChannelResponse
    ) {
        self.socketPath = socketPath
        self.authenticator = authenticator
        self.maxFrameBytes = maxFrameBytes
        self.handler = handler
    }

    deinit {
        stop()
    }

    public func serve() throws {
        try bindAndListen()
        while !stopped {
            try acceptAndReply()
        }
    }

    public func serveOnce() throws {
        try bindAndListen()
        try acceptAndReply()
        stop()
    }

    public func stop() {
        stopped = true
        if serverFileDescriptor >= 0 {
            close(serverFileDescriptor)
            serverFileDescriptor = -1
        }
        unlink(socketPath)
    }

    private func bindAndListen() throws {
        if serverFileDescriptor >= 0 {
            return
        }
        try FileManager.default.createDirectory(
            atPath: URL(fileURLWithPath: socketPath).deletingLastPathComponent().path,
            withIntermediateDirectories: true
        )
        unlink(socketPath)
        serverFileDescriptor = socket(AF_UNIX, SOCK_STREAM, 0)
        guard serverFileDescriptor >= 0 else {
            throw CaptureSecurityError.socketStatus(errno)
        }
        do {
            try withSockAddr(socketPath) { address, length in
                guard bind(serverFileDescriptor, address, length) == 0 else {
                    throw CaptureSecurityError.socketStatus(errno)
                }
            }
            guard chmod(socketPath, 0o600) == 0 else {
                throw CaptureSecurityError.socketStatus(errno)
            }
            try authenticator.validateSocketPermissions(try socketPermissions(at: socketPath))
            guard listen(serverFileDescriptor, 8) == 0 else {
                throw CaptureSecurityError.socketStatus(errno)
            }
        } catch {
            stop()
            throw error
        }
    }

    private func acceptAndReply() throws {
        let acceptedFileDescriptor = accept(serverFileDescriptor, nil, nil)
        guard acceptedFileDescriptor >= 0 else {
            if stopped {
                return
            }
            throw CaptureSecurityError.socketStatus(errno)
        }
        defer { close(acceptedFileDescriptor) }

        let response: ControlChannelResponse
        do {
            let body = try readFrame(from: acceptedFileDescriptor, maxFrameBytes: maxFrameBytes)
            try rejectTrailingRequestBytes(on: acceptedFileDescriptor)
            let envelope = try decodeEnvelope(from: body)
            try authenticator.validatePeerCredentials(
                fileDescriptor: acceptedFileDescriptor,
                presentedSecret: envelope.secret
            )
            response = try handler(envelope.request)
        } catch {
            response = ControlChannelResponse(ok: false, error: sanitizedControlError(error))
        }
        try writeAll(try encodeFrame(JSONEncoder().encode(response)), to: acceptedFileDescriptor)
    }

    private struct Envelope: Decodable {
        var secret: String
        var request: ControlChannelRequest
    }

    private func decodeEnvelope(from body: Data) throws -> Envelope {
        do {
            return try JSONDecoder().decode(Envelope.self, from: body)
        } catch {
            throw CaptureSecurityError.malformedRequest
        }
    }
}

extension UnixDomainControlServer: @unchecked Sendable {}

public enum ControlSocketDefaults {
    public static func socketPath(environment: [String: String] = ProcessInfo.processInfo.environment) -> String {
        environment["MOSS_CAPTURE_CONTROL_SOCKET"] ?? "/tmp/moss-capture-\(getuid())/control.sock"
    }
}

public final class URLSessionCapturePairingExchangeAdapter: CapturePairingExchangeAdapter {
    private let client: CaptureHTTPClient

    public init(client: CaptureHTTPClient = URLSessionCaptureHTTPClient()) {
        self.client = client
    }

    public func pair(serverURL: URL, pairingPayload: Data) throws -> CapturePairingResult {
        var request = URLRequest(url: serverURL.appendingPathComponent("api").appendingPathComponent("live").appendingPathComponent("pair"))
        request.httpMethod = "POST"
        request.setValue("application/octet-stream", forHTTPHeaderField: "Content-Type")
        request.httpBody = pairingPayload
        let response = try client.send(request)
        guard (200..<300).contains(response.statusCode) else {
            throw CaptureHTTPTransportError.nonSuccessStatus(response.statusCode)
        }
        let body = try JSONDecoder().decode(PairingResponseBody.self, from: response.body)
        return CapturePairingResult(sessionID: body.sessionID, captureBearerToken: body.captureBearerToken)
    }

    private struct PairingResponseBody: Decodable {
        var sessionID: String
        var captureBearerToken: String?

        enum CodingKeys: String, CodingKey {
            case sessionID = "session_id"
            case captureBearerToken = "capture_bearer"
        }
    }
}

private func constantTimeEquals(_ lhs: String, _ rhs: String) -> Bool {
    let left = Array(lhs.utf8)
    let right = Array(rhs.utf8)
    guard !left.isEmpty, !right.isEmpty else {
        return left.isEmpty && right.isEmpty
    }
    var difference = left.count ^ right.count
    for index in 0..<max(left.count, right.count) {
        difference |= Int(left[index % left.count] ^ right[index % right.count])
    }
    return difference == 0
}

private func connect(fileDescriptor: Int32, socketPath: String) throws {
    try withSockAddr(socketPath) { address, length in
        guard Darwin.connect(fileDescriptor, address, length) == 0 else {
            throw CaptureSecurityError.socketStatus(errno)
        }
    }
}

private func withSockAddr<T>(_ socketPath: String, _ body: (UnsafePointer<sockaddr>, socklen_t) throws -> T) throws -> T {
    let pathBytes = Array(socketPath.utf8)
    guard pathBytes.count < 104 else {
        throw CaptureSecurityError.invalidSocketPath
    }
    var address = sockaddr_un()
    address.sun_family = sa_family_t(AF_UNIX)
    #if os(macOS)
    address.sun_len = UInt8(MemoryLayout<sockaddr_un>.size)
    #endif
    withUnsafeMutableBytes(of: &address.sun_path) { rawBuffer in
        for index in pathBytes.indices {
            rawBuffer[index] = pathBytes[index]
        }
        rawBuffer[pathBytes.count] = 0
    }
    let length = socklen_t(MemoryLayout<sa_family_t>.size + pathBytes.count + 1)
    return try withUnsafePointer(to: &address) { pointer in
        try pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) { socketAddress in
            try body(socketAddress, length)
        }
    }
}

private func encodeFrame(_ body: Data) throws -> Data {
    guard body.count <= 65_536 else {
        throw CaptureSecurityError.oversizedRequest
    }
    var length = UInt32(body.count).bigEndian
    var frame = Data()
    withUnsafeBytes(of: &length) { bytes in
        frame.append(contentsOf: bytes)
    }
    frame.append(body)
    return frame
}

private func readFrame(from fileDescriptor: Int32, maxFrameBytes: Int) throws -> Data {
    let prefix = try readExactly(4, from: fileDescriptor)
    let length = prefix.withUnsafeBytes { rawBuffer in
        UInt32(bigEndian: rawBuffer.load(as: UInt32.self))
    }
    guard length <= maxFrameBytes else {
        throw CaptureSecurityError.oversizedRequest
    }
    return try readExactly(Int(length), from: fileDescriptor)
}

private func rejectTrailingRequestBytes(on fileDescriptor: Int32) throws {
    var byte: UInt8 = 0
    let count = withUnsafeMutableBytes(of: &byte) { rawBuffer in
        recv(fileDescriptor, rawBuffer.baseAddress, 1, MSG_PEEK | MSG_DONTWAIT)
    }
    if count > 0 {
        throw CaptureSecurityError.trailingRequestBytes
    }
    if count == 0 {
        return
    }
    if errno == EAGAIN || errno == EWOULDBLOCK {
        return
    }
    throw CaptureSecurityError.socketStatus(errno)
}

private func readExactly(_ byteCount: Int, from fileDescriptor: Int32) throws -> Data {
    var data = Data(count: byteCount)
    var offset = 0
    while offset < byteCount {
        let count = data.withUnsafeMutableBytes { rawBuffer in
            Darwin.read(fileDescriptor, rawBuffer.baseAddress!.advanced(by: offset), byteCount - offset)
        }
        guard count > 0 else {
            throw CaptureSecurityError.malformedRequest
        }
        offset += count
    }
    return data
}

private func writeAll(_ data: Data, to fileDescriptor: Int32) throws {
    try data.withUnsafeBytes { rawBuffer in
        var offset = 0
        while offset < data.count {
            let count = Darwin.write(fileDescriptor, rawBuffer.baseAddress!.advanced(by: offset), data.count - offset)
            guard count > 0 else {
                throw CaptureSecurityError.socketStatus(errno)
            }
            offset += count
        }
    }
}

private func socketPermissions(at path: String) throws -> UInt16 {
    var info = stat()
    guard stat(path, &info) == 0 else {
        throw CaptureSecurityError.socketStatus(errno)
    }
    return UInt16(info.st_mode & 0o777)
}

private func sanitizedControlError(_ error: Error) -> String {
    switch error {
    case let securityError as CaptureSecurityError:
        return String(describing: securityError)
    case let controllerError as CaptureControllerError:
        return String(describing: controllerError)
    case let transportError as CaptureHTTPTransportError:
        return String(describing: transportError)
    default:
        return "control_failed"
    }
}
