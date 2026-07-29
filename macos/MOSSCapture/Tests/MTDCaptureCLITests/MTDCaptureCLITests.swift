import Foundation
@testable import MOSSCaptureCore
import XCTest

final class MTDCaptureCLITests: XCTestCase {
    func testCLIAppLaunchDecisionAndFailureArePropagated() throws {
        let launchFailure = RecordingCaptureAppLauncher(error: CLIProbeError.launchFailed)
        let client = RecordingControlChannelClient(
            response: ControlChannelResponse(ok: true, running: false)
        )
        let standardOutput = RecordingCLIOutput()
        let standardError = RecordingCLIOutput()
        let commandLine = CaptureCommandLine(
            launcher: launchFailure,
            socketChecker: StaticSocketChecker(exists: false),
            client: client,
            input: StaticCLIInput(data: Data()),
            standardOutput: standardOutput,
            standardError: standardError
        )

        let exitCode = commandLine.run(arguments: ["status"])

        XCTAssertEqual(exitCode, 70)
        XCTAssertEqual(launchFailure.launchCount, 1)
        XCTAssertTrue(client.requests.isEmpty)
        XCTAssertTrue(standardOutput.data.isEmpty)
        XCTAssertEqual(String(data: standardError.data, encoding: .utf8), "{\"ok\":false}\n")

        let skippedLauncher = RecordingCaptureAppLauncher()
        let socketReadyClient = RecordingControlChannelClient(
            response: ControlChannelResponse(ok: true, running: false)
        )
        let readyOutput = RecordingCLIOutput()
        let socketReady = CaptureCommandLine(
            launcher: skippedLauncher,
            socketChecker: StaticSocketChecker(exists: true),
            client: socketReadyClient,
            input: StaticCLIInput(data: Data()),
            standardOutput: readyOutput,
            standardError: RecordingCLIOutput()
        )

        XCTAssertEqual(socketReady.run(arguments: ["status"]), 0)
        XCTAssertEqual(skippedLauncher.launchCount, 0)
        XCTAssertEqual(socketReadyClient.requests.map(\.command), ["status"])
        XCTAssertEqual(
            try JSONDecoder().decode(
                ControlChannelResponse.self,
                from: readyOutput.data.dropTrailingNewline()
            ),
            ControlChannelResponse(ok: true, running: false)
        )
    }

    func testLaunchServicesAdapterInvokesInjectedOpenAndPropagatesFailure() throws {
        var openedURLs: [URL] = []
        let launcher = NSWorkspaceLaunchServicesCaptureAppLauncher(
            environment: ["MOSS_CAPTURE_APP_URL": "/Applications/MOSSCapture.app"]
        ) { appURL in
            openedURLs.append(appURL)
        }

        try launcher.launch()

        XCTAssertEqual(openedURLs.map(\.path), ["/Applications/MOSSCapture.app"])
        let failing = NSWorkspaceLaunchServicesCaptureAppLauncher(
            environment: ["MOSS_CAPTURE_APP_URL": "/Applications/MOSSCapture.app"]
        ) { _ in
            throw CLIProbeError.launchFailed
        }
        XCTAssertThrowsError(try failing.launch()) { error in
            XCTAssertEqual(error as? CLIProbeError, .launchFailed)
        }
        XCTAssertThrowsError(
            try NSWorkspaceLaunchServicesCaptureAppLauncher(environment: [:]).launch()
        ) { error in
            XCTAssertEqual(error as? CaptureCLIError, .launchServicesUnavailable)
        }
    }

