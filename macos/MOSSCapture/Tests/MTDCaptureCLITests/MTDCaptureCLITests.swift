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

    func testCLIExplicitHandoffCopiesViewAuthorityWithoutOutputLeak() throws {
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
        try store.saveCaptureServerURL(serverURL)
        try store.saveCaptureSessionID("session-handoff")
        try store.saveCaptureViewToken("view-token-secret")
        var copiedToken: String?
        let handoff = PasteboardCapturePortalHandoff(
            sessionStore: store,
            copyViewToken: {
                copiedToken = $0
                return true
            }
        )
        let client = RecordingControlChannelClient(
            response: ControlChannelResponse(ok: true, running: false)
        )
        let standardOutput = RecordingCLIOutput()
        let standardError = RecordingCLIOutput()
        let commandLine = CaptureCommandLine(
            launcher: RecordingCaptureAppLauncher(),
            socketChecker: StaticSocketChecker(exists: true),
            client: client,
            input: StaticCLIInput(data: Data()),
            standardOutput: standardOutput,
            standardError: standardError,
            portalHandoff: handoff
        )

        XCTAssertEqual(commandLine.run(arguments: ["handoff"]), 0)

        let confirmation = try JSONDecoder().decode(
            CapturePortalHandoffConfirmation.self,
            from: standardOutput.data.dropTrailingNewline()
        )
        XCTAssertEqual(client.requests.map(\.command), ["status"])
        XCTAssertEqual(copiedToken, "view-token-secret")
        XCTAssertEqual(
            confirmation,
            CapturePortalHandoffConfirmation(
                sessionID: "session-handoff",
                portalURL: serverURL.appendingPathComponent("live")
            )
        )
        XCTAssertEqual(confirmation.viewAuthority, "copied-to-pasteboard")
        XCTAssertTrue(standardError.data.isEmpty)
        let combinedOutput = String(
            decoding: standardOutput.data + standardError.data,
            as: UTF8.self
        )
        XCTAssertFalse(combinedOutput.contains("view-token-secret"))
        XCTAssertFalse(combinedOutput.contains("?"))
        XCTAssertFalse(combinedOutput.contains("#"))
    }

    func testShimCommandsStayControlOnlyAndAudioFrameworkFree() throws {
        let source = try cliSources()

        XCTAssertTrue(source.contains("pair"))
        XCTAssertTrue(source.contains("start"))
        XCTAssertTrue(source.contains("stop"))
        XCTAssertTrue(source.contains("status"))
        XCTAssertTrue(source.contains("handoff"))
        XCTAssertTrue(source.contains("PasteboardCapturePortalHandoff"))
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

    func testProductEntrypointsShareExplicitLabStoreResolverAndKeepKeychainDefault() throws {
        let defaultStore = try CaptureSecretStoreSelection.makeDefault(environment: [:])
        XCTAssertTrue(defaultStore is KeychainCaptureSecretStore)
        let path = FileManager.default.temporaryDirectory
            .appendingPathComponent("moss-cli-store-\(UUID().uuidString)")
            .appendingPathComponent("secrets.json")
            .path
        defer { try? FileManager.default.removeItem(at: URL(fileURLWithPath: path).deletingLastPathComponent()) }
        let selectedStore = try CaptureSecretStoreSelection.makeDefault(
            environment: [CaptureSecretStoreSelection.environmentKey: path]
        )
        XCTAssertTrue(selectedStore is FileCaptureSecretStore)

        let package = packageRoot()
        let appMain = try String(
            contentsOf: package
                .appendingPathComponent("Sources")
                .appendingPathComponent("MOSSCaptureApp")
                .appendingPathComponent("main.swift"),
            encoding: .utf8
        )
        let cliMain = try String(
            contentsOf: package
                .appendingPathComponent("Sources")
                .appendingPathComponent("MTDCaptureCLI")
                .appendingPathComponent("main.swift"),
            encoding: .utf8
        )
        let coreSecurity = try String(
            contentsOf: package
                .appendingPathComponent("Sources")
                .appendingPathComponent("MOSSCaptureCore")
                .appendingPathComponent("CaptureSecurity.swift"),
            encoding: .utf8
        )

        XCTAssertTrue(appMain.contains("environmentKey: \"MOSS_CAPTURE_SECRET_STORE_PATH\""))
        XCTAssertTrue(cliMain.contains("environmentKey: \"MOSS_CAPTURE_SECRET_STORE_PATH\""))
        XCTAssertTrue(appMain.contains("keychainDefault: KeychainCaptureSecretStore()"))
        XCTAssertTrue(cliMain.contains("keychainDefault: KeychainCaptureSecretStore()"))
        XCTAssertTrue(coreSecurity.contains("MOSS_CAPTURE_SECRET_STORE_PATH"))
        XCTAssertTrue(coreSecurity.contains("keychainDefault()"))
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

private extension Data {
    func dropTrailingNewline() -> Data {
        guard last == Character("\n").asciiValue else {
            return self
        }
        return dropLast()
    }
}
