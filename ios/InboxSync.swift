import SwiftUI
import Combine
import CryptoKit

@MainActor final class InboxSync: ObservableObject {
    @Published var enabledServer = UserDefaults.standard.string(forKey: "inbox.enabledServer") ?? ""
    @Published var status = "Desativado"
    @Published var busy = false
    @Published var lastError: String?
    @Published var paused = UserDefaults.standard.bool(forKey: "inbox.paused") {
        didSet { UserDefaults.standard.set(paused, forKey: "inbox.paused") }
    }
    @Published var completedBytes: Int64 = 0
    @Published var totalBytes: Int64 = 0
    @Published var bytesPerSecond: Double = 0
    @Published var queue: [String] = []
    @Published var activeName: String?
    @Published var activePhase = "Aguardando"
    @Published var backgroundEnabled = UserDefaults.standard.bool(forKey: "inbox.background")
    @Published var history: [InboxRecord] = InboxRecord.load()
    @Published var removeAfterTransfer = UserDefaults.standard.object(forKey: "inbox.removeAfterTransfer") == nil ? !(UserDefaults.standard.string(forKey: "inbox.enabledServer") ?? "").isEmpty : UserDefaults.standard.bool(forKey: "inbox.removeAfterTransfer")
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
        paused = false
        if !value { BackgroundInbox.shared.cancelAll() }
    }
    func setBackground(_ value: Bool) {
        backgroundEnabled = value
        UserDefaults.standard.set(value, forKey: "inbox.background")
        if !value { paused = true; BackgroundInbox.shared.cancelAll() }
    }
    func setRemoval(_ value: Bool) {
        removeAfterTransfer = value
        UserDefaults.standard.set(value, forKey: "inbox.removeAfterTransfer")
    }
    func record(_ name: String, path: String, server: String, removed: Bool) {
        history.insert(InboxRecord(id: UUID(), name: name, path: path, serverKey: HistoryCache.key(server), date: Date(), removed: removed), at: 0)
        history = Array(history.prefix(100)); InboxRecord.save(history)
    }
    private func mayContinue(_ api: API, server: String) -> Bool {
        InboxAdmission.allows(connected: api.connected, enabledServer: enabledServer, currentServer: api.server,
                              admittedServer: server, paused: paused, cancelled: Task.isCancelled)
    }
    func sync(_ api: API) async {
        guard !busy, !paused, api.connected, enabledServer == api.server else { return }
        if let job = BackgroundInbox.shared.active(server: api.server) {
            status = "Transferência entregue ao iOS: \(job.name). Original preservado até verificação em primeiro plano."
            activeName = job.name; activePhase = "Segundo plano"; totalBytes = job.size; completedBytes = job.sent
            return
        }
        let server = api.server
        busy = true
        defer { busy = false }
        do {
            let folder = try Self.folder()
            let entries = try FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: [.isRegularFileKey, .isSymbolicLinkKey], options: [.skipsHiddenFiles])
                .sorted { $0.lastPathComponent.localizedStandardCompare($1.lastPathComponent) == .orderedAscending }
            queue = entries.map(\.lastPathComponent)
            guard !entries.isEmpty else { status = "Pasta vazia. Salve arquivos nela pelo app Arquivos."; lastError = nil; return }
            let _: BrowserLocation = try await api.request("/phone/inbox/prepare", method: "POST")
            for source in entries {
                try Task.checkCancellation()
                guard mayContinue(api, server: server) else { return }
                let info = try source.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey])
                guard info.isRegularFile == true, info.isSymbolicLink != true else { continue }
                activeName = source.lastPathComponent; activePhase = "Verificando"
                status = "Verificando \(source.lastPathComponent)…"
                let staged = try await Task.detached(priority: .utility) { try InboxLocalFiles.inspect(source) }.value
                let keyData = Data((server + "|" + source.lastPathComponent + "|" + staged.sha256).utf8)
                let key = "inbox.job." + SHA256.hash(data: keyData).map { String(format: "%02x", $0) }.joined()
                if UserDefaults.standard.bool(forKey: key + ".copied") { queue.removeAll { $0 == source.lastPathComponent }; continue }
                let identifier: UUID
                if let saved = UserDefaults.standard.string(forKey: key), let id = UUID(uuidString: saved) { identifier = id }
                else { identifier = UUID(); UserDefaults.standard.set(identifier.uuidString, forKey: key) }
                let path = "Downloads/" + Self.folderName + "/" + identifier.uuidString.lowercased() + "-" + staged.name
                let file = StagedUpload(id: identifier, url: staged.url, name: staged.name, size: staged.size, sha256: staged.sha256)
                guard mayContinue(api, server: server) else { return }
                totalBytes = file.size; completedBytes = 0; bytesPerSecond = 0
                if try await verification(api, path: path, id: identifier) == nil {
                    if backgroundEnabled, file.size <= PrivateTransferFiles.maxBytes {
                        try await BackgroundInbox.shared.enqueue(api, file: file, path: path, permitted: { self.backgroundEnabled && self.mayContinue(api, server: server) })
                        status = "Envio agendado no iOS. Verificação e remoção somente ao reabrir Pocket."
                        return
                    }
                    status = "Enviando \(staged.name)…"
                    activePhase = "Enviando"
                    let started = Date()
                    var resumedAt: Int64?
                    try await api.uploadResumable(file, path: path, permitted: { self.mayContinue(api, server: server) }, progress: { bytes in
                        if resumedAt == nil { resumedAt = bytes }
                        self.completedBytes = bytes
                        self.bytesPerSecond = Double(bytes - (resumedAt ?? 0)) / max(0.1, Date().timeIntervalSince(started))
                    })
                }
                status = "Verificando conteúdo gravado: \(staged.name)…"
                activePhase = "Verificando"
                // A receipt alone is insufficient: re-read actual committed bytes.
                guard mayContinue(api, server: server),
                      let verified = try await verification(api, path: path, id: identifier),
                      verified.root == "home", verified.path == path,
                      verified.uploadID.lowercased() == identifier.uuidString.lowercased(),
                      verified.sha256 == file.sha256, verified.size == file.size else {
                    throw TransferFailure.message("Conteúdo no computador não confirmado. Original preservado.")
                }
                guard mayContinue(api, server: server) else { return }
                if removeAfterTransfer {
                    try await Task.detached(priority: .utility) { try InboxLocalFiles.removeUnchanged(source, digest: file.sha256, size: file.size) }.value
                    UserDefaults.standard.removeObject(forKey: key)
                    status = "Transferido e verificado: \(file.name). Original local removido."
                    record(file.name, path: path, server: server, removed: true)
                } else {
                    UserDefaults.standard.set(true, forKey: key + ".copied")
                    status = "Cópia verificada: \(file.name). Original mantido no iPhone."
                    record(file.name, path: path, server: server, removed: false)
                }
                completedBytes = totalBytes
                queue.removeAll { $0 == source.lastPathComponent }
                activeName = nil; activePhase = "Concluído"
                lastError = nil
            }
        } catch is CancellationError { status = "Pausado; arquivos pendentes preservados" }
        catch { lastError = ConnectionAdvice.describe(error); status = "Pendente — original preservado"; activePhase = "Falhou"; paused = true }
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
    @EnvironmentObject var privacy: PrivacyLock
    @State private var confirmRemoval = false
    @ObservedObject private var background = BackgroundInbox.shared
    var body: some View {
        NavigationStack {
            Form {
                Section("Pasta no iPhone") {
                    Text(InboxSync.folderName).font(.headline)
                    Text("Arquivos → No Meu iPhone → OpenCode Pocket → Iphone 11 Omoki. Salve imagens, documentos e outros arquivos diretamente nessa pasta.")
                    Text("Envio retomável até 1 TiB por arquivo; depende do espaço livre e conexão. Subpastas e links não são enviados.").font(.caption)
                }
                Section("Mover para computador") {
                    Toggle("Ativar transferência automática", isOn: Binding(get: { inbox.enabledServer == api.server }, set: { value in
                        Task { if await privacy.confirm("Autorizar transferência da pasta do iPhone") { inbox.setEnabled(value, server: api.server) } }
                    }))
                    Toggle("Remover original após verificar", isOn: Binding(get: { inbox.removeAfterTransfer }, set: { value in
                        if value { confirmRemoval = true } else { inbox.setRemoval(false) }
                    })).disabled(inbox.busy)
                    Text(inbox.removeAfterTransfer ? "Modo mover: remove original somente após verificar bytes gravados." : "Modo copiar: mantém original no iPhone; conteúdo alterado será nova transferência.").font(.caption).foregroundStyle(.secondary)
                    Text("Destino: ~/Downloads/Iphone 11 Omoki. Nomes recebem identificador único; nada é sobrescrito. Após verificar bytes gravados no computador, original é apagado desta pasta do iPhone. Não há desfazer no app.").font(.caption)
                    Text("Funciona com Pocket aberto e computador conectado. iOS pode suspender ao sair; arquivos pendentes ficam no iPhone. Desativar impede próximas remoções, mas não desfaz transferências já concluídas.").font(.caption)
                }
                Section("Estado") {
                    Toggle("Continuar envio iniciado em segundo plano", isOn: Binding(get: { inbox.backgroundEnabled }, set: { value in Task { if await privacy.confirm("Alterar transferência em segundo plano") { inbox.setBackground(value) } } }))
                    Text("Opcional: arquivos até 64 MiB usam cópia imutável privada, acessível ao sistema após primeiro desbloqueio. Exige espaço extra no iPhone. Originais só podem ser apagados após voltar ao Pocket e verificar computador. Maiores continuam por blocos com app aberto. Não monitora pasta continuamente fora do app.").font(.caption)
                    Text("iOS decide quando executar. Encerrar app pelo seletor cancela transferências. Tailscale precisa continuar conectado. Desativar solicita cancelamento, mas não desfaz gravação já recebida.").font(.caption).foregroundStyle(.secondary)
                    Text(inbox.status)
                    if inbox.busy { ProgressView() }
                    if inbox.totalBytes > 0 {
                        ProgressView(value: Double(inbox.completedBytes), total: Double(inbox.totalBytes))
                        Text("\(ByteCountFormatter.string(fromByteCount: inbox.completedBytes, countStyle: .file)) / \(ByteCountFormatter.string(fromByteCount: inbox.totalBytes, countStyle: .file)) · \(ByteCountFormatter.string(fromByteCount: Int64(inbox.bytesPerSecond), countStyle: .file))/s").font(.caption.monospacedDigit())
                    }
                    Button(inbox.paused ? "Retomar fila" : "Pausar fila") { inbox.paused.toggle(); if inbox.paused { background.cancelAll() } }
                    if let error = inbox.lastError { Text(error).foregroundStyle(.red) }
                    Button("Sincronizar agora") { Task { await inbox.sync(api) } }.disabled(inbox.busy || inbox.enabledServer != api.server)
                }
                Section("Fila") {
                    ForEach(inbox.queue, id: \.self) { name in
                        HStack { Text(name).font(.caption); Spacer(); Text(inbox.activeName == name ? (inbox.paused ? "Pausado" : inbox.activePhase) : "Aguardando").font(.caption2).foregroundStyle(.secondary) }
                    }
                    if inbox.queue.isEmpty { Text("Sem arquivos pendentes na última consulta.").foregroundStyle(.secondary) }
                }
                Section("Envios entregues ao iOS") {
                    ForEach(background.jobs.filter { $0.serverKey == HistoryCache.key(api.server) }) { job in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(job.name).font(.caption.weight(.semibold))
                            Text(backgroundLabel(job.state)).font(.caption2).foregroundStyle(.secondary)
                            if job.size > 0 { ProgressView(value: Double(job.sent), total: Double(job.size)) }
                        }
                    }
                    Button("Cancelar envios de segundo plano", role: .destructive) { inbox.paused = true; background.cancelAll() }
                    Button("Limpar registros encerrados") { Task { await background.clearFinished() } }
                }
                Section("Transferências verificadas") {
                    ForEach(inbox.history.filter { $0.serverKey == HistoryCache.key(api.server) }) { item in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(item.name).font(.subheadline.weight(.semibold))
                            Text(item.removed ? "Verificado · original removido" : "Verificado · original mantido").font(.caption)
                            Text(item.path).font(.system(.caption2, design: .monospaced)).textSelection(.enabled)
                            Text(item.date, style: .date).font(.caption2).foregroundStyle(.secondary)
                        }
                    }
                }
            }
            .navigationTitle("Pasta automática").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Fechar") { dismiss() } } }
            .task { do { _ = try InboxSync.folder() } catch { inbox.lastError = error.localizedDescription } }
            .alert("Remover originais após transferência?", isPresented: $confirmRemoval) {
                Button("Ativar remoção", role: .destructive) { Task { if await privacy.confirm("Ativar remoção após transferência verificada") { inbox.setRemoval(true) } } }
                Button("Cancelar", role: .cancel) { }
            } message: { Text("Arquivos novos dessa pasta serão removidos do iPhone após verificação. Não há desfazer. Cópias anteriores mantidas não serão apagadas automaticamente.") }
        }
    }
    private func backgroundLabel(_ state: String) -> String {
        switch state {
        case "queued": return "Agendado pelo iOS"
        case "sending": return "Enviando pelo iOS"
        case "uploaded": return "Recebido · verificação final pendente no Pocket"
        case "cancelled": return "Cancelamento solicitado · confira destino"
        default: return "Resultado incerto · original preservado; consulte destino ao retomar"
        }
    }
}