    func testCLIPairingPayloadCrossesStdinThroughRealUDSWithoutOutputLeak() throws {
        let socketPath = temporarySocketPath()
        let pairingPayload = Data("pairing-secret-bytes".utf8)
        let serverURL = URL(string: "https://moss.example")!
        let receivedRequest = ControlRequestBox()
        let serverFinished = expectation(description: "server received CLI pairing request")
        let server = UnixDomainControlServer(
            socketPath: socketPath,
            authenticator: SameUserUDSAuthenticator(
                secrets: FakeCaptureKeyStoreAdapter(secret: "control-secret")
            )
        ) { request in
            receivedRequest.store(request)
            return ControlChannelResponse(
                ok: true,
                running: false,
                sessionID: "session-from-app",
                portalURL: serverURL.appendingPathComponent("live")
            )
        }
        DispatchQueue.global().async {
            try? server.serveOnce()
            serverFinished.fulfill()
        }
        try waitForSocket(at: socketPath)

        let standardOutput = RecordingCLIOutput()
        let standardError = RecordingCLIOutput()
        let commandLine = CaptureCommandLine(
            launcher: RecordingCaptureAppLauncher(),
            socketChecker: StaticSocketChecker(exists: true),
            client: UnixDomainControlClient(
                socketPath: socketPath,
                secrets: FakeCaptureKeyStoreAdapter(secret: "control-secret")
            ),
            input: StaticCLIInput(data: pairingPayload),
            standardOutput: standardOutput,
            standardError: standardError
        )

        let exitCode = commandLine.run(
            arguments: ["pair", "--server", serverURL.absoluteString]
        )

        wait(for: [serverFinished], timeout: 2)
        let request = try XCTUnwrap(receivedRequest.load())
        XCTAssertEqual(exitCode, 0)
        XCTAssertEqual(request.command, "pair")
        XCTAssertEqual(request.serverURL, serverURL)
        XCTAssertEqual(request.pairingPayload, pairingPayload)
        XCTAssertEqual(
            try JSONDecoder().decode(
                ControlChannelResponse.self,
                from: standardOutput.data.dropTrailingNewline()
            ),
            ControlChannelResponse(
                ok: true,
                running: false,
                sessionID: "session-from-app",
                portalURL: serverURL.appendingPathComponent("live")
            )
        )
        XCTAssertTrue(standardError.data.isEmpty)
        let combinedOutput = standardOutput.data + standardError.data
        for secret in [
            "pairing-secret-bytes",
            "control-secret",
            "capture-bearer",
            "certificate-pin",
            "view-token",
        ] {
            XCTAssertFalse(String(decoding: combinedOutput, as: UTF8.self).contains(secret))
        }
    }

    func testCLIPrintsAppFailureResponseAndReturnsNonzeroWithoutSecretLeak() throws {
        let response = ControlChannelResponse(ok: false, error: "missingCaptureConfiguration")
        let standardOutput = RecordingCLIOutput()
        let standardError = RecordingCLIOutput()
        let commandLine = CaptureCommandLine(
            launcher: RecordingCaptureAppLauncher(),
            socketChecker: StaticSocketChecker(exists: true),
            client: RecordingControlChannelClient(response: response),
            input: StaticCLIInput(data: Data()),
            standardOutput: standardOutput,
            standardError: standardError
        )

        XCTAssertEqual(commandLine.run(arguments: ["start", "--label", "local"]), 70)
        XCTAssertEqual(
            try JSONDecoder().decode(
                ControlChannelResponse.self,
                from: standardOutput.data.dropTrailingNewline()
            ),
            response
        )
        XCTAssertTrue(standardError.data.isEmpty)
    }

