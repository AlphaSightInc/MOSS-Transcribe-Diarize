import Foundation
import MOSSCaptureCore

@main
struct MTDCaptureCLI {
    static func main() {
        let sendRequestClient = UnixDomainControlClient(
            socketPath: ControlSocketDefaults.socketPath(),
            secrets: KeychainCaptureSecretStore()
        )
        let pairingPayloadInput = StandardInput()
        let commandLine = CaptureCommandLine(
            launcher: NSWorkspaceLaunchServicesCaptureAppLauncher(),
            socketChecker: FileManager.default,
            client: sendRequestClient,
            input: pairingPayloadInput,
            standardOutput: StandardOutput(fileHandle: .standardOutput),
            standardError: StandardOutput(fileHandle: .standardError),
            skipLaunch: ProcessInfo.processInfo.environment["MOSS_CAPTURE_SKIP_LAUNCH"] == "1"
        )
        let exitCode = commandLine.run(arguments: Array(CommandLine.arguments.dropFirst()))
        if exitCode != 0 {
            Foundation.exit(exitCode)
        }
    }
}

private struct StandardInput: CaptureCLIInput {
    func readAll() -> Data {
        FileHandle.standardInput.readDataToEndOfFile()
    }
}

private struct StandardOutput: CaptureCLIOutput {
    let fileHandle: FileHandle

    func write(_ data: Data) throws {
        fileHandle.write(data)
    }
}
