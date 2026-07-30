import AppKit
import Foundation
import Darwin
import MOSSCaptureCore
import Security

@main
struct MOSSCaptureAppMain {
    static func main() {
        if CommandLine.arguments.dropFirst() == [SystemAudioPermissionSignal.commandArgument] {
            do {
                try SystemAudioPermissionSignal.run()
            } catch {
                Foundation.exit(71)
            }
            return
        }
        do {
            let application = NSApplication.shared
            let delegate = MOSSCaptureApplicationDelegate(
                runtime: try ProductionCaptureRuntime.makeDefault()
            )
            application.delegate = delegate
            application.run()
            withExtendedLifetime(delegate) {}
        } catch {
            Foundation.exit(70)
        }
    }
}

/// Keeps Launch Services responsive while the blocking local control server runs off-main.
///
/// `LSUIElement` hides the agent from the Dock and Force Quit, so AppKit is also the only path by
/// which Finder can observe a completed launch and deliver a normal terminate or reopen event.
final class MOSSCaptureApplicationDelegate: NSObject, NSApplicationDelegate, @unchecked Sendable {
    private let runtime: ProductionCaptureRuntime

    init(runtime: ProductionCaptureRuntime) {
        self.runtime = runtime
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        DispatchQueue.global(qos: .userInitiated).async { [self] in
            do {
                try runtime.serve()
            } catch {
                Foundation.exit(70)
            }
        }
    }

    func applicationShouldHandleReopen(
        _ sender: NSApplication,
        hasVisibleWindows flag: Bool
    ) -> Bool {
        true
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
        let clock = SystemCaptureClockAdapter()
        // Built before the controller because the measurement's origin is the first capture instant
        // of the session: it has to be watching from the first acknowledged frame, not from whenever
        // an operator first asks for a figure.
        let latencySampler = CaptureLatencySampler()
        // This app is LSUIElement and Launch Services gives it no usable stderr, so a failure it
        // does not put in the unified log is a failure nobody can reconstruct. One log for both
        // kinds, so one `log show` predicate answers "why did the meeting stop".
        let failureLog = OSLogControlChannelFailureLog()
        let controller = CaptureController(
            source: NativeDualCaptureSource(),
            transport: CaptureV2HTTPTransportAdapter(
                clientProvider: httpClients,
                certificatePin: keyStore,
                bearerToken: keyStore
            ),
            keyStore: keyStore,
            clock: clock,
            scheduler: RepeatingCaptureSchedulerAdapter(interval: CapturePumpContract.interval),
            // Wrapped, so every lane failure is recorded on its way to the server — including the
            // ones the server never receives.
            health: LaneFailureLoggingHealthAdapter(
                wrapping: CaptureHTTPHealthAdapter(
                    clientProvider: httpClients,
                    certificatePin: keyStore,
                    bearerToken: keyStore,
                    instanceID: ProcessInfo.processInfo.globallyUniqueString,
                    helperVersion: "0.1.0"
                ),
                log: failureLog
            ),
            frameObserver: latencySampler,
            // Without this the meeting ends only on this Mac and the server holds the session — and
            // the view authority — until the helper lease expires.
            sessionStop: CaptureHTTPSessionStopAdapter(
                clientProvider: httpClients,
                certificatePin: keyStore,
                bearerToken: keyStore
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
            portalHandoff: PasteboardCapturePortalHandoff(sessionStore: keyStore),
            // The probe reads view authority from the same app-only store the handoff uses; it
            // polls nothing until an operator asks for a figure.
            latencyProbe: CaptureLatencyProbe(
                sampler: latencySampler,
                status: { controller.status() },
                sessionStore: keyStore,
                clientProvider: httpClients,
                certificatePin: keyStore,
                clock: clock,
                scheduler: RepeatingCaptureSchedulerAdapter(
                    interval: CaptureLatencyContract.pollInterval
                )
            )
        )
        return ProductionCaptureRuntime(
            server: UnixDomainControlServer(
                socketPath: ControlSocketDefaults.socketPath(),
                authenticator: SameUserUDSAuthenticator(secrets: keyStore),
                failureLog: failureLog,
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
