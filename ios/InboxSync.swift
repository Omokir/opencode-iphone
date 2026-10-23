import SwiftUI
import Combine
import CryptoKit

@MainActor final class InboxSync: ObservableObject {
    @Published var enabledServer = UserDefaults.standard.string(forKey: "inbox.enabledServer") ?? ""
    @Published var status = "Desativado"
    @Published var busy = false
    @Published var lastError: String?
    static let folderName = "Iphone 11 Omoki"

    static func folder() throws -> URL {
        let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let url = documents.appendingPathComponent(folderName, isDirectory: true)
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        return url
    }
    func setEnabled(_ value: Bool, server: String) {
        enabledServer = value ? server : ""
        UserDefaults.standard.set(enabledServer, forKey: "inbox.enabledServer")
        status = value ? "Aguardando arquivos…" : "Desativado; arquivos locais preservados"
    }
    func sync(_ api: API) async {
        guard !busy, api.connected, enabledServer == api.server else { return }
        let server = api.server
        busy = true
        defer { busy = false }
        do {
            let folder = try Self.folder()
            let entries = try FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: [.isRegularFileKey, .isSymbolicLinkKey], options: [.skipsHiddenFiles])
            guard !entries.isEmpty else { status = "Pasta vazia. Salve arquivos nela pelo app Arquivos."; lastError = nil; return }
            let _: BrowserLocation = try await api.request("/phone/inbox/prepare", method: "POST")
            for source in entries {
                try Task.checkCancellation()
                guard enabledServer == server, api.server == server else { return }
                let info = try source.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey])
                guard info.isRegularFile == true, info.isSymbolicLink != true else { continue }
                status = "Verificando \(source.lastPathComponent)…"
                let staged = try await Task.detached(priority: .utility) { try InboxLocalFiles.inspect(source) }.value
                let keyData = Data((server + "|" + source.lastPathComponent + "|" + staged.sha256).utf8)
                let key = "inbox.job." + SHA256.hash(data: keyData).map { String(format: "%02x", $0) }.joined()
                let identifier: UUID
                if let saved = UserDefaults.standard.string(forKey: key), let id = UUID(uuidString: saved) { identifier = id }
                else { identifier = UUID(); UserDefaults.standard.set(identifier.uuidString, forKey: key) }
                let path = "Downloads/" + Self.folderName + "/" + identifier.uuidString.lowercased() + "-" + staged.name
                let file = StagedUpload(id: identifier, url: staged.url, name: staged.name, size: staged.size, sha256: staged.sha256)
                guard enabledServer == server, api.server == server else { return }
                if try await verification(api, path: path, id: identifier) == nil {
                    status = "Enviando \(staged.name)…"
                    let _: UploadReceipt = try await api.uploadFile(file, root: "home", path: path, expected: nil, inbox: true)
                }
                // A receipt alone is insufficient: re-read actual committed bytes.
                guard enabledServer == server, api.server == server,
                      let verified = try await verification(api, path: path, id: identifier),
                      verified.root == "home", verified.path == path,
                      verified.uploadID.lowercased() == identifier.uuidString.lowercased(),
                      verified.sha256 == file.sha256, verified.size == file.size else {
                    throw TransferFailure.message("Conteúdo no computador não confirmado. Original preservado.")
                }
                guard enabledServer == server, api.server == server, !Task.isCancelled else { return }
                try await Task.detached(priority: .utility) { try InboxLocalFiles.removeUnchanged(source, digest: file.sha256, size: file.size) }.value
                UserDefaults.standard.removeObject(forKey: key)
                status = "Transferido e verificado: \(file.name). Original local removido."
                lastError = nil
            }
        } catch is CancellationError { status = "Pausado; arquivos pendentes preservados" }
        catch { lastError = error.localizedDescription; status = "Pendente — original preservado" }
    }
    private func verification(_ api: API, path: String, id: UUID) async throws -> UploadReceipt? {
        var request = try api.makeRequest("/phone/inbox/verify?path=" + API.escape(path) + "&id=" + id.uuidString)
        request.timeoutInterval = 3600
        let (data, response) = try await api.transport.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw TransferFailure.message("Verificação indisponível.") }
        if http.statusCode == 404 { return nil }
        guard http.statusCode == 200 else { throw TransferFailure.message("Verificação falhou. Original preservado.") }
        return try JSONDecoder().decode(UploadReceipt.self, from: data)
    }
}

struct InboxSyncView: View {
    @EnvironmentObject var api: API
    @EnvironmentObject var inbox: InboxSync
    @Environment(\.dismiss) var dismiss
    var body: some View {
        NavigationStack {
            Form {
                Section("Pasta no iPhone") {
                    Text(InboxSync.folderName).font(.headline)
                    Text("Arquivos → No Meu iPhone → OpenCode Pocket → Iphone 11 Omoki. Salve imagens, documentos e outros arquivos diretamente nessa pasta.")
                    Text("Sem limite fixo por arquivo; depende do espaço livre e conexão. Subpastas e links não são enviados.").font(.caption)
                }
                Section("Mover para computador") {
                    Toggle("Ativar envio e remoção após verificar", isOn: Binding(get: { inbox.enabledServer == api.server }, set: { inbox.setEnabled($0, server: api.server) }))
                    Text("Destino: ~/Downloads/Iphone 11 Omoki. Nomes recebem identificador único; nada é sobrescrito. Após verificar bytes gravados no computador, original é apagado desta pasta do iPhone. Não há desfazer no app.").font(.caption)
                    Text("Funciona com Pocket aberto e computador conectado. iOS pode suspender ao sair; arquivos pendentes ficam no iPhone. Desativar impede próximas remoções, mas não desfaz transferências já concluídas.").font(.caption)
                }
                Section("Estado") {
                    Text(inbox.status)
                    if inbox.busy { ProgressView() }
                    if let error = inbox.lastError { Text(error).foregroundStyle(.red) }
                    Button("Sincronizar agora") { Task { await inbox.sync(api) } }.disabled(inbox.busy || inbox.enabledServer != api.server)
                }
            }
            .navigationTitle("Pasta automática").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Fechar") { dismiss() } } }
            .task { do { _ = try InboxSync.folder() } catch { inbox.lastError = error.localizedDescription } }
        }
    }
}
