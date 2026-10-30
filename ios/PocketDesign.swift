import SwiftUI

enum PocketDesign {
    static let kzL = Color(red: 0.77, green: 0.10, blue: 0.16)
    static let graphite = Color(red: 0.065, green: 0.067, blue: 0.08)
    static func modelName(_ id: String?) -> String {
        guard let id else { return "Modelo" }
        switch id {
        case "gpt-6.1-terra-fast": return "Terra Fast"
        case "gpt-6.1-terra": return "Terra"
        case "gpt-6.1-sol-ultrafast": return "Sol Ultrafast"
        case "gpt-realtime-2.1": return "Realtime"
        default: return id
        }
    }
}

struct NotebookOverviewView: View {
    @EnvironmentObject var api: API
    @Environment(\.dismiss) private var dismiss
    @State private var status: HostStatus?
    @State private var quota: CodexQuota?
    @State private var error: String?
    var body: some View {
        NavigationStack {
            List {
                Section("Computador selecionado") { Text(api.server).font(.caption).textSelection(.enabled) }
                Section("Bateria") { HostBatteryView(status: status, stale: error != nil) }
                Section("Armazenamento") { StorageDashboard(host: status?.storage, stale: error != nil) }
                Section("Codex") { CodexQuotaView(quota: quota, failed: error != nil, loading: quota == nil && error == nil) { Task { await load() } } }
                if let error { Section { Text(error).font(.caption).foregroundStyle(.secondary); Button("Atualizar") { Task { await load() } } } }
            }.navigationTitle("Computador").navigationBarTitleDisplayMode(.inline)
                .toolbar { Button("Fechar") { dismiss() } }.task { await load() }.refreshable { await load() }
        }
    }
    private func load() async {
        let connection = api.connectionID
        do {
            let value: HostStatus = try await api.request("/phone/status")
            guard connection == api.connectionID, !Task.isCancelled else { return }; status = value
            let limits: CodexQuota = try await api.request("/phone/codex/usage")
            guard connection == api.connectionID, !Task.isCancelled else { return }
            quota = limits; error = nil
        } catch { self.error = "Não foi possível atualizar indicadores. Última leitura pode estar antiga." }
    }
}
