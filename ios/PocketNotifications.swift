import Foundation
import UserNotifications
import Combine
import SwiftUI

@MainActor final class PocketNotifications: NSObject, ObservableObject, UNUserNotificationCenterDelegate {
    static let shared = PocketNotifications()
    @Published private(set) var enabled = UserDefaults.standard.bool(forKey: "notifications.local")
    @Published var error: String?
    private var enabledAt = UserDefaults.standard.double(forKey: "notifications.enabledAt")
    private var seen = UserDefaults.standard.dictionary(forKey: "notifications.seen") as? [String: Double] ?? [:]
    override init() { super.init(); UNUserNotificationCenter.current().delegate = self }
    func setEnabled(_ value: Bool) async {
        if value {
            do {
                guard try await UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) else {
                    error = "Permissão não concedida. Você pode alterar em Ajustes do iOS → Notificações → Pocket."; return
                }
            } catch { self.error = "Não foi possível solicitar notificações."; return }
            enabledAt = Date().timeIntervalSince1970
            UserDefaults.standard.set(enabledAt, forKey: "notifications.enabledAt")
        } else {
            UNUserNotificationCenter.current().removeAllPendingNotificationRequests()
            UNUserNotificationCenter.current().removeAllDeliveredNotifications()
        }
        enabled = value; error = nil
        UserDefaults.standard.set(value, forKey: "notifications.local")
    }
    func post(key: String, title: String, body: String) {
        guard enabled else { return }
        let id = HistoryCache.key(key)
        guard seen[id] == nil else { return }
        seen[id] = Date().timeIntervalSince1970
        if seen.count > 500 { seen = Dictionary(uniqueKeysWithValues: seen.sorted { $0.value > $1.value }.prefix(500).map { ($0.key, $0.value) }) }
        UserDefaults.standard.set(seen, forKey: "notifications.seen")
        let content = UNMutableNotificationContent()
        content.title = title; content.body = body; content.sound = .default
        UNUserNotificationCenter.current().add(UNNotificationRequest(identifier: "pocket." + id, content: content, trigger: nil))
    }
    func observe(_ sessions: [Session], server: String) {
        guard enabled else { return }
        for session in sessions {
            guard let raw = session.completionStamp else { continue }
            guard (session.time?.viewed ?? 0) < raw else { continue }
            let timestamp = raw > 100_000_000_000 ? raw / 1000 : raw
            guard timestamp > enabledAt else { continue }
            post(key: "completion|\(server)|\(session.id)|\(raw)", title: "Tarefa finalizada", body: "Abra Pocket para consultar resultado no notebook.")
        }
    }
    nonisolated func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification,
                                            withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .sound])
    }
}

struct NotificationSettingsView: View {
    @ObservedObject private var notifications = PocketNotifications.shared
    var body: some View {
        Form {
            Toggle("Avisos locais opcionais", isOn: Binding(get: { notifications.enabled }, set: { value in Task { await notifications.setEnabled(value) } }))
            Text("Avisa conclusões observadas quando Pocket consulta notebook, permissões da conversa aberta e uploads de segundo plano concluídos. Não mostra nomes, texto de chat nem arquivos na tela bloqueada.").font(.caption)
            Text("Não é push remoto: enquanto Pocket estiver suspenso, tarefas do notebook não são consultadas continuamente. Alertas podem aparecer somente ao reabrir. Push pelo APNs exige capacidades e infraestrutura Apple ainda não configuradas.").font(.caption).foregroundStyle(.secondary)
            if let error = notifications.error { Text(error).foregroundStyle(.red) }
        }.navigationTitle("Notificações")
    }
}
