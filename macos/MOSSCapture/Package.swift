// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "MOSSCapture",
    platforms: [
        .macOS(.v14)
    ],
    products: [
        .library(name: "MOSSCaptureCore", targets: ["MOSSCaptureCore"]),
        .executable(name: "MOSSCaptureApp", targets: ["MOSSCaptureApp"]),
        .executable(name: "mtd-capture", targets: ["MTDCaptureCLI"])
    ],
    targets: [
        .target(name: "MOSSCaptureCore"),
        .executableTarget(
            name: "MOSSCaptureApp",
            dependencies: ["MOSSCaptureCore"]
        ),
        .executableTarget(
            name: "MTDCaptureCLI",
            dependencies: ["MOSSCaptureCore"]
        ),
        .testTarget(
            name: "MOSSCaptureCoreTests",
            dependencies: ["MOSSCaptureCore"]
        ),
        .testTarget(
            name: "MTDCaptureCLITests",
            dependencies: ["MOSSCaptureCore"]
        )
    ]
)
