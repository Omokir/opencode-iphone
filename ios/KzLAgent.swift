import Foundation
import SwiftUI

struct KzLTask: Decodable, Identifiable {
    let id: String
    let parent: String
    let child: String
    let request: String
    let text: String
    let state: String
    let result: String
    let revision: Int
    let created: Double
    let updated: Double
    let confirmed: Bool
    var terminal: Bool { ["completed", "failed", "cancelled", "uncertain"].contains(state) }
    var canCancel: Bool { !["completed", "failed", "cancelled"].contains(state) }
    var label: String {
        if !confirmed && !terminal && state != "queued" { return "Estado sem confirmação recente · conferir notebook" }
        switch state {
        case "queued": return "Na fila"
        case "creating", "sending": return "Encaminhando"
        case "admitted": return "Recebida pelo OpenCode"
        case "running": return "Executando"
        case "waiting": return "Aguardando sua resposta"
        case "completed": return "Concluída"
        case "failed": return "Falhou"
        case "cancelled": return "Interrompida"
        case "cancelling": return "Interrupção solicitada"
        default: return "Resultado incerto · conferir"
        }
    }
    var payload: [String: Any] {
        ["id": id, "sessionID": child, "task": text, "state": state, "confirmed": confirmed, "result": String(result.prefix(6000)), "revision": revision]
    }
}

struct KzLTaskList: Decodable { let tasks: [KzLTask] }
struct KzLMemory: Decodable {
    struct Turn: Decodable, Identifiable {
        let id: String
        let role: String
        let text: String
        let created: Double
        var message: Message {
            Message(id: id, type: role, text: text, content: nil, time: .init(created: created, completed: created), error: nil, files: nil)
        }
    }
    let turns: [Turn]
}

struct KzLTaskDestination: View {
    @EnvironmentObject var api: API
    let id: String
    @State private var session: Session?
    @State private var error: String?
    var body: some View {
        Group {
            if let session { ChatView(session: session) }
            else if let error { ContentUnavailableView("Tarefa indisponível", systemImage: "wifi.exclamationmark", description: Text(error)) }
            else { ProgressView("Abrindo tarefa…") }
        }.task(id: id) {
            do { let item: Item<Session> = try await api.request("/api/session/\(id)"); session = item.data }
            catch { self.error = error.localizedDescription }
        }
    }
}

struct KzLTasksView: View {
    @EnvironmentObject var api: API
    @Environment(\.scenePhase) var phase
    @State private var tasks: [KzLTask] = []
    @State private var turns: [KzLMemory.Turn] = []
    @State private var error: String?
    var body: some View {
        List {
            Section {
                Text("Tarefas continuam no notebook após encerrar chamada. Permissões e perguntas ficam na conversa vinculada. Resultados incertos não são reenviados.").font(.caption)
                if let error { Text(error).foregroundStyle(.red) }
            }
            Section("Tarefas persistentes") {
                if tasks.isEmpty { Text("Nenhuma tarefa delegada ainda.").foregroundStyle(.secondary) }
                ForEach(tasks) { task in
                    NavigationLink { KzLTaskDestination(id: task.child) } label: {
                        VStack(alignment: .leading, spacing: 5) {
                            Text(task.text).lineLimit(2)
                            Label(task.label, systemImage: task.terminal ? "checklist" : "gearshape.2")
                                .font(.caption).foregroundStyle(task.state == "waiting" ? Color.orange : Color.secondary)
                            if !task.result.isEmpty { Text(task.result).font(.caption).lineLimit(3).foregroundStyle(.secondary) }
                        }
                    }
                }
            }
            Section("Histórico de voz · recente") {
                Text("Texto salvo no notebook; áudio não é gravado. Transcrição pode ter erros. Chamadas novas recebem contexto limitado, não memória ilimitada.").font(.caption).foregroundStyle(.secondary)
                ForEach(turns) { turn in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(turn.role == "user" ? "Você · voz" : "Agente KzL · voz").font(.caption.weight(.semibold))
                        Text(turn.text).textSelection(.enabled)
                    }
                }
            }
        }.navigationTitle("Agente KzL · atividade")
            .refreshable { await refresh() }
            .task(id: phase) {
                guard phase == .active else { return }
                while !Task.isCancelled {
                    await refresh()
                    do { try await Task.sleep(for: .seconds(3)) } catch { return }
                }
            }
    }
    private func refresh() async {
        let server = api.server; let connection = api.connectionID
        do {
            let list: KzLTaskList = try await api.request("/phone/kzl/tasks")
            let memory: KzLMemory = try await api.request("/phone/kzl/memory")
            guard api.connected, api.server == server, api.connectionID == connection, !Task.isCancelled else { return }
            tasks = list.tasks; turns = memory.turns; error = nil
        } catch { self.error = error.localizedDescription }
    }
}
