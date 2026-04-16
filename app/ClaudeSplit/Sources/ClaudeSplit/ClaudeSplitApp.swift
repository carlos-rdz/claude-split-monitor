import SwiftUI
import UserNotifications

@main
struct ClaudeSplitApp: App {
    @StateObject private var ws = WatchClient()

    var body: some Scene {
        MenuBarExtra {
            MenuContent(ws: ws)
        } label: {
            MenuBarLabel(ws: ws)
        }
        .menuBarExtraStyle(.window)

        // Optional dashboard window — opens via "Open Dashboard" action
        WindowGroup("claude-split", id: "dashboard") {
            DashboardWindow(ws: ws)
                .frame(minWidth: 900, minHeight: 600)
        }
    }
}

// ─────────────────────────────────────────────────────────────
// Menu bar label — two tiny alive dots
// ─────────────────────────────────────────────────────────────

struct MenuBarLabel: View {
    @ObservedObject var ws: WatchClient

    var body: some View {
        HStack(spacing: 3) {
            Circle()
                .fill(statusColor(ws.plannerAlive, ws.plannerStuck))
                .frame(width: 7, height: 7)
            Circle()
                .fill(statusColor(ws.executorAlive, ws.executorStuck))
                .frame(width: 7, height: 7)
            if ws.alerts > 0 {
                Text("!")
                    .font(.system(size: 10, weight: .black))
                    .foregroundColor(.red)
            }
        }
    }

    func statusColor(_ alive: Bool, _ stuck: Int) -> Color {
        if !alive { return .gray.opacity(0.4) }
        if stuck > 180 { return .red }
        if stuck > 60 { return .yellow }
        return .green
    }
}

// ─────────────────────────────────────────────────────────────
// Menu content — compact popover
// ─────────────────────────────────────────────────────────────

struct MenuContent: View {
    @ObservedObject var ws: WatchClient
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Header
            HStack {
                Text("claude-split")
                    .font(.system(size: 11, weight: .heavy))
                    .textCase(.uppercase)
                    .foregroundColor(.primary)
                Spacer()
                statusBadge
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .background(Color(nsColor: .controlBackgroundColor))

            Divider()

            // Agents
            AgentRow(name: "PLANNER", color: .blue,
                     alive: ws.plannerAlive, stuck: ws.plannerStuck,
                     cost: ws.plannerCost, action: ws.plannerLastAction)
            Divider()
            AgentRow(name: "EXECUTOR", color: .orange,
                     alive: ws.executorAlive, stuck: ws.executorStuck,
                     cost: ws.executorCost, action: ws.executorLastAction)

            Divider()

            // Alerts (if any)
            if ws.alertList.count > 0 {
                VStack(alignment: .leading, spacing: 4) {
                    Text("ALERTS")
                        .font(.system(size: 9, weight: .bold))
                        .foregroundColor(.secondary)
                        .textCase(.uppercase)
                    ForEach(ws.alertList.prefix(3)) { a in
                        HStack(spacing: 6) {
                            Text(a.severity == "warn" ? "⚠" : "✕")
                                .foregroundColor(a.severity == "warn" ? .yellow : .red)
                            Text(a.text)
                                .font(.system(size: 11))
                                .foregroundColor(.primary)
                                .lineLimit(1)
                        }
                    }
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                Divider()
            }

            // Totals
            HStack(spacing: 12) {
                Label(String(format: "$%.2f", ws.totalCost),
                      systemImage: "dollarsign.circle")
                    .font(.system(size: 11))
                Label(fmtDuration(ws.uptimeSec),
                      systemImage: "clock")
                    .font(.system(size: 11))
                Spacer()
                Circle()
                    .fill(ws.connected ? Color.green : Color.red)
                    .frame(width: 6, height: 6)
            }
            .foregroundColor(.secondary)
            .padding(.horizontal, 10)
            .padding(.vertical, 6)

            Divider()

            // Actions
            HStack(spacing: 0) {
                Button { openWindow(id: "dashboard") } label: {
                    Label("Dashboard", systemImage: "rectangle.stack")
                        .font(.system(size: 11))
                }
                .buttonStyle(.plain)
                .frame(maxWidth: .infinity, alignment: .leading)

                Button { NSApp.terminate(nil) } label: {
                    Text("Quit")
                        .font(.system(size: 11))
                        .foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
        }
        .frame(width: 280)
    }

    var statusBadge: some View {
        let status: String
        let color: Color
        if !ws.connected { status = "OFFLINE"; color = .red }
        else if ws.alerts > 0 { status = "ALERT"; color = .red }
        else if ws.plannerAlive || ws.executorAlive { status = "ACTIVE"; color = .green }
        else { status = "IDLE"; color = .gray }
        return Text(status)
            .font(.system(size: 9, weight: .bold, design: .monospaced))
            .foregroundColor(color)
    }
}

// ─────────────────────────────────────────────────────────────
// Agent row
// ─────────────────────────────────────────────────────────────

struct AgentRow: View {
    let name: String
    let color: Color
    let alive: Bool
    let stuck: Int
    let cost: Double
    let action: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Circle()
                    .fill(dotColor)
                    .frame(width: 8, height: 8)
                Text(name)
                    .font(.system(size: 11, weight: .heavy))
                    .foregroundColor(color)
                Spacer()
                Text(String(format: "$%.2f", cost))
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundColor(.secondary)
            }
            HStack {
                Text(status)
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundColor(.secondary)
                Spacer()
            }
            if let action = action, !action.isEmpty {
                Text(action)
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundColor(.primary)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
    }

    var dotColor: Color {
        if !alive { return .gray.opacity(0.4) }
        if stuck > 180 { return .red }
        if stuck > 60 { return .yellow }
        return .green
    }

    var status: String {
        if !alive { return "offline" }
        if stuck > 180 { return "stuck \(fmtRel(stuck))" }
        if stuck > 60 { return "idle \(fmtRel(stuck))" }
        return "active"
    }
}

// ─────────────────────────────────────────────────────────────
// Dashboard window — embeds the web dashboard via WebView
// ─────────────────────────────────────────────────────────────

struct DashboardWindow: View {
    @ObservedObject var ws: WatchClient

    var body: some View {
        WebView(url: URL(string: "http://\(ws.serverHost):\(ws.serverPort)/")!)
            .frame(minWidth: 900, minHeight: 600)
    }
}

// ─────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────

func fmtRel(_ sec: Int) -> String {
    if sec < 60 { return "\(sec)s" }
    if sec < 3600 { return "\(sec/60)m" }
    return "\(sec/3600)h"
}

func fmtDuration(_ sec: Int) -> String {
    if sec < 60 { return "\(sec)s" }
    if sec < 3600 { return "\(sec/60)m" }
    let h = sec / 3600
    let m = (sec % 3600) / 60
    return m > 0 ? "\(h)h\(m)m" : "\(h)h"
}
