import CryptoKit
import Foundation
import Security
@testable import MOSSCaptureCore
import XCTest

final class CaptureControllerTests: XCTestCase {
    func testStartStatusStopPublishesIndependentFakeLaneFrames() throws {
        let systemFrame = CaptureFrame(
            lane: .system,
            sequence: 0,
            sampleRate: 16_000,
            sampleCount: 2,
            captureTimestampNS: 10,
            deviceEpoch: 1,
            silent: false,
            discontinuity: false,
            pcm16: Data([1, 0, 2, 0])
        )
        let microphoneFrame = CaptureFrame(
            lane: .microphone,
            sequence: 0,
            sampleRate: 16_000,
            sampleCount: 2,
            captureTimestampNS: 12,
            deviceEpoch: 7,
            silent: true,
            discontinuity: false,
            pcm16: Data([0, 0, 0, 0])
        )
        let source = FakeCaptureSourceAdapter(frames: [systemFrame, microphoneFrame])
        let transport = FakeCaptureTransportAdapter()
        let scheduler = FakeCaptureSchedulerAdapter()
        let health = FakeCaptureHealthAdapter()
        let controller = CaptureController(
            source: source,
            transport: transport,
            keyStore: FakeCaptureKeyStoreAdapter(),
            clock: FakeCaptureClockAdapter(ticks: [100]),
            scheduler: scheduler,
            health: health
        )
        let configuration = CaptureConfiguration(
            sessionID: "session-a",
            serverURL: URL(string: "https://127.0.0.1/live")!,
            label: "local"
        )

        let started = try controller.start(configuration: configuration)
        let current = controller.status()
        let stopped = try controller.stop(deadline: Date(timeIntervalSince1970: 1))

        XCTAssertTrue(started.running)
        XCTAssertEqual(started.sessionID, "session-a")
        XCTAssertEqual(started.publishedFrameCount, 2)
        XCTAssertEqual(current.lanes.map(\.lane), [.system, .microphone])
        XCTAssertEqual(current.lanes.first { $0.lane == .system }?.deviceEpoch, 1)
        XCTAssertEqual(current.lanes.first { $0.lane == .microphone }?.deviceEpoch, 7)
        XCTAssertEqual(transport.publishedFrames.map(\.lane), [.system, .microphone])
        XCTAssertEqual(transport.publishedFrames.map(\.sequence), [0, 0])
        XCTAssertEqual(transport.sessionIDs, ["session-a", "session-a"])
        XCTAssertEqual(health.emissions.count, 1)
        XCTAssertEqual(health.emissions.first?.configuration, configuration)
        XCTAssertEqual(health.emissions.first?.sentMonotonicNS, 100)
        XCTAssertEqual(scheduler.labels, ["moss.capture.pump"])
        XCTAssertFalse(stopped.running)
        XCTAssertNil(controller.status().sessionID)
    }

    func testContinuousPumpPublishesAcrossTicks() throws {
        let firstSystem = CaptureFrame(
            lane: CaptureLane.system,
            sequence: 0,
            sampleRate: 16_000,
            sampleCount: 1,
            captureTimestampNS: 10,
            deviceEpoch: 1,
            silent: false,
            discontinuity: false,
            pcm16: Data([1, 0])
        )
        let firstMicrophone = CaptureFrame(
            lane: CaptureLane.microphone,
            sequence: 0,
            sampleRate: 16_000,
            sampleCount: 1,
            captureTimestampNS: 20,
            deviceEpoch: 7,
            silent: true,
            discontinuity: false,
            pcm16: Data([0, 0])
        )
        let secondSystem = CaptureFrame(
            lane: CaptureLane.system,
            sequence: 1,
            sampleRate: 16_000,
            sampleCount: 1,
            captureTimestampNS: 30,
            deviceEpoch: 1,
            silent: false,
            discontinuity: false,
            pcm16: Data([2, 0])
        )
        let secondMicrophone = CaptureFrame(
            lane: CaptureLane.microphone,
            sequence: 1,
            sampleRate: 16_000,
            sampleCount: 1,
            captureTimestampNS: 40,
            deviceEpoch: 7,
            silent: false,
            discontinuity: true,
            pcm16: Data([3, 0])
        )
        let source = FakeCaptureSourceAdapter(frames: [firstSystem])
        let transport = FakeCaptureTransportAdapter()
        let scheduler = FakeCaptureSchedulerAdapter()
        let health = FakeCaptureHealthAdapter()
        let controller = CaptureController(
            source: source,
            transport: transport,
            keyStore: FakeCaptureKeyStoreAdapter(),
            clock: FakeCaptureClockAdapter(ticks: [100, 200, 300, 400]),
            scheduler: scheduler,
            health: health
        )
        let configuration = CaptureConfiguration(
            sessionID: "session-a",
            serverURL: URL(string: "https://127.0.0.1/live")!
        )

        try controller.start(configuration: configuration)
        source.enqueue(frames: [firstMicrophone, secondSystem])
        try scheduler.runScheduledOperation()
        source.enqueue(frames: [secondMicrophone])
        try scheduler.runScheduledOperation()
        try scheduler.runScheduledOperation()

        XCTAssertEqual(
            transport.publishedFrames.map(\.lane),
            [CaptureLane.system, CaptureLane.microphone, CaptureLane.system, CaptureLane.microphone]
        )
        XCTAssertEqual(transport.publishedFrames.map(\.sequence), [0, 0, 1, 1])
        XCTAssertEqual(transport.publishedFrames.map(\.captureTimestampNS), [10, 20, 30, 40])
        XCTAssertEqual(health.emissions.map(\.sentMonotonicNS), [100, 200, 300, 400])
        XCTAssertEqual(health.emissions.map(\.status.publishedFrameCount), [1, 3, 4, 4])
        XCTAssertEqual(controller.status().publishedFrameCount, 4)
    }

