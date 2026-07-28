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
        let keyStore = try CaptureSecretStoreSelection.makeDefault()
        try ensureControlSecret(in: keyStore)
        // One provider for the whole process, so frames, heartbeats and pairing share a single
        // pinned session per pin instead of opening one per request.
        let httpClients = PinnedURLSessionCaptureHTTPClientProvider()
        let controller = CaptureController(
            source: NativeDualCaptureSource(),
            transport: CaptureV2HTTPTransportAdapter(
                clientProvider: httpClients,
                certificatePin: keyStore,
                bearerToken: keyStore
            ),
            keyStore: keyStore,
            clock: SystemCaptureClockAdapter(),
            scheduler: RepeatingCaptureSchedulerAdapter(interval: CapturePumpContract.interval),
            health: CaptureHTTPHealthAdapter(
                clientProvider: httpClients,
                certificatePin: keyStore,
                bearerToken: keyStore,
                instanceID: ProcessInfo.processInfo.globallyUniqueString,
                helperVersion: "0.1.0"
            )
        )
        let dispatcher = ControlCommandDispatcher(
            controller: controller,
            pairingExchange: URLSessionCapturePairingExchangeAdapter(
                clientProvider: httpClients,
                deviceIdentity: keyStore
            ),
            captureTokenStore: keyStore,
            certificatePinStore: keyStore,
            sessionStore: keyStore,
            portalHandoff: PasteboardCapturePortalHandoff(sessionStore: keyStore)
        )
        return ProductionCaptureRuntime(
            server: UnixDomainControlServer(
                socketPath: ControlSocketDefaults.socketPath(),
                authenticator: SameUserUDSAuthenticator(secrets: keyStore),
                handler: dispatcher.dispatch
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
