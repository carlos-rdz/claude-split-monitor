import Foundation
import UserNotifications

class WatchClient: ObservableObject {

    struct Alert: Identifiable {
        let id       = UUID()
        let severity: String  // "warn" | "error"
        let text:     String
    }

    @Published var connected:         Bool    = false
    @Published var plannerAlive:      Bool    = false
    @Published var plannerStuck:      Int     = 0
    @Published var plannerCost:       Double  = 0
    @Published var plannerLastAction: String? = nil
    @Published var executorAlive:      Bool    = false
    @Published var executorStuck:      Int     = 0
    @Published var executorCost:       Double  = 0
    @Published var executorLastAction: String? = nil
    @Published var totalCost:  Double  = 0
    @Published var uptimeSec:  Int     = 0
    @Published var alerts:     Int     = 0
    @Published var alertList:  [Alert] = []
    @Published var serverHost: String  = "localhost"
    @Published var serverPort: Int     = 7433

    private var task:             URLSessionWebSocketTask?
    private var reconnectDelay:   Double  = 1.0
    private let maxDelay:         Double  = 15.0
    private var prevAlertTexts:   Set<String> = []

    init() {
        UNUserNotificationCenter.current()
            .requestAuthorization(options: [.alert, .sound]) { _, _ in }
        connect()
    }

    // ── Connection ──────────────────────────────────────────────────────────

    private func connect() {
        let urlStr = "ws://\(serverHost):\(serverPort)/ws"
        guard let url = URL(string: urlStr) else { return }
        task = URLSession.shared.webSocketTask(with: url)
        task?.resume()
        receive()
    }

    private func receive() {
        task?.receive { [weak self] result in
            guard let self else { return }
            switch result {
            case .success(let msg):
                switch msg {
                case .string(let s):        self.handle(s)
                case .data(let d):
                    if let s = String(data: d, encoding: .utf8) { self.handle(s) }
                default: break
                }
                self.receive()                  // re-arm
            case .failure:
                DispatchQueue.main.async { self.connected = false }
                self.scheduleReconnect()
            }
        }
    }

    private func scheduleReconnect() {
        let delay = reconnectDelay
        reconnectDelay = min(reconnectDelay * 2, maxDelay)
        DispatchQueue.global().asyncAfter(deadline: .now() + delay) { [weak self] in
            self?.connect()
        }
    }

    // ── Payload parsing ─────────────────────────────────────────────────────

    private func handle(_ text: String) {
        guard
            let data = text.data(using: .utf8),
            let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            json["type"] as? String == "cowork_state"
        else { return }

        let planner   = json["planner"]   as? [String: Any] ?? [:]
        let executor  = json["executor"]  as? [String: Any] ?? [:]
        let totals    = json["totals"]    as? [String: Any] ?? [:]
        let rawAlerts = json["alerts"]    as? [[String: Any]] ?? []

        let newAlerts = rawAlerts.map {
            Alert(severity: $0["severity"] as? String ?? "warn",
                  text:     $0["text"]     as? String ?? "")
        }

        // Desktop notification for newly-appearing alerts (dedup by text)
        let newTexts = Set(newAlerts.map(\.text))
        for t in newTexts.subtracting(prevAlertTexts) { notify(t) }
        prevAlertTexts = newTexts

        DispatchQueue.main.async {
            self.plannerAlive       = planner["alive"]         as? Bool   ?? false
            self.plannerStuck       = planner["stuck_seconds"] as? Int    ?? 0
            self.plannerCost        = planner["cost_usd"]      as? Double ?? 0
            self.plannerLastAction  = self.fmtAction(planner["last_action"]  as? [String: Any])
            self.executorAlive      = executor["alive"]         as? Bool   ?? false
            self.executorStuck      = executor["stuck_seconds"] as? Int    ?? 0
            self.executorCost       = executor["cost_usd"]      as? Double ?? 0
            self.executorLastAction = self.fmtAction(executor["last_action"] as? [String: Any])
            self.totalCost  = totals["total_cost"] as? Double ?? 0
            self.uptimeSec  = totals["uptime_s"]   as? Int    ?? 0
            self.alerts     = newAlerts.count
            self.alertList  = newAlerts
            self.connected  = true
        }
    }

    private func fmtAction(_ a: [String: Any]?) -> String? {
        guard let type   = a?["type"]   as? String,
              let target = a?["target"] as? String else { return nil }
        return "\(type) \(target)"
    }

    // ── Notifications ────────────────────────────────────────────────────────

    private func notify(_ text: String) {
        let content       = UNMutableNotificationContent()
        content.title     = "claude-split"
        content.body      = text
        content.sound     = .default
        let req = UNNotificationRequest(
            identifier:  UUID().uuidString,
            content:     content,
            trigger:     nil
        )
        UNUserNotificationCenter.current().add(req, withCompletionHandler: nil)
    }
}
