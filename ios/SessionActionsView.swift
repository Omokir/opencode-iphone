import SwiftUI

struct CoreCommand: Decodable, Identifiable {
    let name: String
    let description: String?
    var id: String { name }
}
struct CoreSkill: Decodable, Identifiable {
    let id: String
    let name: String
    let description: String?
}
struct CoreInbox: Decodable, Identifiable {
    let id: String
    let type: String
    let delivery: String
    let payload: Payload
    struct Payload: Decodable { let text: String? }
}
struct CoreSchedule: Decodable, Identifiable {
    let id: String
    let name: String?
    let status: String
    let runCount: Int
    let nextDueAt: Double?
}
struct CoreList<T: Decodable>: Decodable { let data: [T] }

/// User-driven writes only. An uncertain response locks writes until this sheet
/// is reopened after inspecting the conversation; never retries execution.
@MainActor struct SessionActionsView: View {
    @EnvironmentObject var api: API
    @EnvironmentObject var privacy: PrivacyLock
    @Environment(\.dismiss) private var dismiss
    let session: Session
    @State private var commands: [CoreCommand] = []
    @State private var skills: [CoreSkill] = []
    @State private var inbox: [CoreInbox] = []
    @State private var schedules: [CoreSchedule] = []
    @State private var unavailable: [String] = []
    @State private var text = ""
    @State private var prompt = ""
    @State private var date = Date().addingTimeInterval(3600)
    @State private var busy = false
    @State private var uncertain = false
    @State private var notice: String?
    @State private var selectedCommand: CoreCommand?
    @State private var selectedSkill: CoreSkill?
    var body: some View {
        NavigationStack {
            List {
                if let notice { Section { Text(notice).foregroundStyle(.secondary) } }
                if !unavailable.isEmpty {
                    Section { Text("Indisponível neste notebook: " + unavailable.joined(separator: ", ")).font(.caption) }
                }
                Section("Comandos") {
                    ForEach(commands) { item in
                        Button { selectedCommand = item } label: {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("/" + item.name).foregroundStyle(.primary)
                                if let description = item.description { Text(description).font(.caption).foregroundStyle(.secondary).lineLimit(2) }
                            }
                        }
                    }
                }
                Section("Skills") {
                    ForEach(skills) { item in
                        Button { selectedSkill = item } label: {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(item.name).foregroundStyle(.primary)
                                if let description = item.description { Text(description).font(.caption).foregroundStyle(.secondary).lineLimit(2) }
                            }
                        }
                    }
                }
                Section("Fila desta conversa") {
                    if inbox.isEmpty { Text("Nenhuma entrada pendente confirmada.").foregroundStyle(.secondary) }
                    ForEach(inbox) { item in
                        VStack(alignment: .leading, spacing: 8) {
                            Text(item.payload.text ?? item.type).lineLimit(4)
                            Text(item.delivery == "queue" ? "Na fila" : "Orientação durante execução").font(.caption).foregroundStyle(.secondary)
                            Button("Cancelar entrada", role: .destructive) {
                                Task { await write("/api/session/\(session.id)/inbox/\(API.escape(item.id))", method: "DELETE", reason: "Cancelar entrada pendente") }
                            }
                        }
                    }
                    Text("OpenCode 2.2.1 não permite editar texto já enfileirado por essa API. Cancelar não desfaz entrada já entregue.").font(.caption).foregroundStyle(.secondary)
                }
                Section("Agendamentos") {
                    ForEach(schedules) { item in
                        VStack(alignment: .leading, spacing: 8) {
                            Text(item.name ?? "Tarefa agendada").font(.headline)
                            Text("\(item.status) · \(item.runCount) execuções").font(.caption).foregroundStyle(.secondary)
                            if let due = item.nextDueAt { Text(Date(timeIntervalSince1970: due / 1000), style: .date) }
                            if item.status != "done" {
                                Button(item.status == "paused" ? "Retomar" : "Pausar") {
                                    Task { await write("/api/experimental/schedule/\(API.escape(item.id))/\(item.status == "paused" ? "resume" : "pause")", reason: "Alterar agendamento") }
                                }
                            }
                            Button("Excluir agendamento", role: .destructive) {
                                Task { await write("/api/experimental/schedule/\(API.escape(item.id))", method: "DELETE", reason: "Excluir agendamento") }
                            }
                        }
                    }
                    if !unavailable.contains("agendamentos") {
                        TextField("Tarefa para executar depois", text: $prompt, axis: .vertical).lineLimit(2...5)
                        DatePicker("Quando", selection: $date, in: Date()..., displayedComponents: [.date, .hourAndMinute])
                        Text("Notebook precisa estar disponível. Execução pode consumir cota do modelo da conversa.").font(.caption).foregroundStyle(.secondary)
                        Button("Agendar uma execução") {
                            Task { await write("/api/experimental/schedule", body: ["sessionID": session.id, "prompt": prompt, "when": ["at": ISO8601DateFormatter().string(from: date)]], reason: "Agendar execução no notebook") }
                        }.disabled(prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    }
                }
            }
            .disabled(busy || uncertain)
            .overlay { if busy { ProgressView() } }
            .navigationTitle("Recursos da conversa").navigationBarTitleDisplayMode(.inline)
            .toolbar { Button("Fechar") { dismiss() } }
            .task { await load() }
            .refreshable { await load() }
            .sheet(item: $selectedCommand) { item in
                NavigationStack {
                    Form {
                        Text(item.description ?? "Executar comando no notebook.")
                        TextField("Argumentos", text: $text, axis: .vertical)
                        Button("Executar /" + item.name) {
                            selectedCommand = nil
                            Task { await write("/api/session/\(session.id)/command", body: ["name": item.name, "text": text], reason: "Executar /" + item.name) }
                        }
                    }.navigationTitle(item.name).toolbar { Button("Cancelar") { selectedCommand = nil } }
                }
            }
            .alert(item: $selectedSkill) { item in
                Alert(title: Text("Ativar \(item.name)?"), message: Text("Adiciona skill e retoma execução desta conversa."), primaryButton: .default(Text("Ativar")) {
                    Task { await write("/api/experimental/session/\(session.id)/skill", body: ["id": item.id, "resume": true], reason: "Ativar skill") }
                }, secondaryButton: .cancel())
            }
        }
    }
    private func load() async {
        let server = api.server; let connection = api.connectionID
        let location = "?location%5Bdirectory%5D=" + API.escape(session.location.directory)
        var missing: [String] = []
        let c: CoreList<CoreCommand>? = try? await api.request("/api/command" + location)
        let s: CoreList<CoreSkill>? = try? await api.request("/api/skill" + location)
        let i: CoreList<CoreInbox>? = try? await api.request("/api/session/\(session.id)/inbox")
        let a: CoreList<CoreSchedule>? = try? await api.request("/api/experimental/schedule?sessionID=" + API.escape(session.id))
        guard api.server == server, api.connectionID == connection, !Task.isCancelled else { return }
        if c == nil { missing.append("comandos") }; if s == nil { missing.append("skills") }
        if i == nil { missing.append("fila") }; if a == nil { missing.append("agendamentos") }
        commands = c?.data ?? []; skills = s?.data ?? []; inbox = i?.data ?? []; schedules = a?.data ?? []; unavailable = missing
    }
    private func write(_ path: String, method: String = "POST", body: [String: Any]? = nil, reason: String) async {
        guard !busy, !uncertain else { return }
        let connection = api.connectionID
        busy = true; defer { busy = false }
        guard await privacy.confirm(reason), api.connected, api.connectionID == connection else { return }
        do {
            let _: EmptyResponse = try await api.request(path, method: method, body: body)
            guard api.connectionID == connection else { return }
            notice = "Solicitação aceita. Confira estado atualizado abaixo."; prompt = ""; text = ""
            await load()
        } catch {
            uncertain = true
            notice = "Solicitação não confirmada. Confira conversa antes de repetir. " + error.localizedDescription
        }
    }
}
