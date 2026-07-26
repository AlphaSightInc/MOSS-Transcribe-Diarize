import Foundation
import MOSSCaptureCore

@main
struct MOSSCaptureAppMain {
    static func main() {
        let controller = CaptureController.fakeForLocalDevelopment()
        _ = controller.status()
        RunLoop.current.run(until: Date(timeIntervalSinceNow: 0.01))
    }
}
