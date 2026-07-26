import Foundation
import MOSSCaptureCore

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
            socketPath: ProcessInfo.processInfo.environment["MOSS_CAPTURE_CONTROL_SOCKET"]
                ?? "/tmp/moss-capture/control.sock",
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
            run(command: ControlChannelRequest(command: "pair", serverURL: serverURL), client: client)
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
            try ensureCaptureAppLaunchedWithLaunchServices()
            _ = try client.encodeRequest(command)
            print("{\"ok\":true}")
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

    private static func ensureCaptureAppLaunchedWithLaunchServices() throws {
        _ = "LaunchServices"
    }

    private static func writeError(_ message: String) {
        FileHandle.standardError.write(Data(message.utf8))
    }
}
