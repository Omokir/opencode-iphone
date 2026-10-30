import SwiftUI
import UIKit

enum PocketDesign {
    // Text accents remain legible in both appearances; the send glyph uses
    // white on signalRed. No images, identity assets or private state change.
    static let kzL = adaptive(light: 0xB52231, dark: 0xFF6370)
    static let signalRed = Color(red: 229 / 255.0, green: 57 / 255.0, blue: 69 / 255.0)
    static let graphite = Color(red: 9 / 255.0, green: 9 / 255.0, blue: 12 / 255.0)
    static let canvas = adaptive(light: 0xFFFFFF, dark: 0x09090C)
    static let surface = adaptive(light: 0xF2F2F7, dark: 0x15151B)
    static let bubble = adaptive(light: 0xF2F2F7, dark: 0x1B1820)
    static let line = adaptive(light: 0xDDD5DA, dark: 0x44303A)
    static let secondary = adaptive(light: 0x64646D, dark: 0xB3B3C0)

    private static func adaptive(light: UInt32, dark: UInt32) -> Color {
        Color(uiColor: UIColor { traits in
            let rgb = traits.userInterfaceStyle == .dark ? dark : light
            return UIColor(red: CGFloat((rgb >> 16) & 255) / 255,
                           green: CGFloat((rgb >> 8) & 255) / 255,
                           blue: CGFloat(rgb & 255) / 255, alpha: 1)
        })
    }
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
