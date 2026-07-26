import Foundation
import MOSSCaptureCore
#if canImport(AppKit)
import AppKit
#endif

enum MTDCaptureCommand: String {
    case pair
    case start
    case stop
    case status
}

@main
struct MTDCaptureCLI {
    static func main() {
        let arguments = Array(CommandLine.arguments.dropFirst())
        guard let rawCommand = arguments.first,
              let command = MTDCaptureCommand(rawValue: rawCommand) else {
            writeError("usage: mtd-capture pair --server <https-url> | start [--label <name>] | stop | status\n")
            Foundation.exit(64)
        }

        let client = UnixDomainControlClient(
            socketPath: ControlSocketDefaults.socketPath(),
            secrets: KeychainCaptureSecretStore()
        )

        switch command {
        case .pair:
            guard let server = value(after: "--server", in: arguments),
                  let serverURL = URL(string: server),
                  serverURL.scheme == "https" else {
                writeError("usage: mtd-capture pair --server <https-url>\n")
                Foundation.exit(64)
            }
            let pairingPayload = FileHandle.standardInput.readDataToEndOfFile()
            guard !pairingPayload.isEmpty else {
                writeError("pairing payload required on stdin\n")
                Foundation.exit(65)
            }
            run(
                command: ControlChannelRequest(
                    command: "pair",
                    serverURL: serverURL,
                    pairingPayload: pairingPayload
                ),
                client: client
            )
        case .start:
            run(
                command: ControlChannelRequest(command: "start", label: value(after: "--label", in: arguments)),
                client: client
            )
        case .stop:
            run(command: ControlChannelRequest(command: "stop"), client: client)
        case .status:
            run(command: ControlChannelRequest(command: "status"), client: client)
        }
    }

    private static func run(command: ControlChannelRequest, client: UnixDomainControlClient) {
        do {
            try ensureCaptureAppLaunchedWithLaunchServices(socketPath: client.socketPath)
            let response = try client.sendRequest(command)
            try writeResponse(response)
            if !response.ok {
                Foundation.exit(70)
            }
        } catch {
            writeError("{\"ok\":false}\n")
            Foundation.exit(70)
        }
    }

    private static func value(after flag: String, in arguments: [String]) -> String? {
        guard let index = arguments.firstIndex(of: flag),
              arguments.indices.contains(arguments.index(after: index)) else {
            return nil
        }
        return arguments[arguments.index(after: index)]
    }

    private static func ensureCaptureAppLaunchedWithLaunchServices(socketPath: String) throws {
        if FileManager.default.fileExists(atPath: socketPath)
            || ProcessInfo.processInfo.environment["MOSS_CAPTURE_SKIP_LAUNCH"] == "1" {
            return
        }
        guard let rawAppURL = ProcessInfo.processInfo.environment["MOSS_CAPTURE_APP_URL"] else {
            throw MTDCaptureCLIError.launchServicesUnavailable
        }
        let appURL = URL(fileURLWithPath: rawAppURL)
        #if canImport(AppKit)
        let configuration = NSWorkspace.OpenConfiguration()
        let semaphore = DispatchSemaphore(value: 0)
        let launchResult = LaunchResultBox()
        NSWorkspace.shared.openApplication(at: appURL, configuration: configuration) { _, error in
            launchResult.store(error)
            semaphore.signal()
        }
        semaphore.wait()
        if let launchError = launchResult.load() {
            throw launchError
        }
        #else
        _ = appURL
        throw MTDCaptureCLIError.launchServicesUnavailable
        #endif
        _ = "LaunchServices"
    }

    private static func writeResponse(_ response: ControlChannelResponse) throws {
        let data = try JSONEncoder().encode(response)
        FileHandle.standardOutput.write(data)
        FileHandle.standardOutput.write(Data("\n".utf8))
    }

    private static func writeError(_ message: String) {
        FileHandle.standardError.write(Data(message.utf8))
    }
}

enum MTDCaptureCLIError: Error {
    case launchServicesUnavailable
}

final class LaunchResultBox: @unchecked Sendable {
    private let lock = NSLock()
    private var error: Error?

    func store(_ error: Error?) {
        lock.lock()
        self.error = error
        lock.unlock()
    }

    func load() -> Error? {
        lock.lock()
        defer { lock.unlock() }
        return error
    }
}
