import SwiftUI

struct PairedDeviceList: Decodable {
    let devices: [Device]
    struct Device: Decodable, Identifiable {
        let id: String
        let name: String
        let current: Bool
        let createdAt: Double?
    }
}

struct PairedDevicesView: View {
    @EnvironmentObject var api: API
    @EnvironmentObject var privacy: PrivacyLock
    @State private var devices: [PairedDeviceList.Device] = []
    @State private var selected: PairedDeviceList.Device?
    @State private var error: String?
    @State private var busy = false
    var body: some View {
        List {
            Section {
                Text("Novos pareamentos recebem tokens individuais. Conexões anteriores compartilham token: revogá-lo desconecta todos os aparelhos antigos e integrações que usam esse token.").font(.caption)
            }
            ForEach(devices) { device in
                VStack(alignment: .leading, spacing: 6) {
                    Text(device.name).font(.headline)
                    if device.current { Text("Conexão atual").font(.caption).foregroundStyle(.secondary) }
                    if let created = device.createdAt { Text(Date(timeIntervalSince1970: created), style: .date).font(.caption) }
                    Button("Revogar acesso", role: .destructive) { selected = device }.disabled(busy)
                }
            }
            if let error { Text(error).foregroundStyle(.red) }
            Button("Atualizar lista") { Task { await load() } }.disabled(busy)
        }.navigationTitle("Aparelhos pareados")
            .task { await load() }
            .alert("Revogar acesso?", isPresented: Binding(get: { selected != nil }, set: { if !$0 { selected = nil } }), presenting: selected) { device in
                Button("Revogar", role: .destructive) { Task { await revoke(device) } }
                Button("Cancelar", role: .cancel) { selected = nil }
            } message: { device in Text(device.id == "legacy" ? "Todas as conexões com token antigo perderão acesso. Será necessário parear novamente." : "Este aparelho precisará de novo pareamento. Operações já admitidas podem terminar.") }
    }
    func load() async {
        busy = true; defer { busy = false }
        do { let result: PairedDeviceList = try await api.request("/phone/devices"); devices = result.devices; error = nil }
        catch { self.error = ConnectionAdvice.describe(error) }
    }
    func revoke(_ device: PairedDeviceList.Device) async {
        selected = nil
        guard await privacy.confirm("Revogar acesso de aparelho pareado") else { return }
        busy = true; defer { busy = false }
        do {
            let _: EmptyResponse = try await api.request("/phone/devices/revoke", method: "POST", body: ["id": device.id])
            devices.removeAll { $0.id == device.id }
            if device.current { api.disconnect() }
        } catch { self.error = "Revogação não confirmada. Atualize lista antes de tentar novamente." }
    }
}

struct MaintenanceView: View {
    @EnvironmentObject var api: API
    @State private var update = "Não consultado"
    @State private var checking = false
    private var version: String { Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "—" }
    private var diagnostics: String {
        "OpenCode Pocket \(version)\niOS \(UIDevice.current.systemVersion)\nPareado: \(api.connected ? "sim" : "não")\nÚltima conexão HTTP: \(api.reachable.map { $0 ? "respondeu" : "falhou" } ?? "não consultada")\nControle remoto sem USB: não suportado\nSem tokens, domínio, IDs, arquivos ou conteúdo de conversas."
    }
    var body: some View {
        Form {
            Section("Versão") {
                LabeledContent("Instalada", value: version)
                Text(update).font(.caption)
                Button("Consultar versão no código público") { Task { await checkUpdate() } }.disabled(checking)
                Link("Abrir builds no GitHub", destination: URL(string: "https://github.com/Omokir/opencode-iphone/actions/workflows/ios.yml")!)
                Text("Consulta pública ao GitHub, somente quando solicitada. Versão no código não garante IPA aprovado. Assinatura e instalação são etapas separadas.").font(.caption).foregroundStyle(.secondary)
            }
            Section("Diagnóstico sem dados privados") {
                Text(diagnostics).font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                ShareLink(item: diagnostics) { Label("Compartilhar diagnóstico", systemImage: "square.and.arrow.up") }
            }
        }.navigationTitle("Manutenção")
    }
    func checkUpdate() async {
        checking = true; defer { checking = false }
        let config = URLSessionConfiguration.ephemeral
        config.urlCache = nil; config.timeoutIntervalForResource = 15
        let session = URLSession(configuration: config); defer { session.invalidateAndCancel() }
        do {
            let (bytes, response) = try await session.bytes(from: URL(string: "https://raw.githubusercontent.com/Omokir/opencode-iphone/main/ios/Info.plist")!)
            guard (response as? HTTPURLResponse)?.statusCode == 200 else { throw URLError(.badServerResponse) }
            var data = Data()
            for try await byte in bytes { guard data.count < 65536 else { throw URLError(.dataLengthExceedsMaximum) }; data.append(byte) }
            let info = try PropertyListSerialization.propertyList(from: data, format: nil) as? [String: Any]
            guard let remote = info?["CFBundleShortVersionString"] as? String else { throw URLError(.cannotParseResponse) }
            update = remote.compare(version, options: .numeric) == .orderedDescending
                ? "Código mais novo: \(remote). Confira build antes de instalar."
                : "Código público: \(remote). Versão instalada não está atrás desse código."
        } catch { update = "Consulta indisponível. Versão instalada permanece \(version)." }
    }
}
