import SwiftUI

struct TransferCenterView: View {
    @EnvironmentObject var api: API
    @EnvironmentObject var inbox: InboxSync
    @Environment(\.scenePhase) private var phase
    @ObservedObject private var manual = TransferActivity.shared
    @ObservedObject private var background = BackgroundInbox.shared
    @State private var inboxSettings = false
    @State private var notice: String?
    @State private var checking = false
    var body: some View {
        List {
            Section("Pasta automática") {
                Text(inbox.status).font(.subheadline)
                if inbox.totalBytes > 0 { ProgressView(value: Double(inbox.completedBytes), total: Double(inbox.totalBytes)) }
                Button(inbox.paused ? "Retomar fila autorizada" : "Pausar fila") {
                    inbox.paused.toggle(); if inbox.paused { background.cancelAll() }
                }.disabled(inbox.enabledServer != api.server)
                Button("Configurar pasta e modo copiar/mover") { inboxSettings = true }
                Text("Retomar vale somente para fila automática já autorizada. Envios manuais incertos não são repetidos por este painel.").font(.caption).foregroundStyle(.secondary)
            }
            Section("Manuais · enviar e baixar") {
                ForEach(manual.records.filter { $0.serverKey == TaskHistory.serverKey(api.server) }) { item in
                    VStack(alignment: .leading, spacing: 6) {
                        Label(item.name, systemImage: item.direction == "upload" ? "arrow.up.doc" : "arrow.down.doc").font(.headline)
                        Text(TransferActivity.label(item.state)).font(.caption)
                        Text(item.destination).font(.system(.caption2, design: .monospaced)).textSelection(.enabled)
                        if let total = item.total, total > 0 { ProgressView(value: Double(min(item.completed, total)), total: Double(total)) }
                        Text(ByteCountFormatter.string(fromByteCount: item.completed, countStyle: .file)).font(.caption.monospacedDigit())
                        if ["sending", "receiving", "verifying"].contains(item.state) { Button("Solicitar cancelamento", role: .destructive) { manual.cancel(item.id) } }
                        if item.state == "uncertain", item.uploadID != nil { Button("Conferir recibo, sem reenviar") { Task { await receipt(item) } }.disabled(checking) }
                    }
                }
            }
            Section("Entregues ao iOS") {
                ForEach(background.jobs.filter { job in
                    job.serverKey == TaskHistory.serverKey(api.server) && !inbox.history.contains { $0.path == job.path && $0.serverKey == job.serverKey }
                }) { job in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(job.name).font(.headline)
                        Text(["uploaded": "Upload recebido · verificação pendente", "sending": "Enviando pelo iOS", "queued": "Agendado pelo iOS", "cancelled": "Cancelamento solicitado"][job.state] ?? "Resultado incerto · original preservado").font(.caption)
                        if job.size > 0 { ProgressView(value: Double(min(job.sent, job.size)), total: Double(job.size)) }
                        Text(job.path).font(.system(.caption2, design: .monospaced)).textSelection(.enabled)
                    }
                }
            }
            Section("Pasta automática · verificados") {
                ForEach(inbox.history.filter { $0.serverKey == TaskHistory.serverKey(api.server) }) { item in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(item.name).font(.headline)
                        Text(item.removed ? "Verificado · original removido pela sua configuração" : "Verificado · original mantido").font(.caption)
                        Text(item.path).font(.system(.caption2, design: .monospaced)).textSelection(.enabled)
                    }
                }
            }
            if let notice { Text(notice).font(.caption).foregroundStyle(.secondary) }
            Text("Progresso representa bytes observados, não conclusão de checksum. Recibo antigo não prova conteúdo atual; downloads ficam em cache até você salvar em Arquivos.").font(.caption).foregroundStyle(.secondary)
        }.navigationTitle("Transferências")
            .sheet(isPresented: $inboxSettings) { InboxSyncView() }
            .task(id: phase) {
                guard phase == .active else { return }
                while !Task.isCancelled {
                    await manual.observe(api)
                    do { try await Task.sleep(for: .seconds(1)) } catch { break }
                }
            }
    }
    func receipt(_ item: TransferActivity.Record) async {
        guard let uploadID = item.uploadID, !checking else { return }
        let server = api.server
        checking = true; defer { checking = false }
        do {
            let result: UploadReceipt = try await api.request("/phone/files/receipt?id=" + uploadID.uuidString)
            guard server == api.server, api.connected,
                  UUID(uuidString: result.uploadID) == uploadID, result.root == item.root,
                  result.path == item.remotePath, result.sha256 == item.digest, result.size == item.total else { throw PhoneError.message("Recibo não corresponde ao envio.") }
            manual.finish(item.id, state: "receipt")
            notice = "Recibo corresponde ao envio. Consulte pasta para estado atual; nada foi reenviado."
        } catch { notice = "Sem confirmação correspondente. Confira destino antes de nova tentativa; nenhum envio repetido." }
    }
}
