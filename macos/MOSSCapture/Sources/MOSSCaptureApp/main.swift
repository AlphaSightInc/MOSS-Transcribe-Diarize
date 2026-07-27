import AVFoundation
import CoreGraphics
import Foundation
import Darwin
import MOSSCaptureCore
import Security

@main
struct MOSSCaptureAppMain {
    static func main() {
        do {
            try ProductionCaptureRuntime.makeDefault().serve()
        } catch {
            Foundation.exit(70)
        }
    }
}

final class ProductionCaptureRuntime {
    private let server: UnixDomainControlServer

    init(server: UnixDomainControlServer) {
        self.server = server
    }

    static func makeDefault() throws -> ProductionCaptureRuntime {
        let keyStore = try CaptureSecretStoreSelection.makeDefault(
            environmentKey: "MOSS_CAPTURE_SECRET_STORE_PATH",
            keychainDefault: KeychainCaptureSecretStore()
        )
        try ensureControlSecret(in: keyStore)
        let controller = CaptureController(
            source: NativeDualCaptureSource(),
            transport: CaptureV2HTTPTransportAdapter(
                certificatePin: keyStore,
                bearerToken: keyStore
            ),
            keyStore: keyStore,
            clock: SystemCaptureClockAdapter(),
            scheduler: RepeatingCaptureSchedulerAdapter(interval: 0.25),
            health: CaptureHTTPHealthAdapter(
                certificatePin: keyStore,
                bearerToken: keyStore,
                instanceID: ProcessInfo.processInfo.globallyUniqueString,
                helperVersion: "0.1.0"
            )
        )
        let dispatcher = ControlCommandDispatcher(
            controller: controller,
            pairingExchange: URLSessionCapturePairingExchangeAdapter(deviceIdentity: keyStore),
            captureTokenStore: keyStore,
            certificatePinStore: keyStore,
            sessionStore: keyStore
        )
        return ProductionCaptureRuntime(
            server: UnixDomainControlServer(
                socketPath: ControlSocketDefaults.socketPath(),
                authenticator: SameUserUDSAuthenticator(secrets: keyStore),
                handler: { request in
                    if request.command == "start" {
                        try requireDualCaptureAuthorization()
                    }
                    return try dispatcher.dispatch(request)
                }
            )
        )
    }

    func serve() throws {
        try server.serve()
    }

    private static func ensureControlSecret(in keyStore: any CaptureSecretStoreAdapter) throws {
        if try keyStore.loadControlSecret() != nil {
            return
        }
        var bytes = [UInt8](repeating: 0, count: 32)
        guard SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes) == errSecSuccess else {
            throw CaptureSecurityError.missingSecret
        }
        try keyStore.saveControlSecret(Data(bytes).base64EncodedString())
    }

    private static func requireDualCaptureAuthorization() throws {
        guard AVCaptureDevice.authorizationStatus(for: .audio) == .authorized,
              CGPreflightScreenCaptureAccess()
        else {
            throw NativeCaptureError.permissionDenied(
                "microphone and system-audio authorization required"
            )
        }
    }
}

final class SystemCaptureClockAdapter: CaptureClockAdapter {
    func now() -> Date {
        Date()
    }

    func monotonicNanoseconds() -> UInt64 {
        var time = timespec()
        clock_gettime(CLOCK_MONOTONIC_RAW, &time)
        return UInt64(time.tv_sec) * 1_000_000_000 + UInt64(time.tv_nsec)
    }
}
