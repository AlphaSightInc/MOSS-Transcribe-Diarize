import CryptoKit
import Darwin
import Foundation
import Security
#if canImport(AppKit)
import AppKit
#endif

private enum CaptureSecretStoreAccount {
    static let controlSecret = "local-control-secret"
    static let captureBearer = "capture-bearer"
    static let certificatePin = "capture-certificate-pin"
    static let deviceIDAccount = "capture-device-id"
    static let deviceID = deviceIDAccount
    static let serverURL = "capture-server-url"
    static let sessionID = "capture-session-id"
    static let viewToken = "capture-view-token"
}

public enum CaptureSecurityError: Error, Equatable {
    case keychainStatus(OSStatus)
    case missingSecret
    case invalidSecretStorePath
    case secretStoreStatus(Int32)
    case secretStorePathNotPrivate
    case secretStoreDirectoryNotPrivate
    case secretStoreOwnerMismatch(expected: uid_t, actual: uid_t)
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
    case invalidPairingPayload
    case missingPairingServer
    case missingCaptureConfiguration
    case portalHandoffUnavailable
    case pasteboardUnavailable
}

/// Dormant secret store: no product entrypoint selects it. It keeps no access group, so it can
/// only ever reach the process's own default keychain access group — a shared group needs a Team
/// ID that a locally signed identity does not have.
public final class KeychainCaptureSecretStore: CaptureKeyStoreAdapter, CaptureBearerTokenAdapter {
    public let service: String

    public init(service: String = "com.alphasight.moss.capture") {
        self.service = service
    }

    public func saveControlSecret(_ secret: String) throws {
        try save(secret, account: CaptureSecretStoreAccount.controlSecret)
    }

    public func saveCaptureBearerToken(_ token: String) throws {
        try save(token, account: CaptureSecretStoreAccount.captureBearer)
    }

    public func saveCaptureCertificatePin(_ pin: String) throws {
        try save(pin, account: CaptureSecretStoreAccount.certificatePin)
    }

    public func saveCaptureServerURL(_ serverURL: URL) throws {
        try save(serverURL.absoluteString, account: CaptureSecretStoreAccount.serverURL)
    }

    public func saveCaptureSessionID(_ sessionID: String) throws {
        try save(sessionID, account: CaptureSecretStoreAccount.sessionID)
    }

    public func saveCaptureViewToken(_ viewToken: String) throws {
        try save(viewToken, account: CaptureSecretStoreAccount.viewToken)
    }

    public func loadControlSecret() throws -> String? {
        try load(account: CaptureSecretStoreAccount.controlSecret)
    }

    public func loadCaptureBearerToken() throws -> String? {
        try load(account: CaptureSecretStoreAccount.captureBearer)
    }

    public func loadCaptureCertificatePin() throws -> String? {
        try load(account: CaptureSecretStoreAccount.certificatePin)
    }

    public func loadDeviceID() throws -> String {
        if let deviceID = try load(account: CaptureSecretStoreAccount.deviceID), !deviceID.isEmpty {
            return deviceID
        }
        let deviceID = UUID().uuidString
        try save(deviceID, account: CaptureSecretStoreAccount.deviceID)
        return deviceID
    }

    public func loadCaptureServerURL() throws -> URL? {
        guard let rawURL = try load(account: CaptureSecretStoreAccount.serverURL) else {
            return nil
        }
        return URL(string: rawURL)
    }

    public func loadCaptureSessionID() throws -> String? {
        try load(account: CaptureSecretStoreAccount.sessionID)
    }

    public func loadCaptureViewToken() throws -> String? {
        try load(account: CaptureSecretStoreAccount.viewToken)
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
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
    }
}

public protocol CaptureSecretStoreAdapter:
    CaptureKeyStoreAdapter,
    ControlSecretStoreAdapter,
    CaptureBearerTokenAdapter,
    CaptureBearerTokenStoreAdapter,
    CaptureCertificatePinAdapter,
    CaptureCertificatePinStoreAdapter,
    CaptureDeviceIdentityAdapter,
    CaptureSessionStoreAdapter
{}

extension KeychainCaptureSecretStore: CaptureSecretStoreAdapter {}

public enum CaptureSecretStoreSelection {
    public static let environmentKey = "MOSS_CAPTURE_SECRET_STORE_PATH"