    func testStartRequiresControlSecretAndRejectsSecondStart() throws {
        let configuration = CaptureConfiguration(
            sessionID: "session-a",
            serverURL: URL(string: "https://127.0.0.1/live")!
        )
        let missingSecret = CaptureController(
            source: FakeCaptureSourceAdapter(frames: []),
            transport: FakeCaptureTransportAdapter(),
            keyStore: FakeCaptureKeyStoreAdapter(secret: nil),
            clock: FakeCaptureClockAdapter(),
            scheduler: FakeCaptureSchedulerAdapter(),
            health: FakeCaptureHealthAdapter()
        )
        XCTAssertThrowsError(try missingSecret.start(configuration: configuration)) { error in
            XCTAssertEqual(error as? CaptureControllerError, .missingControlSecret)
        }

        let controller = CaptureController.fakeForLocalDevelopment()
        try controller.start(configuration: configuration)
        XCTAssertThrowsError(try controller.start(configuration: configuration)) { error in
            XCTAssertEqual(error as? CaptureControllerError, .alreadyRunning)
        }
    }

    func testNativeSourceVectorsUseRequiredMacOSCapturePaths() throws {
        let system = SystemAudioTap()
        let description = system.makeTapDescription(name: "test")

        XCTAssertTrue(description.isPrivate)
        XCTAssertEqual(description.muteBehavior, .unmuted)
        XCTAssertTrue(description.isExclusive)
        XCTAssertTrue(description.isMixdown)
        XCTAssertEqual(SystemAudioTap.sourceVector.processTapFunction, "AudioHardwareCreateProcessTap")
        XCTAssertEqual(SystemAudioTap.sourceVector.halCallbackFunction, "AudioDeviceCreateIOProcIDWithBlock")
        XCTAssertEqual(SystemAudioTap.sourceVector.aggregateDevice, "private transient aggregate")
        XCTAssertEqual(MicrophoneCapture.sourceVector.engine, "AVAudioEngine")
        XCTAssertEqual(MicrophoneCapture.sourceVector.input, "inputNode")
        XCTAssertEqual(MicrophoneCapture.sourceVector.tap, "installTap")
    }