    func testCLIStatusReportsBothLanesAndTheTypedCodeOfAFailedOneAcrossTheRealSocket() throws {
        let path = FileManager.default.temporaryDirectory
            .appendingPathComponent("moss-cli-lanes-\(UUID().uuidString)")
            .appendingPathComponent("secrets.json")
            .path
        defer {
            try? FileManager.default.removeItem(
                at: URL(fileURLWithPath: path).deletingLastPathComponent()
            )
        }
        let store = try FileCaptureSecretStore(path: path)
        try store.saveControlSecret("control-secret")
        let dispatcher = ControlCommandDispatcher(
            controller: CaptureController(
                source: StaticLaneStatusCaptureSource(
                    lanes: [
                        CaptureLaneStatus(
                            lane: .system,
                            sequence: 0,
                            deviceEpoch: 1,
                            state: "failed",
                            failureCode: "macos_permission_denied"
                        ),
                        CaptureLaneStatus(
                            lane: .microphone,
                            sequence: 3,
                            deviceEpoch: 1,
                            state: "capturing"
                        ),
                    ]
                ),
                transport: FakeCaptureTransportAdapter(),
                keyStore: FakeCaptureKeyStoreAdapter(),
                clock: FakeCaptureClockAdapter(),
                scheduler: FakeCaptureSchedulerAdapter(),
                health: FakeCaptureHealthAdapter()
            ),
            pairingExchange: UnusedPairingExchange()
        )
        let socketPath = temporarySocketPath()
        let serverFinished = expectation(description: "app answered the CLI status request")
        let server = UnixDomainControlServer(
            socketPath: socketPath,
            authenticator: SameUserUDSAuthenticator(secrets: store)
        ) { request in
            try dispatcher.dispatch(request)
        }
        DispatchQueue.global().async {
            try? server.serveOnce()
            serverFinished.fulfill()
        }
        try waitForSocket(at: socketPath)

        let standardOutput = RecordingCLIOutput()
        let standardError = RecordingCLIOutput()
        let commandLine = CaptureCommandLine(
            launcher: RecordingCaptureAppLauncher(),
            socketChecker: StaticSocketChecker(exists: true),
            client: UnixDomainControlClient(socketPath: socketPath, secrets: store),
            input: StaticCLIInput(data: Data()),
            standardOutput: standardOutput,
            standardError: standardError
        )

        XCTAssertEqual(commandLine.run(arguments: ["status"]), 0)

        wait(for: [serverFinished], timeout: 2)
        let printed = try JSONDecoder().decode(
            ControlChannelResponse.self,
            from: standardOutput.data.dropTrailingNewline()
        )
        XCTAssertEqual(
            printed.lanes,
            [
                ControlChannelLaneStatus(
                    lane: "system",
                    state: "failed",
                    failureCode: "macos_permission_denied"
                ),
                ControlChannelLaneStatus(lane: "microphone", state: "capturing"),
            ],
            "the lane state an operator asks for has to survive the socket, not just exist in the app"
        )
        XCTAssertTrue(standardError.data.isEmpty)
        XCTAssertFalse(
            String(decoding: standardOutput.data, as: UTF8.self).contains("control-secret")
        )
    }

    func testCLIHandoffIsOneUDSRequestAndRelaysOnlyTheAppsNonSecretConfirmation() throws {
        let path = FileManager.default.temporaryDirectory
            .appendingPathComponent("moss-cli-handoff-\(UUID().uuidString)")
            .appendingPathComponent("secrets.json")
            .path
        defer {
            try? FileManager.default.removeItem(
                at: URL(fileURLWithPath: path).deletingLastPathComponent()
            )
        }
        let store = try FileCaptureSecretStore(path: path)
        let serverURL = URL(string: "https://moss.example")!
        try store.saveControlSecret("control-secret")
        try store.saveCaptureServerURL(serverURL)
        try store.saveCaptureSessionID("session-handoff")
        try store.saveCaptureViewToken("view-token-secret")
        let copiedTokens = CopiedTokenBox()
        let dispatcher = ControlCommandDispatcher(
            controller: CaptureController.fakeForLocalDevelopment(),
            pairingExchange: UnusedPairingExchange(),
            sessionStore: store,
            portalHandoff: PasteboardCapturePortalHandoff(sessionStore: store) { viewToken in
                copiedTokens.append(viewToken)
                return true
            }
        )
        let socketPath = temporarySocketPath()
        let receivedRequest = ControlRequestBox()
        let serverFinished = expectation(description: "app answered the CLI handoff request")
        let server = UnixDomainControlServer(
            socketPath: socketPath,
            authenticator: SameUserUDSAuthenticator(secrets: store)
        ) { request in
            receivedRequest.store(request)
            return try dispatcher.dispatch(request)
        }
        DispatchQueue.global().async {
            try? server.serveOnce()
            serverFinished.fulfill()
        }
        try waitForSocket(at: socketPath)

        let standardOutput = RecordingCLIOutput()
        let standardError = RecordingCLIOutput()
        let commandLine = CaptureCommandLine(
            launcher: RecordingCaptureAppLauncher(),
            socketChecker: StaticSocketChecker(exists: true),
            client: UnixDomainControlClient(socketPath: socketPath, secrets: store),
            input: StaticCLIInput(data: Data()),
            standardOutput: standardOutput,
            standardError: standardError
        )

        XCTAssertEqual(commandLine.run(arguments: ["handoff"]), 0)

        wait(for: [serverFinished], timeout: 2)
        XCTAssertEqual(try XCTUnwrap(receivedRequest.load()).command, "handoff")
        XCTAssertEqual(copiedTokens.load(), ["view-token-secret"])
        XCTAssertEqual(
            try JSONDecoder().decode(
                ControlChannelResponse.self,
                from: standardOutput.data.dropTrailingNewline()
            ),
            ControlChannelResponse(
                ok: true,
                sessionID: "session-handoff",
                portalURL: serverURL.appendingPathComponent("live"),
                viewAuthority: "copied-to-pasteboard"
            )
        )
        XCTAssertTrue(standardError.data.isEmpty)
        let combinedOutput = String(
            decoding: standardOutput.data + standardError.data,
            as: UTF8.self
        )
        XCTAssertFalse(combinedOutput.contains("view-token-secret"))
        XCTAssertFalse(combinedOutput.contains("control-secret"))
        XCTAssertFalse(combinedOutput.contains("?"))
        XCTAssertFalse(combinedOutput.contains("#"))
    }

