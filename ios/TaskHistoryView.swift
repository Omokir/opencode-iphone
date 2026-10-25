import SwiftUI

struct TaskHistoryView: View {
    @EnvironmentObject var api: API
    @ObservedObject private var history = TaskHistory.shared
    @State private var error: String?
    @State private var checking = false
    var body: some View {
        List {
            Section {
                Text("Envios de texto/voz neste iPhone. Reiniciar ou perder acompanhamento marca resultado incerto, sem repetir comandos. Resposta concluída não garante que todos os efeitos desejados ocorreram.").font(.caption)
            }
            ForEach(history.records.filter { $0.serverKey == TaskHistory.serverKey(api.server) }) { record in
                Section {
                    Text(record.title).font(.headline).textSelection(.enabled)
                    Label(TaskHistory.label(record.state), systemImage: record.state == "uncertain" ? "questionmark.circle" : record.state == "completed" ? "checkmark.circle" : "clock")
                        .font(.caption).foregroundStyle(record.state == "uncertain" ? Color.orange : .secondary)
                    Text(record.date, style: .date).font(.caption2).foregroundStyle(.secondary)
                    if let result = record.resultID { NavigationLink("Abrir resposta identificada") { SearchMessageDetail(sessionID: record.sessionID, messageID: result) } }
                    NavigationLink("Abrir conversa") { TaskConversationLoader(sessionID: record.sessionID) }
                    Button("Consultar estado sem reenviar") { Task { await check(record) } }.disabled(checking || !api.connected)
                }
            }
            if let message = history.storageError { Text(message).font(.caption).foregroundStyle(.red) }
            if let error { Text(error).font(.caption).foregroundStyle(.secondary) }
        }.navigationTitle("Tarefas deste iPhone")
    }
    func check(_ record: TaskHistory.Record) async {
        guard !checking else { return }; checking = true; defer { checking = false }
        let server = api.server
        do {
            let info: Item<Session> = try await api.request("/api/session/\(record.sessionID)")
            let page: Page<Message> = try await api.request("/api/session/\(record.sessionID)/message?limit=50&order=desc")
            let permissions: Page<Permission> = try await api.request("/api/session/\(record.sessionID)/permission")
            let questions: Page<QuestionForm> = try await api.request("/api/session/\(record.sessionID)/form")
            guard server == api.server, api.connected else { return }
            history.reconcile(server: server, session: info.data, messages: page.data, waitingPermission: !permissions.data.isEmpty, waitingQuestion: !questions.data.isEmpty)
            error = "Consulta feita. Se envio não estiver na página recente ou houver escrita simultânea, abra conversa para conferir. Nenhum comando repetido."
        } catch { self.error = ConnectionAdvice.describe(error) }
    }
}

struct TaskConversationLoader: View {
    @EnvironmentObject var api: API
    let sessionID: String
    @State private var session: Session?
    @State private var error: String?
    var body: some View {
        Group {
            if let session { ChatView(session: session) }
            else if let error { Text(error).padding() }
            else { ProgressView() }
        }.task {
            if let cached: Item<Session> = api.cached("/api/session/\(sessionID)") { session = cached.data }
            do { let info: Item<Session> = try await api.request("/api/session/\(sessionID)"); session = info.data }
            catch { if session == nil { self.error = ConnectionAdvice.describe(error) } }
        }
    }
}