    func testRealtimeQueueIsBoundedAndFrameEmitterKeepsLaneStateIndependent() throws {
        let queue = RealTimeNativeAudioBufferQueue(capacity: 2)
        queue.enqueueFromRealtimeCallback(
            NativeCapturedAudioBuffer(
                lane: .system,
                sampleRate: 16_000,
                channelCount: 1,
                frameCount: 1,
                firstSampleMonotonicNS: 10,
                deviceEpoch: 1,
                discontinuity: false,
                samples: [0.25]
            )
        )
        queue.enqueueFromRealtimeCallback(
            NativeCapturedAudioBuffer(
                lane: .microphone,
                sampleRate: 16_000,
                channelCount: 1,
                frameCount: 1,
                firstSampleMonotonicNS: 11,
                deviceEpoch: 7,
                discontinuity: false,
                samples: [0]
            )
        )
        queue.enqueueFromRealtimeCallback(
            NativeCapturedAudioBuffer(
                lane: .system,
                sampleRate: 16_000,
                channelCount: 1,
                frameCount: 1,
                firstSampleMonotonicNS: 12,
                deviceEpoch: 1,
                discontinuity: true,
                samples: [-0.25]
            )
        )

        let emitter = NativeLaneFrameEmitter()
        let frames = emitter.frames(from: queue.drain())

        XCTAssertEqual(queue.droppedBuffers, 1)
        XCTAssertEqual(frames.map(\.lane), [.microphone, .system])
        XCTAssertEqual(frames.map(\.sequence), [0, 0])
        XCTAssertEqual(frames.map(\.deviceEpoch), [7, 1])
        XCTAssertEqual(frames.map(\.captureTimestampNS), [11, 12])
        XCTAssertEqual(frames.map(\.silent), [true, false])
        XCTAssertEqual(frames.map(\.discontinuity), [false, true])
        XCTAssertEqual(frames.map(\.sampleCount), [1, 1])
        XCTAssertEqual(frames.map(\.pcm16.count), [2, 2])

        let nextSystem = emitter.frames(
            from: [
                NativeCapturedAudioBuffer(
                    lane: .system,
                    sampleRate: 16_000,
                    channelCount: 1,
                    frameCount: 1,
                    firstSampleMonotonicNS: 13,
                    deviceEpoch: 1,
                    discontinuity: false,
                    samples: [0.5]
                )
            ]
        )
        XCTAssertEqual(nextSystem.first?.sequence, 1)
    }

    func testRealtimeCallbacksOnlyCopyAndEnqueueNativeBuffers() throws {
        let root = packageRoot()
        let system = try String(
            contentsOf: root.appendingPathComponent("Sources/MOSSCaptureCore/SystemAudioTap.swift"),
            encoding: .utf8
        )
        let microphone = try String(
            contentsOf: root.appendingPathComponent("Sources/MOSSCaptureCore/MicrophoneCapture.swift"),
            encoding: .utf8
        )
        let callbackSources = system + microphone

        XCTAssertTrue(callbackSources.contains("enqueueFromRealtimeCallback"))
        XCTAssertFalse(callbackSources.contains("URLSession"))
        XCTAssertFalse(callbackSources.contains("SecItemAdd"))
        XCTAssertFalse(callbackSources.contains("FileHandle"))
        XCTAssertFalse(callbackSources.contains("print("))
        XCTAssertFalse(callbackSources.contains("JSONEncoder"))
    }

    func testHTTPTransportPostsStrictV2FramesWithBearerHeaderOnly() throws {
        let client = RecordingCaptureHTTPClient()
        let transport = CaptureV2HTTPTransportAdapter(
            client: client,
            bearerToken: StaticCaptureBearerTokenAdapter(token: "capture-token")
        )
        let configuration = CaptureConfiguration(
            sessionID: "session-a",
            serverURL: URL(string: "https://moss.example")!
        )

        try transport.publish(
            frame: CaptureFrame(
                lane: .system,
                sequence: 3,
                sampleRate: 16_000,
                sampleCount: 2,
                captureTimestampNS: 123,
                deviceEpoch: 9,
                silent: false,
                discontinuity: true,
                pcm16: Data([1, 0, 2, 0])
            ),
            configuration: configuration
        )

        let request = try XCTUnwrap(client.requests.first)
        let body = try jsonBody(request)
        XCTAssertEqual(request.httpMethod, "POST")
        XCTAssertEqual(request.url?.absoluteString, "https://moss.example/api/live/sessions/session-a/frames")
        XCTAssertNil(request.url?.query)
        XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer capture-token")
        XCTAssertEqual(request.value(forHTTPHeaderField: "Content-Type"), "application/json")
        XCTAssertEqual(Set(body.keys), [
            "lane",
            "sequence",
            "capture_timestamp_ns",
            "device_epoch",
            "silent",
            "discontinuity",
            "sample_rate",
            "sample_count",
            "pcm_base64",
        ])
        XCTAssertEqual(body["lane"] as? String, "system")
        XCTAssertEqual(body["sequence"] as? Int, 3)
        XCTAssertEqual(body["capture_timestamp_ns"] as? Int, 123)
        XCTAssertEqual(body["device_epoch"] as? Int, 9)
        XCTAssertEqual(body["silent"] as? Bool, false)
        XCTAssertEqual(body["discontinuity"] as? Bool, true)
        XCTAssertEqual(body["sample_rate"] as? Int, 16_000)
        XCTAssertEqual(body["sample_count"] as? Int, 2)
        XCTAssertEqual(body["pcm_base64"] as? String, Data([1, 0, 2, 0]).base64EncodedString())
        XCTAssertFalse(String(data: request.httpBody ?? Data(), encoding: .utf8)?.contains("capture-token") ?? true)
    }