    func testCLILatencyRelaysOnlyTheAppsAggregateTimingsAndNeverTheViewToken() throws {
        let path = FileManager.default.temporaryDirectory
            .appendingPathComponent("moss-cli-latency-\(UUID().uuidString)")
            .appendingPathComponent("secrets.json")
            .path
        defer {
            try? FileManager.default.removeItem(
                at: URL(fileURLWithPath: path).deletingLastPathComponent()
            )
        }
        let store = try FileCaptureSecretStore(path: path)
        try store.saveControlSecret("control-secret")
        try store.saveCaptureServerURL(URL(string: "https://moss.example")!)
        try store.saveCaptureSessionID("session-latency")
        try store.saveCaptureViewToken("view-token-secret")
        let probe = StubLatencyProbe(
            report: CaptureLatencyReport(
                polling: true,
                mixerOriginResolved: true,
                sufficientSamples: true,
                committedLatency: CaptureLatencyDistribution(
                    count: 24,
                    p50MS: 1_100,
                    p95MS: 1_800,
                    maxMS: 2_400
                ),
                snapshotFetch: CaptureLatencyDistribution(count: 96, p50MS: 40, p95MS: 90, maxMS: 140),
                eventsFetch: CaptureLatencyDistribution(count: 96, p50MS: 30, p95MS: 70, maxMS: 110),
                renderBoundMS: 660,
                userVisibleMS: 2_460
            )
        )
        let dispatcher = ControlCommandDispatcher(
            controller: CaptureController.fakeForLocalDevelopment(),
            pairingExchange: UnusedPairingExchange(),
            sessionStore: store,
            latencyProbe: probe
        )
        let socketPath = temporarySocketPath()
        let receivedRequest = ControlRequestBox()
        let serverFinished = expectation(description: "app answered the CLI latency request")
        let server = UnixDomainControlServer(
            socketPath: socketPath,
            authenticator: SameUserUDSAuthenticator(secrets: store)
        ) { request in
            receivedRequest.store(request)
            return try dispatcher.dispatch(request)
        }
        DispatchQueue.global().async {
            try? server.serveOnce()
            serverFinished.fulfill()
        }
        try waitForSocket(at: socketPath)

        let standardOutput = RecordingCLIOutput()
        let standardError = RecordingCLIOutput()
        let commandLine = CaptureCommandLine(
            launcher: RecordingCaptureAppLauncher(),
            socketChecker: StaticSocketChecker(exists: true),
            client: UnixDomainControlClient(socketPath: socketPath, secrets: store),
            input: StaticCLIInput(data: Data()),
            standardOutput: standardOutput,
            standardError: standardError
        )

        XCTAssertEqual(commandLine.run(arguments: ["latency"]), 0)

        wait(for: [serverFinished], timeout: 2)
        XCTAssertEqual(try XCTUnwrap(receivedRequest.load()).command, "latency")
        XCTAssertEqual(probe.measureCount(), 1)
        let response = try JSONDecoder().decode(
            ControlChannelResponse.self,
            from: standardOutput.data.dropTrailingNewline()
        )
        // Both components of the gated number reach the operator separately.
        XCTAssertEqual(response.latency?.committedLatency.p95MS, 1_800)
        XCTAssertEqual(response.latency?.renderBoundMS, 660)
        XCTAssertEqual(response.latency?.userVisibleMS, 2_460)
        XCTAssertTrue(standardError.data.isEmpty)
        let combinedOutput = String(
            decoding: standardOutput.data + standardError.data,
            as: UTF8.self
        )
        XCTAssertFalse(combinedOutput.contains("view-token-secret"))
        XCTAssertFalse(combinedOutput.contains("control-secret"))
        XCTAssertFalse(combinedOutput.contains("session-latency"))
        XCTAssertFalse(combinedOutput.contains("moss.example"))
    }

