import Foundation
import XCTest

final class MTDCaptureCLITests: XCTestCase {
    func testShimCommandsStayControlOnlyAndAudioFrameworkFree() throws {
        let source = try String(
            contentsOf: packageRoot()
                .appendingPathComponent("Sources")
                .appendingPathComponent("MTDCaptureCLI")
                .appendingPathComponent("main.swift"),
            encoding: .utf8
        )

        XCTAssertTrue(source.contains("pair"))
        XCTAssertTrue(source.contains("start"))
        XCTAssertTrue(source.contains("stop"))
        XCTAssertTrue(source.contains("status"))
        XCTAssertTrue(source.contains("LaunchServices"))
        XCTAssertTrue(source.contains("UnixDomainControlClient"))
        XCTAssertTrue(source.contains("readDataToEndOfFile"))
        XCTAssertTrue(source.contains("--server"))
        XCTAssertTrue(source.contains("--label"))
        XCTAssertFalse(source.contains("CoreAudio"))
        XCTAssertFalse(source.contains("AVFAudio"))
        XCTAssertFalse(source.contains("AudioHardwareCreateProcessTap"))
        XCTAssertFalse(source.contains("CaptureController.fakeForLocalDevelopment"))
        XCTAssertFalse(source.contains("capture-token"))
        XCTAssertFalse(source.contains("\"command\":\"status\""))
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

    private func packageRoot() -> URL {
        var url = URL(fileURLWithPath: #filePath)
        for _ in 0..<3 {
            url.deleteLastPathComponent()
        }
        return url
    }
}