    func testHTTPHealthPostsVersionedHeartbeatWithoutBearerLeakage() throws {
        let client = RecordingCaptureHTTPClient()
        let health = CaptureHTTPHealthAdapter(
            client: client,
            bearerToken: StaticCaptureBearerTokenAdapter(token: "capture-token"),
            instanceID: "boot-a",
            helperVersion: "0.1.0"
        )
        let configuration = CaptureConfiguration(
            sessionID: "session-a",
            serverURL: URL(string: "https://moss.example")!
        )
        let status = CaptureStatus(
            running: true,
            sessionID: "session-a",
            lanes: [
                CaptureLaneStatus(lane: .system, sequence: 4, deviceEpoch: 2, state: "capturing"),
                CaptureLaneStatus(lane: .microphone, sequence: 6, deviceEpoch: 8, state: "capturing"),
            ],
            publishedFrameCount: 10,
            lastHealthSequence: 5
        )

        try health.emit(status: status, configuration: configuration, sentMonotonicNS: 900)

        let request = try XCTUnwrap(client.requests.first)
        let body = try jsonBody(request)
        let lanes = try XCTUnwrap(body["lanes"] as? [String: [String: Any]])
        let system = try XCTUnwrap(lanes["system"])
        let microphone = try XCTUnwrap(lanes["microphone"])
        XCTAssertEqual(request.url?.absoluteString, "https://moss.example/api/live/sessions/session-a/heartbeat")
        XCTAssertNil(request.url?.query)
        XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer capture-token")
        XCTAssertEqual(Set(body.keys), [
            "schema",
            "instance_id",
            "sequence",
            "sent_monotonic_ns",
            "helper_version",
            "state",
            "lanes",
        ])
        XCTAssertEqual(body["schema"] as? String, "moss-live-helper-health.v1")
        XCTAssertEqual(body["instance_id"] as? String, "boot-a")
        XCTAssertEqual(body["sequence"] as? Int, 5)
        XCTAssertEqual(body["sent_monotonic_ns"] as? Int, 900)
        XCTAssertEqual(body["helper_version"] as? String, "0.1.0")
        XCTAssertEqual(body["state"] as? String, "capturing")
        XCTAssertEqual(Set(lanes.keys), ["system", "microphone"])
        XCTAssertEqual(system["device_epoch"] as? Int, 2)
        XCTAssertEqual(microphone["device_epoch"] as? Int, 8)
        XCTAssertTrue(system["failure_code"] is NSNull)
        XCTAssertTrue(microphone["failure_code"] is NSNull)
        XCTAssertFalse(String(data: request.httpBody ?? Data(), encoding: .utf8)?.contains("capture-token") ?? true)
    }

    func testHTTPTransportRejectsMissingBearerBeforeRequest() throws {
        let client = RecordingCaptureHTTPClient()
        let transport = CaptureV2HTTPTransportAdapter(
            client: client,
            bearerToken: StaticCaptureBearerTokenAdapter(token: nil)
        )

        XCTAssertThrowsError(
            try transport.publish(
                frame: CaptureFrame(
                    lane: .system,
                    sequence: 0,
                    sampleRate: 16_000,
                    sampleCount: 1,
                    captureTimestampNS: 0,
                    deviceEpoch: 0,
                    silent: true,
                    discontinuity: false,
                    pcm16: Data([0, 0])
                ),
                configuration: CaptureConfiguration(
                    sessionID: "session-a",
                    serverURL: URL(string: "https://moss.example")!
                )
            )
        ) { error in
            XCTAssertEqual(error as? CaptureHTTPTransportError, .missingCaptureBearer)
        }
        XCTAssertTrue(client.requests.isEmpty)
    }

    func testSecurityAdaptersExposeKeychainFullCertificatePinAndUDSInventory() throws {
        let source = try String(
            contentsOf: packageRoot()
                .appendingPathComponent("Sources")
                .appendingPathComponent("MOSSCaptureCore")
                .appendingPathComponent("CaptureSecurity.swift"),
            encoding: .utf8
        )

        XCTAssertTrue(source.contains("SecItemAdd"))
        XCTAssertTrue(source.contains("SecItemCopyMatching"))
        XCTAssertTrue(source.contains("SecCertificateCopyData"))
        XCTAssertTrue(source.contains("SHA256"))
        XCTAssertTrue(source.contains("AF_UNIX"))
        XCTAssertTrue(source.contains("SOCK_STREAM"))
        XCTAssertTrue(source.contains("LOCAL_PEERCRED"))
        XCTAssertTrue(source.contains("constantTimeEquals"))
    }