    func testShimCommandsStayControlOnlyAndAudioFrameworkFree() throws {
        let source = try cliSources()

        XCTAssertTrue(source.contains("pair"))
        XCTAssertTrue(source.contains("start"))
        XCTAssertTrue(source.contains("stop"))
        XCTAssertTrue(source.contains("status"))
        XCTAssertTrue(source.contains("handoff"))
        XCTAssertTrue(source.contains("ControlChannelRequest(command: \"handoff\")"))
        XCTAssertTrue(source.contains("latency"))
        XCTAssertTrue(source.contains("ControlChannelRequest(command: \"latency\")"))
        XCTAssertFalse(source.contains("PasteboardCapturePortalHandoff"))
        XCTAssertFalse(source.contains("loadCaptureViewToken"))
        XCTAssertFalse(source.contains("NSPasteboard"))
        XCTAssertFalse(source.contains("CaptureLatencyProbe("))
        XCTAssertTrue(source.contains("LaunchServices"))
        XCTAssertTrue(source.contains("UnixDomainControlClient"))
        XCTAssertTrue(source.contains("sendRequest"))
        XCTAssertTrue(source.contains("readDataToEndOfFile"))
        XCTAssertTrue(source.contains("--server"))
        XCTAssertTrue(source.contains("--label"))
        XCTAssertFalse(source.contains("CoreAudio"))
        XCTAssertFalse(source.contains("AVFAudio"))
        XCTAssertFalse(source.contains("AudioHardwareCreateProcessTap"))
        XCTAssertFalse(source.contains("CaptureController.fakeForLocalDevelopment"))
        XCTAssertFalse(source.contains("capture-token"))
        XCTAssertFalse(source.contains("\"command\":\"status\""))
        XCTAssertFalse(source.contains("print(\"{\\\"ok\\\":true}\")"))
    }

    func testCLIPropagatesControlResponse() throws {
        let source = try cliSources()

        XCTAssertTrue(source.contains("writeResponse(response)"))
        XCTAssertTrue(source.contains("return response.ok ? 0 : 70"))
        XCTAssertTrue(source.contains("Foundation.exit(exitCode)"))
        XCTAssertFalse(source.contains("CoreAudio"))
        XCTAssertFalse(source.contains("AVFAudio"))
    }

    func testBundleMetadataPinsHelperContractWithoutSandbox() throws {
        let resources = packageRoot().appendingPathComponent("Resources")
        let info = try String(
            contentsOf: resources.appendingPathComponent("Info.plist"),
            encoding: .utf8
        )
        let entitlements = try String(
            contentsOf: resources.appendingPathComponent("MOSSCapture.entitlements"),
            encoding: .utf8
        )

        XCTAssertTrue(info.contains("CFBundleIdentifier"))
        XCTAssertTrue(info.contains("LSUIElement"))
        XCTAssertTrue(info.contains("LSMinimumSystemVersion"))
        XCTAssertTrue(info.contains("14.2"))
        XCTAssertTrue(info.contains("NSAudioCaptureUsageDescription"))
        XCTAssertTrue(info.contains("NSMicrophoneUsageDescription"))
        XCTAssertTrue(entitlements.contains("com.apple.security.device.audio-input"))
        XCTAssertTrue(entitlements.contains("keychain-access-groups"))
        XCTAssertFalse(entitlements.contains("com.apple.security.app-sandbox"))
    }

