import Foundation
#if canImport(AppKit)
import AppKit
#endif

public protocol CaptureAppLaunching {
    func launch() throws
}

public protocol ControlSocketChecking {
    func fileExists(atPath path: String) -> Bool
}

extension FileManager: ControlSocketChecking {}

public protocol ControlChannelRequestSending {
    var socketPath: String { get }
    func sendRequest(_ request: ControlChannelRequest) throws -> ControlChannelResponse
}

extension UnixDomainControlClient: ControlChannelRequestSending {}

public protocol CaptureCLIInput {
    func readAll() -> Data
}

public protocol CaptureCLIOutput {
    func write(_ data: Data) throws
}

public enum CaptureCLIError: Error, Equatable {
    case launchServicesUnavailable
}

public final class NSWorkspaceLaunchServicesCaptureAppLauncher: CaptureAppLaunching {
    private let environment: [String: String]
    private let openApplication: (URL) throws -> Void

    public convenience init(environment: [String: String] = ProcessInfo.processInfo.environment) {
        self.init(environment: environment) { appURL in
            #if canImport(AppKit)
            let configuration = NSWorkspace.OpenConfiguration()
            let semaphore = DispatchSemaphore(value: 0)
            let result = LaunchResultBox()
            NSWorkspace.shared.openApplication(at: appURL, configuration: configuration) { _, error in
                result.store(error)
                semaphore.signal()
            }
            semaphore.wait()
            if let error = result.load() {
                throw error
            }
            #else
            _ = appURL
            throw CaptureCLIError.launchServicesUnavailable
            #endif
        }
    }

    init(
        environment: [String: String],
        openApplication: @escaping (URL) throws -> Void
    ) {
        self.environment = environment
        self.openApplication = openApplication
    }

    public func launch() throws {
        guard let rawAppURL = environment["MOSS_CAPTURE_APP_URL"] else {
            throw CaptureCLIError.launchServicesUnavailable
        }
        try openApplication(URL(fileURLWithPath: rawAppURL))
    }
}

public final class CaptureCommandLine {
    private let launcher: CaptureAppLaunching
    private let socketChecker: ControlSocketChecking
    private let client: ControlChannelRequestSending
    private let input: CaptureCLIInput
    private let standardOutput: CaptureCLIOutput
    private let standardError: CaptureCLIOutput
    private let skipLaunch: Bool

    public init(
        launcher: CaptureAppLaunching,
        socketChecker: ControlSocketChecking,
        client: ControlChannelRequestSending,
        input: CaptureCLIInput,
        standardOutput: CaptureCLIOutput,
        standardError: CaptureCLIOutput,
        skipLaunch: Bool = false
    ) {
        self.launcher = launcher
        self.socketChecker = socketChecker
        self.client = client
        self.input = input
        self.standardOutput = standardOutput
        self.standardError = standardError
        self.skipLaunch = skipLaunch
    }

    public func run(arguments: [String]) -> Int32 {
        guard let rawCommand = arguments.first,
              ControlChannelCommands.all.contains(rawCommand) else {
            writeError(
                "usage: mtd-capture pair --server <https-url> | "
                    + "start [--label <name>] | stop | status | handoff | latency\n"
            )
            return 64
        }

        let request: ControlChannelRequest
        if rawCommand == "pair" {
            guard let server = value(after: "--server", in: arguments),
                  let serverURL = URL(string: server),
                  serverURL.scheme == "https" else {
                writeError("usage: mtd-capture pair --server <https-url>\n")
                return 64
            }
            let pairingPayload = input.readAll()
            guard !pairingPayload.isEmpty else {
                writeError("pairing payload required on stdin\n")
                return 65
            }
            request = ControlChannelRequest(
                command: rawCommand,
                serverURL: serverURL,
                pairingPayload: pairingPayload
            )
        } else if rawCommand == "handoff" {
            // The app owns view authority and the pasteboard; the CLI only asks for the handoff
            // and relays the app's non-secret confirmation.
            request = ControlChannelRequest(command: "handoff")
        } else if rawCommand == "latency" {
            // Same rule for the measurement: the app polls with its own view authority and answers
            // with aggregates, so asking for a figure never puts a token on this side of the socket.
            request = ControlChannelRequest(command: "latency")
        } else {
            request = ControlChannelRequest(
                command: rawCommand,
                label: rawCommand == "start" ? value(after: "--label", in: arguments) : nil
            )
        }

        do {
            if !skipLaunch && !socketChecker.fileExists(atPath: client.socketPath) {
                try launcher.launch()
            }
            let response = try client.sendRequest(request)
            try writeResponse(response)
            return response.ok ? 0 : 70
        } catch {
            writeError("{\"ok\":false}\n")
            return 70
        }
    }

    private func value(after flag: String, in arguments: [String]) -> String? {
        guard let index = arguments.firstIndex(of: flag),
              arguments.indices.contains(arguments.index(after: index)) else {
            return nil
        }
        return arguments[arguments.index(after: index)]
    }

    private func writeResponse(_ response: ControlChannelResponse) throws {
        try writeJSON(response)
    }

    private func writeJSON(_ value: some Encodable) throws {
        var data = try JSONEncoder().encode(value)
        data.append(contentsOf: Data("\n".utf8))
        try standardOutput.write(data)
    }

    private func writeError(_ message: String) {
        try? standardError.write(Data(message.utf8))
    }
}

private final class LaunchResultBox: @unchecked Sendable {
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
