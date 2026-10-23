import SwiftUI

struct ProjectsView: View {
    @EnvironmentObject var api: API
    @EnvironmentObject var projects: ProjectFavorites
    @Environment(\.dismiss) var dismiss
    @State private var name = ""
    @State private var directory = ""
    @State private var error: String?
    @State private var busy = false
    let created: (Session) -> Void
    var body: some View {
        NavigationStack {
            Form {
                Section("Favoritos deste notebook") {
                    ForEach(projects.list(server: api.server)) { project in
                        VStack(alignment: .leading, spacing: 8) {
                            Button { Task { await create(project) } } label: { Label(project.name, systemImage: "folder.badge.plus") }
                                .disabled(busy || api.reachable == false)
                            Text(project.directory).font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                        }.swipeActions { Button("Remover favorito", role: .destructive) { projects.remove(project.id, server: api.server) } }
                    }
                    if projects.list(server: api.server).isEmpty { Text("Salve uma pasta ou favorite projeto pelo menu de uma conversa.").foregroundStyle(.secondary) }
                    Text("Toque para criar conversa nessa pasta. Não envia mensagem nem executa tarefa automaticamente.").font(.caption)
                }
                Section("Adicionar projeto") {
                    TextField("Nome", text: $name)
                    TextField("/home/usuario/projeto", text: $directory).textInputAutocapitalization(.never).autocorrectionDisabled()
                    Button("Salvar favorito") {
                        do { try projects.add(server: api.server, name: name, directory: directory); name = ""; directory = ""; error = nil }
                        catch { self.error = error.localizedDescription }
                    }.disabled(busy)
                }
                if busy { ProgressView() }
                if let error { Text(error).foregroundStyle(.red) }
            }.navigationTitle("Projetos favoritos")
                .toolbar { Button("Fechar") { dismiss() } }
        }
    }
    func create(_ project: ProjectFavorites.Project) async {
        guard !busy else { return }; busy = true; defer { busy = false }
        do {
            let result: Item<Session> = try await api.request("/api/session", method: "POST", body: ["location": ["directory": project.directory]])
            dismiss(); created(result.data)
        } catch { self.error = "Criação não confirmada: \(ConnectionAdvice.describe(error)). Confira lista antes de tentar novamente." }
    }
}