    func testBundleDeclaresTheTransportExceptionThePinnedClientCannotWorkWithout() throws {
        // App Transport Security applies to an `.app` bundle and not to the bare executable, and
        // it rejects this product's self-signed leaf *after* PinnedCertificateURLSessionDelegate
        // has matched the pin — NSURLErrorDomain -1200 / _kCFStreamErrorCodeKey -9802. ATS exempts
        // loopback and the RFC 1918 ranges, so no single-host test can observe this; only the
        // declaration's presence can be gated here. Parsed, not substring-matched, so the
        // explanatory comment in the plist cannot satisfy the assertions.
        let url = packageRoot()
            .appendingPathComponent("Resources")
            .appendingPathComponent("Info.plist")
        let parsed = try PropertyListSerialization.propertyList(
            from: try Data(contentsOf: url),
            options: [],
            format: nil
        )
        let info = try XCTUnwrap(parsed as? [String: Any])
        let transport = try XCTUnwrap(
            info["NSAppTransportSecurity"] as? [String: Any],
            "without this key the app cannot reach the live server at all"
        )
        XCTAssertEqual(transport["NSAllowsArbitraryLoads"] as? Bool, true)
        // Declaring NSAllowsLocalNetworking or either NSAllowsArbitraryLoadsIn* sibling makes the
        // OS ignore NSAllowsArbitraryLoads, which would silently restore the -1200.
        XCTAssertEqual(
            Array(transport.keys),
            ["NSAllowsArbitraryLoads"],
            "a sibling key here disables the exception this product depends on"
        )
    }

