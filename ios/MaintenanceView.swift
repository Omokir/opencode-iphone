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
    @State private var readyBuild: VerifiedUpdate?
    @State private var lastCheck: Date?
    private var version: String { Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "—" }
    private var diagnostics: String {
        "OpenCode Pocket \(version)\niOS \(UIDevice.current.systemVersion)\nPareado: \(api.connected ? "sim" : "não")\nÚltima conexão HTTP: \(api.reachable.map { $0 ? "respondeu" : "falhou" } ?? "não consultada")\nControle remoto sem USB: não suportado\nSem tokens, domínio, IDs, arquivos ou conteúdo de conversas."
    }
    var body: some View {
        Form {
            Section("Versão") {
                LabeledContent("Instalada", value: version)
                LabeledContent("Build instalado", value: Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "—")
                Text(update).font(.caption)
                Button("Procurar IPA com build aprovado") { Task { await checkUpdate() } }.disabled(checking)
                if let readyBuild {
                    Link("Abrir \(readyBuild.version) (build \(readyBuild.build)) e baixar IPA", destination: readyBuild.runURL)
                    Link("Notas e documentação desse build", destination: readyBuild.notesURL)
                    Text("Artefato vence em: \(readyBuild.expires)").font(.caption2)
                }
                Link("Abrir builds no GitHub", destination: URL(string: "https://github.com/Omokir/opencode-iphone/actions/workflows/ios.yml")!)
                Text("Consulta pública somente ao tocar. Exige workflow concluído com sucesso e artefato não expirado do mesmo commit; versão vem desse commit, não do código em desenvolvimento. Download pode exigir login GitHub. Assinatura, instalação e teste físico são etapas separadas.").font(.caption).foregroundStyle(.secondary)
            }
            Section("Diagnóstico sem dados privados") {
                Text(diagnostics).font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                ShareLink(item: diagnostics) { Label("Compartilhar diagnóstico", systemImage: "square.and.arrow.up") }
            }
        }.navigationTitle("Manutenção")
    }
    func checkUpdate() async {
        guard !checking else { return }
        if let lastCheck, Date().timeIntervalSince(lastCheck) < 60 { update = "Aguarde um minuto antes de consultar novamente."; return }
        checking = true; defer { checking = false }
        lastCheck = Date(); readyBuild = nil
        do {
            let build = try await VerifiedUpdate.fetch(); readyBuild = build
            let installedBuild = Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "0"
            update = build.newer(than: version, build: installedBuild) ? "Atualização com build aprovado: \(build.version), build \(build.build)." : "Último IPA aprovado: \(build.version), build \(build.build). Instalada não está atrás dele."
        } catch { update = "Atualização não confirmada: \(error.localizedDescription). Instalada permanece \(version)." }
    }
}