    /// The one store both product entrypoints resolve, so the app and the CLI always agree on
    /// where the paired authority lives without either composition root repeating a literal.
    public static func defaultPath(homeDirectory: String = NSHomeDirectory()) -> String {
        URL(fileURLWithPath: homeDirectory, isDirectory: true)
            .appendingPathComponent("Library", isDirectory: true)
            .appendingPathComponent("Application Support", isDirectory: true)
            .appendingPathComponent("MOSSCapture", isDirectory: true)
            .appendingPathComponent("secrets.json")
            .path
    }

    public static func makeDefault(
        environment: [String: String] = ProcessInfo.processInfo.environment,
        environmentKey: String = environmentKey,
        homeDirectory: String = NSHomeDirectory()
    ) throws -> any CaptureSecretStoreAdapter {
        let overridePath = environment[environmentKey] ?? ""
        return try FileCaptureSecretStore(
            path: overridePath.isEmpty ? defaultPath(homeDirectory: homeDirectory) : overridePath
        )
    }
}

public final class FileCaptureSecretStore: CaptureSecretStoreAdapter {
    private let url: URL
    private let expectedUID: uid_t
    private let lock = NSLock()

    public var path: String {
        url.path
    }

    public init(path: String, expectedUID: uid_t = getuid()) throws {
        guard !path.isEmpty else {
            throw CaptureSecurityError.invalidSecretStorePath
        }
        url = URL(fileURLWithPath: path)
        self.expectedUID = expectedUID
        // Constructing a store stays side-effect free — `mtd-capture --help` must not create a
        // directory in the user's home. The private directory is materialized on first write.
        if FileManager.default.fileExists(atPath: url.path) {
            try validateFile()
        }
    }

    public func saveControlSecret(_ secret: String) throws {
        try save(secret, account: CaptureSecretStoreAccount.controlSecret)
    }

    public func saveCaptureBearerToken(_ token: String) throws {
        try save(token, account: CaptureSecretStoreAccount.captureBearer)
    }

    public func saveCaptureCertificatePin(_ pin: String) throws {
        try save(pin, account: CaptureSecretStoreAccount.certificatePin)
    }

    public func saveCaptureServerURL(_ serverURL: URL) throws {
        try save(serverURL.absoluteString, account: CaptureSecretStoreAccount.serverURL)
    }

    public func saveCaptureSessionID(_ sessionID: String) throws {
        try save(sessionID, account: CaptureSecretStoreAccount.sessionID)
    }

    public func saveCaptureViewToken(_ viewToken: String) throws {
        try save(viewToken, account: CaptureSecretStoreAccount.viewToken)
    }

    public func loadControlSecret() throws -> String? {
        try load(account: CaptureSecretStoreAccount.controlSecret)
    }

    public func loadCaptureBearerToken() throws -> String? {
        try load(account: CaptureSecretStoreAccount.captureBearer)
    }

    public func loadCaptureCertificatePin() throws -> String? {
        try load(account: CaptureSecretStoreAccount.certificatePin)
    }

    public func loadDeviceID() throws -> String {
        if let deviceID = try load(account: CaptureSecretStoreAccount.deviceID), !deviceID.isEmpty {
            return deviceID
        }
        let deviceID = UUID().uuidString
        try save(deviceID, account: CaptureSecretStoreAccount.deviceID)
        return deviceID
    }

    public func loadCaptureServerURL() throws -> URL? {
        guard let rawURL = try load(account: CaptureSecretStoreAccount.serverURL) else {
            return nil
        }
        return URL(string: rawURL)
    }

    public func loadCaptureSessionID() throws -> String? {
        try load(account: CaptureSecretStoreAccount.sessionID)
    }

    public func loadCaptureViewToken() throws -> String? {
        try load(account: CaptureSecretStoreAccount.viewToken)
    }

    private func save(_ value: String, account: String) throws {
        lock.lock()
        defer { lock.unlock() }
        var document = try loadDocument()
        document.values[account] = value
        try writeDocument(document)
    }

    private func load(account: String) throws -> String? {
        lock.lock()
        defer { lock.unlock() }
        return try loadDocument().values[account]
    }

    private func loadDocument() throws -> FileSecretDocument {
        guard FileManager.default.fileExists(atPath: url.path) else {
            return FileSecretDocument()
        }
        try validateFile()
        let data = try Data(contentsOf: url)
        if data.isEmpty {
            return FileSecretDocument()
        }
        return try JSONDecoder().decode(FileSecretDocument.self, from: data)
    }

