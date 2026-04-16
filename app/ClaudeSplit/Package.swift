// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "ClaudeSplit",
    platforms: [.macOS(.v13)],
    products: [
        .executable(name: "ClaudeSplit", targets: ["ClaudeSplit"]),
    ],
    targets: [
        .executableTarget(
            name: "ClaudeSplit",
            path: "Sources/ClaudeSplit"
        ),
    ]
)
