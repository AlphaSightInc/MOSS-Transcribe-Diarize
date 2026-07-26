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
            FileHandle.standardError.write(Data("usage: mtd-capture pair|start|stop|status\n".utf8))
            Foundation.exit(64)
        }

        switch command {
        case .pair:
            guard arguments.contains("--server") else {
                FileHandle.standardError.write(Data("usage: mtd-capture pair --server <https-url>\n".utf8))
                Foundation.exit(64)
            }
            print("{\"ok\":true,\"command\":\"pair\"}")
        case .start:
            print("{\"ok\":true,\"command\":\"start\"}")
        case .stop:
            print("{\"ok\":true,\"command\":\"stop\"}")
        case .status:
            let controller = CaptureController.fakeForLocalDevelopment()
            let status = controller.status()
            print("{\"ok\":true,\"command\":\"status\",\"running\":\(status.running)}")
        }
    }
}
