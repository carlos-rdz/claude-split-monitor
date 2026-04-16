import SwiftUI

@main
struct ClaudeSplitApp: App {
    @StateObject private var ws = WatchClient()

    var body: some Scene {
        Window("claude-split", id: "main") {
            DashboardWindow(ws: ws)
                .frame(minWidth: 1100, idealWidth: 1400, minHeight: 720, idealHeight: 860)
                .background(Color(red: 0, green: 0, blue: 0))
        }
        .windowStyle(.hiddenTitleBar)
        .windowResizability(.contentMinSize)
        .defaultSize(width: 1400, height: 860)
        .commands {
            CommandGroup(replacing: .newItem) {}
        }
    }
}

// ─────────────────────────────────────────────────────────────
// Main window — WebView of the dashboard
// ─────────────────────────────────────────────────────────────

struct DashboardWindow: View {
    @ObservedObject var ws: WatchClient

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            if ws.connected {
                WebView(url: URL(string: "http://\(ws.serverHost):\(ws.serverPort)/")!)
                    .ignoresSafeArea()
            } else {
                VStack(spacing: 16) {
                    Image(systemName: "bolt.slash")
                        .font(.system(size: 44))
                        .foregroundColor(.gray)
                    Text("waiting for claude-split-monitor server")
                        .font(.system(size: 13, weight: .medium, design: .monospaced))
                        .foregroundColor(.gray)
                    Text("ws://\(ws.serverHost):\(ws.serverPort)/ws")
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundColor(.gray.opacity(0.6))
                    Text("run:  pip install claude-split-monitor && claude-split-monitor")
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundColor(.gray.opacity(0.5))
                        .padding(.top, 12)
                }
                .padding(32)
            }
        }
    }
}
