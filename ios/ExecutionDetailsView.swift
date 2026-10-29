import SwiftUI

@MainActor struct ExecutionDetailsView: View {
    struct Diff: Decodable, Identifiable {
        let file: String
        let patch: String
        let additions: Int
        let deletions: Int
        let more: Bool?
        var id: String { file }
    }
    struct TerminalResponse: Decodable {
        let data: Terminal?
        struct Terminal: Decodable {
            let title: String
            let screen: Screen
            struct Screen: Decodable { let text: String }
        }
    }
    @EnvironmentObject var api: API
    @Environment(\.dismiss) private var dismiss
    let session: Session
    @State private var diffs: [Diff] = []
    @State private var terminal: TerminalResponse.Terminal?
    @State private var errors: [String] = []
    @State private var loading = false
    var body: some View {
        NavigationStack {
            List {
                ForEach(errors, id: \.self) { Text($0).font(.caption).foregroundStyle(.secondary) }
                Section("Alterações do último turno") {
                    ForEach(diffs) { diff in
                        DisclosureGroup {
                            ScrollView(.horizontal) {
                                Text(String(diff.patch.prefix(100_000))).font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                            }
                            if diff.more == true || diff.patch.count > 100_000 { Text("Exibição parcial. Confira arquivo completo no notebook.").font(.caption) }
                        } label: {
                            VStack(alignment: .leading) {
                                Text(diff.file).font(.subheadline)
                                Text("+\(diff.additions)  −\(diff.deletions)").font(.caption.monospaced()).foregroundStyle(.secondary)
                            }
                        }
                    }
                    if diffs.isEmpty && !loading { Text("Nenhuma alteração carregada.").foregroundStyle(.secondary) }
                }
                Section("Terminal · somente leitura") {
                    if let terminal {
                        Text(terminal.title).font(.headline)
                        ScrollView(.horizontal) {
                            Text(String(terminal.screen.text.prefix(100_000))).font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                        }
                    } else { Text("Nenhum terminal carregado.").foregroundStyle(.secondary) }
                    Text("Últimas 100 linhas do terminal selecionado pelo OpenCode. Atualize para consultar novamente; não envia teclas ou comandos.").font(.caption).foregroundStyle(.secondary)
                }
            }.navigationTitle("Execução").navigationBarTitleDisplayMode(.inline)
                .toolbar { Button("Fechar") { dismiss() }; Button("Atualizar") { Task { await load() } }.disabled(loading) }
                .overlay { if loading { ProgressView() } }
                .task { await load() }
        }
    }
    private func load() async {
        guard !loading else { return }
        loading = true; defer { loading = false }
        let connection = api.connectionID
        let d: CoreList<Diff>? = try? await api.request("/api/session/\(session.id)/diff?context=3")
        let t: TerminalResponse? = try? await api.request("/api/experimental/session/\(session.id)/terminal/read?lines=100")
        guard !Task.isCancelled, api.connectionID == connection else { return }
        diffs = d?.data ?? []; terminal = t?.data
        errors = []
        if d == nil { errors.append("Diff indisponível nesta consulta.") }
        if t == nil { errors.append("Terminal indisponível nesta versão ou conexão.") }
    }
}