    private func writeDocument(_ document: FileSecretDocument) throws {
        try prepareDirectory()
        if FileManager.default.fileExists(atPath: url.path) {
            try validateFile()
        }
        let data = try JSONEncoder().encode(document)
        let temporaryURL = url
            .deletingLastPathComponent()
            .appendingPathComponent(".\(url.lastPathComponent).\(UUID().uuidString).tmp")
        defer { try? FileManager.default.removeItem(at: temporaryURL) }
        try writePrivateFile(data, at: temporaryURL)
        // rename(2) publishes the new document in one step: a reader never sees a half-written
        // file, and the live path never exists with permissions wider than 0600.
        guard rename(temporaryURL.path, url.path) == 0 else {
            throw CaptureSecurityError.secretStoreStatus(errno)
        }
        try validateFile()
    }

    private func writePrivateFile(_ data: Data, at fileURL: URL) throws {
        let descriptor = open(fileURL.path, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0o600)
        guard descriptor >= 0 else {
            throw CaptureSecurityError.secretStoreStatus(errno)
        }
        var isOpen = true
        defer { if isOpen { close(descriptor) } }
        // umask could have relaxed the creation mode, so state it exactly before any byte lands.
        guard fchmod(descriptor, 0o600) == 0 else {
            throw CaptureSecurityError.secretStoreStatus(errno)
        }
        try data.withUnsafeBytes { buffer in
            var offset = 0
            while offset < buffer.count {
                let written = write(descriptor, buffer.baseAddress! + offset, buffer.count - offset)
                guard written > 0 else {
                    throw CaptureSecurityError.secretStoreStatus(errno)
                }
                offset += written
            }
        }
        guard fsync(descriptor) == 0 else {
            throw CaptureSecurityError.secretStoreStatus(errno)
        }
        isOpen = false
        guard close(descriptor) == 0 else {
            throw CaptureSecurityError.secretStoreStatus(errno)
        }
    }

    /// A widened directory is tightened rather than refused: it cannot expose a 0600 document, so
    /// repairing it keeps a paired device working. A widened document is refused instead, because
    /// its bytes may already have been read by another user.
    private func prepareDirectory() throws {
        let directory = url.deletingLastPathComponent()
        var info = stat()
        if stat(directory.path, &info) != 0 {
            try FileManager.default.createDirectory(
                at: directory,
                withIntermediateDirectories: true,
                attributes: [.posixPermissions: 0o700]
            )
            guard stat(directory.path, &info) == 0 else {
                throw CaptureSecurityError.secretStoreStatus(errno)
            }
        }
        if info.st_mode & 0o777 != 0o700 {
            guard chmod(directory.path, 0o700) == 0, stat(directory.path, &info) == 0 else {
                throw CaptureSecurityError.secretStoreStatus(errno)
            }
        }
        guard info.st_mode & mode_t(S_IFMT) == mode_t(S_IFDIR), info.st_mode & 0o777 == 0o700 else {
            throw CaptureSecurityError.secretStoreDirectoryNotPrivate
        }
        guard info.st_uid == expectedUID else {
            throw CaptureSecurityError.secretStoreOwnerMismatch(expected: expectedUID, actual: info.st_uid)
        }
    }

    private func validateFile() throws {
        var info = stat()
        guard lstat(url.path, &info) == 0 else {
            throw CaptureSecurityError.secretStoreStatus(errno)
        }
        guard info.st_mode & mode_t(S_IFMT) == mode_t(S_IFREG), info.st_mode & 0o777 == 0o600 else {
            throw CaptureSecurityError.secretStorePathNotPrivate
        }
        guard info.st_uid == expectedUID else {
            throw CaptureSecurityError.secretStoreOwnerMismatch(expected: expectedUID, actual: info.st_uid)
        }
    }
}

private struct FileSecretDocument: Codable {
    var values: [String: String] = [:]
}

public struct FullCertificatePinValidator: Sendable {
    public init() {}

    public func validate(expectedSHA256Hex: String) throws {
        guard expectedSHA256Hex.count == 64, expectedSHA256Hex.allSatisfy(\.isHexDigit) else {
            throw CaptureSecurityError.invalidPinnedHash
        }
    }

