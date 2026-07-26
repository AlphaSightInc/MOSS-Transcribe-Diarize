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
        let keyStore = KeychainCaptureSecretStore()
        try ensureControlSecret(in: keyStore)
        let controller = CaptureController(
            source: NativeDualCaptureSource(),
            transport: CaptureV2HTTPTransportAdapter(
                client: URLSessionCaptureHTTPClient(),
                bearerToken: keyStore
            ),
            keyStore: keyStore,
            clock: SystemCaptureClockAdapter(),
            scheduler: RepeatingCaptureSchedulerAdapter(interval: 0.25),
            health: CaptureHTTPHealthAdapter(
                client: URLSessionCaptureHTTPClient(),
                bearerToken: keyStore,
                instanceID: ProcessInfo.processInfo.globallyUniqueString,
                helperVersion: "0.1.0"
            )
        )
        let dispatcher = ControlCommandDispatcher(
            controller: controller,
            pairingExchange: URLSessionCapturePairingExchangeAdapter(),
            captureTokenStore: keyStore
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

    private static func ensureControlSecret(in keyStore: KeychainCaptureSecretStore) throws {
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

final class RepeatingCaptureSchedulerAdapter: CaptureSchedulerAdapter {
    private let interval: TimeInterval

    init(interval: TimeInterval) {
        self.interval = interval
    }

    func schedule(label: String, operation: @escaping () -> Void) -> CaptureCancellation {
        let timer = DispatchSource.makeTimerSource(queue: DispatchQueue(label: label))
        timer.schedule(deadline: .now() + interval, repeating: interval)
        timer.setEventHandler {
            operation()
        }
        timer.resume()
        return TimerCancellation(timer: timer)
    }
}

final class TimerCancellation: CaptureCancellation {
    private let timer: DispatchSourceTimer

    init(timer: DispatchSourceTimer) {
        self.timer = timer
    }

    func cancel() {
        timer.cancel()
    }
}