    func testProductEntrypointsResolveOneSharedPrivateFileStoreByDefault() throws {
        let home = FileManager.default.temporaryDirectory
            .appendingPathComponent("moss-home-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: home, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: home) }
        let expectedPath = home
            .appendingPathComponent("Library")
            .appendingPathComponent("Application Support")
            .appendingPathComponent("MOSSCapture")
            .appendingPathComponent("secrets.json")
            .path

        XCTAssertEqual(
            CaptureSecretStoreSelection.defaultPath(homeDirectory: home.path),
            expectedPath
        )

        // the app composition root and the CLI composition root, resolved independently
        let appStore = try CaptureSecretStoreSelection.makeDefault(
            environment: [:],
            homeDirectory: home.path
        )
        let cliStore = try CaptureSecretStoreSelection.makeDefault(
            environment: [:],
            homeDirectory: home.path
        )
        XCTAssertEqual((appStore as? FileCaptureSecretStore)?.path, expectedPath)
        XCTAssertEqual((cliStore as? FileCaptureSecretStore)?.path, expectedPath)
        try appStore.saveCaptureBearerToken("capture-token")
        try appStore.saveCaptureSessionID("session-shared")
        XCTAssertEqual(try cliStore.loadCaptureBearerToken(), "capture-token")
        XCTAssertEqual(try cliStore.loadCaptureSessionID(), "session-shared")
        XCTAssertEqual(try cliStore.loadDeviceID(), try appStore.loadDeviceID())

        // the environment override still wins; that is what the tracer and lab runs select
        let overridePath = home
            .appendingPathComponent("override")
            .appendingPathComponent("secrets.json")
            .path
        let overridden = try CaptureSecretStoreSelection.makeDefault(
            environment: [CaptureSecretStoreSelection.environmentKey: overridePath],
            homeDirectory: home.path
        )
        XCTAssertEqual((overridden as? FileCaptureSecretStore)?.path, overridePath)
        XCTAssertNil(try overridden.loadCaptureBearerToken())
    }

    func testNeitherProductEntrypointCanSelectTheDormantKeychainStore() throws {
        let package = packageRoot()
        func read(_ target: String, _ file: String) throws -> String {
            try String(
                contentsOf: package
                    .appendingPathComponent("Sources")
                    .appendingPathComponent(target)
                    .appendingPathComponent(file),
                encoding: .utf8
            )
        }
        let appMain = try read("MOSSCaptureApp", "main.swift")
        let cliMain = try read("MTDCaptureCLI", "main.swift")
        let coreSecurity = try read("MOSSCaptureCore", "CaptureSecurity.swift")

        for source in [appMain, cliMain] {
            XCTAssertTrue(source.contains("CaptureSecretStoreSelection.makeDefault()"))
            XCTAssertFalse(source.contains("KeychainCaptureSecretStore"))
            XCTAssertFalse(source.contains("MOSS_CAPTURE_SECRET_STORE_PATH"))
        }
        XCTAssertTrue(coreSecurity.contains("MOSS_CAPTURE_SECRET_STORE_PATH"))
        XCTAssertFalse(coreSecurity.contains("com.alphasight.moss.capture.shared"))
        XCTAssertFalse(coreSecurity.contains("kSecAttrAccessGroup"))
    }

    private func packageRoot() -> URL {
        var url = URL(fileURLWithPath: #filePath)
        for _ in 0..<3 {
            url.deleteLastPathComponent()
        }
        return url
    }

    private func cliSources() throws -> String {
        let package = packageRoot()
        let paths = [
            package
                .appendingPathComponent("Sources")
                .appendingPathComponent("MTDCaptureCLI")
                .appendingPathComponent("main.swift"),
            package
                .appendingPathComponent("Sources")
                .appendingPathComponent("MOSSCaptureCore")
                .appendingPathComponent("CaptureCommandLine.swift"),
        ]
        return try paths.map {
            try String(contentsOf: $0, encoding: .utf8)
        }.joined(separator: "\n")
    }

    private func temporarySocketPath() -> String {
        FileManager.default.temporaryDirectory
            .appendingPathComponent("moss-cli-\(UUID().uuidString).sock")
            .path
    }

    private func waitForSocket(at path: String) throws {
        let deadline = Date(timeIntervalSinceNow: 2)
        while Date() < deadline {
            if FileManager.default.fileExists(atPath: path) {
                return
            }
            Thread.sleep(forTimeInterval: 0.01)
        }
        XCTFail("socket was not created")
    }
}

private enum CLIProbeError: Error, Equatable {
    case launchFailed
}

private final class RecordingCaptureAppLauncher: CaptureAppLaunching {
    private let error: Error?
    private(set) var launchCount = 0

    init(error: Error? = nil) {
        self.error = error
    }

    func launch() throws {
        launchCount += 1
        if let error {
            throw error
        }
    }
}

private struct StaticSocketChecker: ControlSocketChecking {
    let exists: Bool

    func fileExists(atPath path: String) -> Bool {
        exists
    }
}

private final class RecordingControlChannelClient: ControlChannelRequestSending {
    let socketPath = "/tmp/moss-cli-test.sock"
    private let response: ControlChannelResponse
    private(set) var requests: [ControlChannelRequest] = []

    init(response: ControlChannelResponse) {
        self.response = response
    }

    func sendRequest(_ request: ControlChannelRequest) throws -> ControlChannelResponse {
        requests.append(request)
        return response
    }
}

private struct StaticCLIInput: CaptureCLIInput {
    let data: Data

    func readAll() -> Data {
        data
    }
}

private final class RecordingCLIOutput: CaptureCLIOutput {
    private(set) var data = Data()

    func write(_ data: Data) throws {
        self.data.append(data)
    }
}

private final class StaticLaneStatusCaptureSource: CaptureSourceAdapter {
    private let lanes: [CaptureLaneStatus]

    init(lanes: [CaptureLaneStatus]) {
        self.lanes = lanes
    }

    func start(configuration: CaptureConfiguration) throws {}

    func pendingFrames() throws -> [CaptureFrame] {
        []
    }

    func status() -> [CaptureLaneStatus] {
        lanes
    }

    func stop(deadline: Date) throws {}
}

private struct UnusedPairingExchange: CapturePairingExchangeAdapter {
    func pair(serverURL: URL, pairingPayload: Data) throws -> CapturePairingResult {
        throw CLIProbeError.launchFailed
    }
}

private final class CopiedTokenBox: @unchecked Sendable {
    private let lock = NSLock()
    private var tokens: [String] = []

    func append(_ token: String) {
        lock.lock()
        tokens.append(token)
        lock.unlock()
    }

    func load() -> [String] {
        lock.lock()
        defer { lock.unlock() }
        return tokens
    }
}

private final class ControlRequestBox: @unchecked Sendable {
    private let lock = NSLock()
    private var request: ControlChannelRequest?

    func store(_ request: ControlChannelRequest) {
        lock.lock()
        self.request = request
        lock.unlock()
    }

    func load() -> ControlChannelRequest? {
        lock.lock()
        defer { lock.unlock() }
        return request
    }
}

private final class StubLatencyProbe: CaptureLatencyProbing, @unchecked Sendable {
    private let lock = NSLock()
    private let report: CaptureLatencyReport
    private var measures = 0

    init(report: CaptureLatencyReport) {
        self.report = report
    }

    func measure() throws -> CaptureLatencyReport {
        lock.lock()
        measures += 1
        lock.unlock()
        return report
    }

    func stop() {}

    func measureCount() -> Int {
        lock.lock()
        defer { lock.unlock() }
        return measures
    }
}

private extension Data {
    func dropTrailingNewline() -> Data {
        guard last == Character("\n").asciiValue else {
            return self
        }
        return dropLast()
    }
}