    public func validate(certificate: SecCertificate, expectedSHA256Hex: String) throws {
        try validate(expectedSHA256Hex: expectedSHA256Hex)
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

public protocol ControlSecretStoreAdapter: ControlSecretAdapter {
    func saveControlSecret(_ secret: String) throws
}

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
    public var portalURL: URL?
    public var viewAuthority: String?
    public var publishedFrameCount: Int?
    public var pumpFailure: CapturePumpFailure?
    public var error: String?

    public init(
        ok: Bool,
        running: Bool? = nil,
        sessionID: String? = nil,
        portalURL: URL? = nil,
        viewAuthority: String? = nil,
        publishedFrameCount: Int? = nil,
        pumpFailure: CapturePumpFailure? = nil,
        error: String? = nil
    ) {
        self.ok = ok
        self.running = running
        self.sessionID = sessionID
        self.portalURL = portalURL
        self.viewAuthority = viewAuthority
        self.publishedFrameCount = publishedFrameCount
        self.pumpFailure = pumpFailure
        self.error = error
    }

    public init(status: CaptureStatus) {
        self.init(
            ok: true,
            running: status.running,
            sessionID: status.sessionID,
            publishedFrameCount: status.publishedFrameCount,
            pumpFailure: status.pumpFailure
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
    public var deviceID: String
    public var sessionID: String
    public var viewToken: String?
    public var captureBearerToken: String?
    public var certificatePinSHA256Hex: String?

    public init(
        deviceID: String = "",
        sessionID: String,
        viewToken: String? = nil,
        captureBearerToken: String? = nil,
        certificatePinSHA256Hex: String? = nil
    ) {
        self.deviceID = deviceID
        self.sessionID = sessionID
        self.viewToken = viewToken
        self.captureBearerToken = captureBearerToken
        self.certificatePinSHA256Hex = certificatePinSHA256Hex
    }
}

public struct CapturePairingPayload: Equatable {
    public var secret: String
    public var certificatePinSHA256Hex: String

    public init(data: Data, validator: FullCertificatePinValidator = FullCertificatePinValidator()) throws {
        guard let payload = String(data: data, encoding: .utf8), !payload.isEmpty else {
            throw CaptureSecurityError.missingPairingPayload
        }
        let fields = payload.split(separator: ".", omittingEmptySubsequences: false)
        guard fields.count == 3, fields[0] == "mtd1", !fields[1].isEmpty else {
            throw CaptureSecurityError.invalidPairingPayload
        }
        let pin = String(fields[2])
        try validator.validate(expectedSHA256Hex: pin)
        secret = String(fields[1])
        certificatePinSHA256Hex = pin.lowercased()
    }
}

public protocol CapturePairingExchangeAdapter {
    func pair(serverURL: URL, pairingPayload: Data) throws -> CapturePairingResult
}

public protocol CaptureDeviceIdentityAdapter {
    func loadDeviceID() throws -> String
}

public final class GeneratedCaptureDeviceIdentityAdapter: CaptureDeviceIdentityAdapter {
    private let deviceID: String

    public init(deviceID: String = UUID().uuidString) {
        self.deviceID = deviceID
    }

    public func loadDeviceID() throws -> String {
        deviceID
    }
}

public protocol CaptureBearerTokenStoreAdapter {
    func saveCaptureBearerToken(_ token: String) throws
}

extension KeychainCaptureSecretStore: CaptureBearerTokenStoreAdapter {}

public protocol CaptureCertificatePinStoreAdapter {
    func saveCaptureCertificatePin(_ pin: String) throws
}

extension KeychainCaptureSecretStore: CaptureCertificatePinStoreAdapter {}

public protocol CaptureSessionStoreAdapter {
    func saveCaptureServerURL(_ serverURL: URL) throws
    func saveCaptureSessionID(_ sessionID: String) throws
    func saveCaptureViewToken(_ viewToken: String) throws
    func loadCaptureServerURL() throws -> URL?
    func loadCaptureSessionID() throws -> String?
    func loadCaptureViewToken() throws -> String?
}

extension KeychainCaptureSecretStore: CaptureSessionStoreAdapter {}

/// Non-secret result of a portal handoff. The view token itself never leaves the app: it goes
/// straight to the pasteboard, and only this status crosses the control channel.
public struct CapturePortalHandoffConfirmation: Equatable {
    public static let copiedToPasteboard = "copied-to-pasteboard"

    public var sessionID: String
    public var portalURL: URL
    public var viewAuthority: String

    public init(
        sessionID: String,
        portalURL: URL,
        viewAuthority: String = CapturePortalHandoffConfirmation.copiedToPasteboard
    ) {
        self.sessionID = sessionID
        self.portalURL = portalURL
        self.viewAuthority = viewAuthority
    }
}

public protocol CapturePortalHandoffAdapter {
    func perform() throws -> CapturePortalHandoffConfirmation
}

/// App-owned handoff: reads the stored view authority and writes it to the pasteboard. Only the
/// app composition root builds one, so the CLI never holds view authority.
public final class PasteboardCapturePortalHandoff: CapturePortalHandoffAdapter {
    public static let pasteboardNameEnvironmentKey = "MOSS_CAPTURE_PASTEBOARD_NAME"

    private let sessionStore: CaptureSessionStoreAdapter
    private let copyViewToken: (String) -> Bool

    public convenience init(
        sessionStore: CaptureSessionStoreAdapter,
        environment: [String: String] = ProcessInfo.processInfo.environment
    ) {
        self.init(sessionStore: sessionStore) { viewToken in
            #if canImport(AppKit)
            let pasteboard: NSPasteboard
            if let name = environment[Self.pasteboardNameEnvironmentKey], !name.isEmpty {
                pasteboard = NSPasteboard(name: NSPasteboard.Name(name))
            } else {
                pasteboard = .general
            }
            pasteboard.clearContents()
            return pasteboard.setString(viewToken, forType: .string)
            #else
            _ = viewToken
            return false
            #endif
        }
    }

    init(
        sessionStore: CaptureSessionStoreAdapter,
        copyViewToken: @escaping (String) -> Bool
    ) {
        self.sessionStore = sessionStore
        self.copyViewToken = copyViewToken
    }

    public func perform() throws -> CapturePortalHandoffConfirmation {
        guard let serverURL = try sessionStore.loadCaptureServerURL(),
              serverURL.scheme == "https",
              let sessionID = try sessionStore.loadCaptureSessionID(),
              !sessionID.isEmpty,
              let viewToken = try sessionStore.loadCaptureViewToken(),
              !viewToken.isEmpty
        else {
            throw CaptureSecurityError.portalHandoffUnavailable
        }
        guard copyViewToken(viewToken) else {
            throw CaptureSecurityError.pasteboardUnavailable
        }
        return CapturePortalHandoffConfirmation(
            sessionID: sessionID,
            portalURL: livePortalURL(from: serverURL)
        )
    }
}

public final class ControlCommandDispatcher {
    private let controller: CaptureController
    private let pairingExchange: CapturePairingExchangeAdapter
    private let captureTokenStore: CaptureBearerTokenStoreAdapter?
    private let certificatePinStore: CaptureCertificatePinStoreAdapter?
    private let sessionStore: CaptureSessionStoreAdapter?
    private let portalHandoff: CapturePortalHandoffAdapter?
    private var pairedConfiguration: CaptureConfiguration?

    public init(
        controller: CaptureController,
        pairingExchange: CapturePairingExchangeAdapter,
        captureTokenStore: CaptureBearerTokenStoreAdapter? = nil,
        certificatePinStore: CaptureCertificatePinStoreAdapter? = nil,
        sessionStore: CaptureSessionStoreAdapter? = nil,
        portalHandoff: CapturePortalHandoffAdapter? = nil
    ) {
        self.controller = controller
        self.pairingExchange = pairingExchange
        self.captureTokenStore = captureTokenStore
        self.certificatePinStore = certificatePinStore
        self.sessionStore = sessionStore
        self.portalHandoff = portalHandoff
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
            if let pin = result.certificatePinSHA256Hex {
                try certificatePinStore?.saveCaptureCertificatePin(pin)
            }
            try sessionStore?.saveCaptureServerURL(serverURL)
            try sessionStore?.saveCaptureSessionID(result.sessionID)
            if let viewToken = result.viewToken {
                try sessionStore?.saveCaptureViewToken(viewToken)
            }
            pairedConfiguration = CaptureConfiguration(
                sessionID: result.sessionID,
                serverURL: serverURL,
                label: request.label
            )
            return ControlChannelResponse(
                ok: true,
                running: controller.status().running,
                sessionID: result.sessionID,
                portalURL: livePortalURL(from: serverURL)
            )
        case "start":
            let configuration = try captureConfiguration(from: request)
            return ControlChannelResponse(status: try controller.start(configuration: configuration))
        case "status":
            return ControlChannelResponse(status: controller.status())
        case "stop":
            return ControlChannelResponse(status: try controller.stop(deadline: Date()))
        case "handoff":
            guard let portalHandoff else {
                throw CaptureSecurityError.portalHandoffUnavailable
            }
            let confirmation = try portalHandoff.perform()
            return ControlChannelResponse(
                ok: true,
                sessionID: confirmation.sessionID,
                portalURL: confirmation.portalURL,
                viewAuthority: confirmation.viewAuthority
            )
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
        if let sessionID = try sessionStore?.loadCaptureSessionID(),
           let serverURL = try sessionStore?.loadCaptureServerURL()
        {
            return CaptureConfiguration(sessionID: sessionID, serverURL: serverURL, label: request.label)
        }
        throw CaptureSecurityError.missingCaptureConfiguration
    }
}

private func livePortalURL(from serverURL: URL) -> URL {
    var components = URLComponents(url: serverURL, resolvingAgainstBaseURL: false)
    components?.query = nil
    components?.fragment = nil
    return (components?.url ?? serverURL).appendingPathComponent("live")
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
    private let client: (String) throws -> CaptureHTTPClient
    private let deviceIdentity: CaptureDeviceIdentityAdapter

    public init(
        client: CaptureHTTPClient,
        deviceIdentity: CaptureDeviceIdentityAdapter = GeneratedCaptureDeviceIdentityAdapter()
    ) {
        self.client = { _ in client }
        self.deviceIdentity = deviceIdentity
    }

    public init(
        clientProvider: CaptureHTTPClientProvider = PinnedURLSessionCaptureHTTPClientProvider(),
        deviceIdentity: CaptureDeviceIdentityAdapter = GeneratedCaptureDeviceIdentityAdapter()
    ) {
        self.client = { pin in
            try clientProvider.client(certificatePinSHA256Hex: pin)
        }
        self.deviceIdentity = deviceIdentity
    }

    public func pair(serverURL: URL, pairingPayload: Data) throws -> CapturePairingResult {
        let parsedPayload = try CapturePairingPayload(data: pairingPayload)
        let client = try client(parsedPayload.certificatePinSHA256Hex)
        let payload = String(decoding: pairingPayload, as: UTF8.self)
        let deviceID = try deviceIdentity.loadDeviceID()
        let pairing = try postPairing(
            client: client,
            serverURL: serverURL,
            deviceID: deviceID,
            pairingPayload: payload
        )
        let session = try postSession(client: client, serverURL: serverURL, deviceToken: pairing.deviceToken)
        return CapturePairingResult(
            deviceID: pairing.deviceID,
            sessionID: session.id,
            viewToken: session.viewToken,
            captureBearerToken: pairing.deviceToken,
            certificatePinSHA256Hex: parsedPayload.certificatePinSHA256Hex
        )
    }

    private func postPairing(
        client: CaptureHTTPClient,
        serverURL: URL,
        deviceID: String,
        pairingPayload: String
    ) throws -> PairingResponseBody {
        var request = URLRequest(
            url: serverURL
                .appendingPathComponent("api")
                .appendingPathComponent("live")
                .appendingPathComponent("pairings")
        )
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(
            PairingRequestBody(deviceID: deviceID, pairingPayload: pairingPayload)
        )
        let response = try client.send(request)
        guard (200..<300).contains(response.statusCode) else {
            throw CaptureHTTPTransportError.nonSuccessStatus(response.statusCode)
        }
        return try JSONDecoder().decode(PairingResponseBody.self, from: response.body)
    }

    private func postSession(
        client: CaptureHTTPClient,
        serverURL: URL,
        deviceToken: String
    ) throws -> SessionResponseBody {
        var request = URLRequest(
            url: serverURL
                .appendingPathComponent("api")
                .appendingPathComponent("live")
                .appendingPathComponent("sessions")
        )
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("Bearer \(deviceToken)", forHTTPHeaderField: "Authorization")
        let response = try client.send(request)
        guard (200..<300).contains(response.statusCode) else {
            throw CaptureHTTPTransportError.nonSuccessStatus(response.statusCode)
        }
        return try JSONDecoder().decode(SessionResponseBody.self, from: response.body)
    }

    private struct PairingRequestBody: Encodable {
        var deviceID: String
        var pairingPayload: String

        enum CodingKeys: String, CodingKey {
            case deviceID = "device_id"
            case pairingPayload = "pairing_payload"
        }
    }

    private struct PairingResponseBody: Decodable {
        var deviceID: String
        var deviceToken: String

        enum CodingKeys: String, CodingKey {
            case deviceID = "device_id"
            case deviceToken = "device_token"
        }
    }

    private struct SessionResponseBody: Decodable {
        var id: String
        var ownerDeviceID: String
        var viewToken: String

        enum CodingKeys: String, CodingKey {
            case id
            case ownerDeviceID = "owner_device_id"
            case viewToken = "view_token"
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
    case let nativeError as NativeCaptureError:
        return String(describing: nativeError)
    default:
        return "control_failed"
    }
}
