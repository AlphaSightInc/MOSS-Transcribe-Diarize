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
    case socketPathNotPrivate
    case peerCredentialUnavailable
    case peerUIDMismatch(expected: uid_t, actual: uid_t)
    case controlSecretMismatch
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

    public init(command: String, label: String? = nil, serverURL: URL? = nil) {
        self.command = command
        self.label = label
        self.serverURL = serverURL
    }
}

public struct ControlChannelResponse: Codable, Equatable {
    public var ok: Bool
    public var running: Bool?

    public init(ok: Bool, running: Bool? = nil) {
        self.ok = ok
        self.running = running
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

    public init(socketPath: String, secrets: ControlSecretAdapter) {
        self.socketPath = socketPath
        self.secrets = secrets
    }

    public func encodeRequest(_ request: ControlChannelRequest) throws -> Data {
        guard let controlSecret = try secrets.loadControlSecret() else {
            throw CaptureSecurityError.missingSecret
        }
        return try JSONEncoder().encode(Envelope(secret: controlSecret, request: request))
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