    func testFullCertificatePinValidatorRequiresExactValidSHA256() throws {
        let certificate = try testCertificate()
        let certificateData = SecCertificateCopyData(certificate) as Data
        let expectedHash = SHA256.hash(data: certificateData)
            .map { String(format: "%02x", $0) }
            .joined()
        let replacementLastByte = expectedHash.hasSuffix("00") ? "ff" : "00"
        let singleByteMismatch = expectedHash.dropLast(2) + replacementLastByte
        let validator = FullCertificatePinValidator()

        XCTAssertNoThrow(
            try validator.validate(
                certificate: certificate,
                expectedSHA256Hex: expectedHash.uppercased()
            )
        )
        XCTAssertThrowsError(
            try validator.validate(
                certificate: certificate,
                expectedSHA256Hex: String(singleByteMismatch)
            )
        ) { error in
            XCTAssertEqual(error as? CaptureSecurityError, .pinMismatch)
        }
        for invalidHash in [
            String(repeating: "0", count: 63),
            String(repeating: "g", count: 64),
        ] {
            XCTAssertThrowsError(
                try validator.validate(
                    certificate: certificate,
                    expectedSHA256Hex: invalidHash
                )
            ) { error in
                XCTAssertEqual(error as? CaptureSecurityError, .invalidPinnedHash)
            }
        }
    }

