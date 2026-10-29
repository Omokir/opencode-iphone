import SwiftUI

@MainActor struct PendingActivityView: View {
    struct Pending: Decodable, Identifiable {
        let id: String
        let sessionID: String
        let title: String?
        let action: String?
    }
    @EnvironmentObject var api: API
    @Environment(\.dismiss) private var dismiss
    let directories: [String]
    @State private var directory = ""
    @State private var permissions: [Pending] = []
    @State private var questions: [Pending] = []
    @State private var error: String?
    @State private var loading = false
    var body: some View {
        NavigationStack {
            List {
                Section {
                    Picker("Projeto", selection: $directory) {
                        ForEach(directories, id: \.self) { Text($0).tag($0) }
                    }
                    Text("Pendências de todas as conversas do projeto selecionado. Projetos listados vêm do histórico carregado.").font(.caption).foregroundStyle(.secondary)
                }
                if let error { Text(error).foregroundStyle(.secondary) }
                Section("Aprovações") {
                    ForEach(permissions) { item in
                        NavigationLink { KzLTaskDestination(id: item.sessionID) } label: {
                            Label(item.action ?? "Revisar aprovação", systemImage: "hand.raised")
                        }
                    }
                }
                Section("Perguntas") {
                    ForEach(questions) { item in
                        NavigationLink { KzLTaskDestination(id: item.sessionID) } label: {
                            Label(item.title ?? "Responder pergunta", systemImage: "questionmark.bubble")
                        }
                    }
                }
                if !loading && error == nil && permissions.isEmpty && questions.isEmpty {
                    Text("Nenhuma pendência confirmada neste projeto.").foregroundStyle(.secondary)
                }
            }.navigationTitle("Atividade")
                .toolbar { Button("Fechar") { dismiss() } }
                .overlay { if loading { ProgressView() } }
                .onAppear { if directory.isEmpty { directory = directories.first ?? "" } }
                .task(id: directory) { await load() }
                .refreshable { await load() }
        }
    }
    private func load() async {
        guard !directory.isEmpty else { return }
        let selected = directory; let connection = api.connectionID
        loading = true; permissions = []; questions = []; error = nil
        defer { if directory == selected { loading = false } }
        do {
            let query = "?location%5Bdirectory%5D=" + API.escape(selected)
            let p: CoreList<Pending> = try await api.request("/api/permission/request" + query)
            let q: CoreList<Pending> = try await api.request("/api/form" + query)
            guard !Task.isCancelled, directory == selected, api.connectionID == connection else { return }
            permissions = p.data; questions = q.data
        } catch {
            if directory == selected && !Task.isCancelled { self.error = "Não foi possível confirmar pendências. " + error.localizedDescription }
        }
    }
}
