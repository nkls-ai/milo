// swift-tools-version: 5.10
import PackageDescription

let package = Package(
    name: "Milo",
    platforms: [.macOS(.v14)],
    products: [
        .executable(name: "Milo", targets: ["Milo"]),
    ],
    targets: [
        .target(name: "MiloKit", path: "Sources/MiloKit"),
        .executableTarget(name: "Milo", dependencies: ["MiloKit"], path: "Sources/Milo"),
        .testTarget(name: "MiloKitTests", dependencies: ["MiloKit"], path: "Tests/MiloKitTests"),
    ]
)