    func testCaptureControllerPublicInterfaceIsLimitedToStartStatusStop() throws {
        let source = try String(
            contentsOf: packageRoot()
                .appendingPathComponent("Sources")
                .appendingPathComponent("MOSSCaptureCore")
                .appendingPathComponent("CaptureController.swift"),
            encoding: .utf8
        )
        let classStart = try XCTUnwrap(
            source.range(of: "public final class CaptureController {")
        )
        let controllerSource = String(source[classStart.lowerBound...])
        let declarationLine = try XCTUnwrap(
            controllerSource.split(separator: "\n", maxSplits: 1).first
        )
        let methodPattern = try NSRegularExpression(
            pattern: #"\bpublic\s+func\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("#
        )
        let methodMatches = methodPattern.matches(
            in: controllerSource,
            range: NSRange(controllerSource.startIndex..., in: controllerSource)
        )
        let methodNames = methodMatches.compactMap { match -> String? in
            guard let range = Range(match.range(at: 1), in: controllerSource) else {
                return nil
            }
            return String(controllerSource[range])
        }
        let initPattern = try NSRegularExpression(pattern: #"\bpublic\s+init\s*\("#)
        let initMatches = initPattern.matches(
            in: controllerSource,
            range: NSRange(controllerSource.startIndex..., in: controllerSource)
        )
        let storagePattern = try NSRegularExpression(
            pattern: #"\bpublic(?:\s+private\(set\))?\s+(?:var|let)\s+[A-Za-z_][A-Za-z0-9_]*"#
        )
        let storageMatches = storagePattern.matches(
            in: controllerSource,
            range: NSRange(controllerSource.startIndex..., in: controllerSource)
        )
        let publicSubscriptPattern = try NSRegularExpression(
            pattern: #"\bpublic\s+subscript\s*\("#
        )
        let publicSubscriptMatches = publicSubscriptPattern.matches(
            in: controllerSource,
            range: NSRange(controllerSource.startIndex..., in: controllerSource)
        )
        let nestedPublicTypePattern = try NSRegularExpression(
            pattern: #"\bpublic\s+(?:class|struct|enum|actor|protocol|typealias)\s+[A-Za-z_][A-Za-z0-9_]*"#
        )
        let nestedPublicTypeMatches = nestedPublicTypePattern.matches(
            in: controllerSource,
            range: NSRange(controllerSource.startIndex..., in: controllerSource)
        )

        XCTAssertEqual(methodNames.sorted(), ["start", "status", "stop"])
        XCTAssertEqual(initMatches.count, 1)
        XCTAssertTrue(storageMatches.isEmpty)
        XCTAssertTrue(publicSubscriptMatches.isEmpty)
        XCTAssertTrue(nestedPublicTypeMatches.isEmpty)
        XCTAssertFalse(declarationLine.contains(":"))
    }

    func testSameUserUDSAuthenticatorRequiresPrivateSocketPeerUIDAndSecret() throws {
        let authenticator = SameUserUDSAuthenticator(
            secrets: FakeCaptureKeyStoreAdapter(secret: "control-secret"),
            expectedUID: 501
        )

        XCTAssertNoThrow(try authenticator.validateSocketPermissions(0o600))
        XCTAssertThrowsError(try authenticator.validateSocketPermissions(0o660)) { error in
            XCTAssertEqual(error as? CaptureSecurityError, .socketPathNotPrivate)
        }
        XCTAssertNoThrow(try authenticator.validate(peerUID: 501, presentedSecret: "control-secret"))
        XCTAssertThrowsError(try authenticator.validate(peerUID: 502, presentedSecret: "control-secret")) { error in
            XCTAssertEqual(
                error as? CaptureSecurityError,
                .peerUIDMismatch(expected: 501, actual: 502)
            )
        }
        XCTAssertThrowsError(try authenticator.validate(peerUID: 501, presentedSecret: "wrong")) { error in
            XCTAssertEqual(error as? CaptureSecurityError, .controlSecretMismatch)
        }
    }

    func testUnixDomainControlClientUsesStoredControlSecretOnlyInUDSPayload() throws {
        let client = UnixDomainControlClient(
            socketPath: "/tmp/moss-capture/control.sock",
            secrets: FakeCaptureKeyStoreAdapter(secret: "control-secret")
        )

        let payload = try client.encodeRequest(
            ControlChannelRequest(command: "start", label: "local")
        )
        let body = try XCTUnwrap(String(data: payload, encoding: .utf8))

        XCTAssertTrue(body.contains("\"secret\":\"control-secret\""))
        XCTAssertTrue(body.contains("\"command\":\"start\""))
        XCTAssertTrue(body.contains("\"label\":\"local\""))
        XCTAssertFalse(client.socketPath.contains("control-secret"))
    }

    private func testCertificate() throws -> SecCertificate {
        let fixture = """
        MIIBvzCCASgCCQCWZwVkxZUDQDANBgkqhkiG9w0BAQsFADAkMSIwIAYDVQQDDBlN
        T1NTIENhcHR1cmUgVGVzdCBGaXh0dXJlMB4XDTI2MDcyNjAyMjMxOFoXDTI2MDcy
        NzAyMjMxOFowJDEiMCAGA1UEAwwZTU9TUyBDYXB0dXJlIFRlc3QgRml4dHVyZTCB
        nzANBgkqhkiG9w0BAQEFAAOBjQAwgYkCgYEApC3PW4Izr+VU+uJmE9+1uKV9VVo
        glHQFIkOBKZ3UO218L35QVRo+V67IgDIuxKTEQsjqIFWi/pFAeTJtykP4nWDvqDJ
        4XMmJVsTTOGwfQ7Q6CoafBBV0DcvvgqvUMezLQihmfrensrPhGb06kEJgId7q0LA
        bow6DLcBtKSKm3OsCAwEAATANBgkqhkiG9w0BAQsFAAOBgQBS61haY4bsxRuxgxxH
        TXw2BHz6rooSSKktJ5SUCw03TffObW9LFWS+i7Aw/ddaMJHI03LM2lOPz9ZiC2FX
        pv/6V2MCyiBvtMJ/vNht7BNFxzYwyeMNLm1QNGwiGo6NZ/G7U9rgqrw2z/lEJ+6E
        hspPHgHJi69E6fC2EU4JUs3MCQ==
        """
        let der = try XCTUnwrap(
            Data(base64Encoded: fixture, options: .ignoreUnknownCharacters)
        )
        return try XCTUnwrap(SecCertificateCreateWithData(nil, der as CFData))
    }

    private func packageRoot() -> URL {
        var url = URL(fileURLWithPath: #filePath)
        for _ in 0..<3 {
            url.deleteLastPathComponent()
        }
        return url
    }

    private func jsonBody(_ request: URLRequest) throws -> [String: Any] {
        let data = try XCTUnwrap(request.httpBody)
        let object = try JSONSerialization.jsonObject(with: data)
        return try XCTUnwrap(object as? [String: Any])
    }
}

private final class RecordingCaptureHTTPClient: CaptureHTTPClient {
    private(set) var requests: [URLRequest] = []
    var response = CaptureHTTPResponse(statusCode: 200)

    func send(_ request: URLRequest) throws -> CaptureHTTPResponse {
        requests.append(request)
        return response
    }
}
