import SwiftUI

@MainActor
struct MCPRegistryView: View {
    @EnvironmentObject var api: API
    @EnvironmentObject var privacy: PrivacyLock
    let directory: String
    @State private var registry: MCPRegistry?
    @State private var pending: MCPRegistryMutation?
    @State private var busy = false
    @State private var uncertain = false
    @State private var reviewed = false
    @State private var notice: String?
    @State private var name = ""
    @State private var configuration = "{\"type\":\"remote\",\"url\":\"https://example.com/mcp\"}"
    @State private var viewTicket = UUID()
    @State private var loadedConnection: UUID?
    @State private var reviewConnection: UUID?
    @State private var reviewRevision: Int?
    @State private var reviewServer: String?
    private let fence = MCPRegistryFence()

    private var locked: Bool { busy || uncertain || fence.pending(api.server) || registry == nil || loadedConnection != api.connectionID || !privacy.allowsAccess }
    var body: some View {
        List {
            Section("Segurança") {
                Text("Cadastro global, acesso por projeto. Habilitar MCP local executa seu comando no computador. Confira origem e argumentos.")
                Text("Não coloque segredos no comando. Ambiente aceita somente referências {env:NOME}. Autenticação OAuth deve ser concluída no computador.").font(.caption)
                Text("Salvar registro não confirma ativação. Consulte Conexões depois; adaptador KzL precisa estar instalado no OpenCode. Revogar não cancela operações já admitidas.").font(.caption)
                Text(directory).font(.caption).textSelection(.enabled)
            }
            if let registry {
                Section("Cadastros · revisão \(registry.revision)") {
                    ForEach(registry.servers.keys.sorted(), id: \.self) { name in
                        if let server = registry.servers[name] {
                            VStack(alignment: .leading, spacing: 8) {
                                Text(name).font(.headline)
                                Text(server.config.reviewText).font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                                let granted = server.projects.contains(directory)
                                Text(granted ? "Acesso declarado neste projeto" : "Sem acesso neste projeto").font(.caption)
                                Button(granted ? "Revogar neste projeto" : "Habilitar neste projeto") {
                                    prepare(granted ? "revoke" : "grant", name: name, config: server.config)
                                }.disabled(locked)
                                Button("Remover cadastro global", role: .destructive) { prepare("remove", name: name, config: server.config) }.disabled(locked)
                            }
                        }
                    }
                    if registry.servers.isEmpty { Text("Nenhum cadastro MCP.") }
                }
            }
            Section("Novo MCP") {
                TextField("Nome do servidor", text: $name).textInputAutocapitalization(.never).autocorrectionDisabled()
                TextEditor(text: $configuration).font(.system(.caption, design: .monospaced)).frame(minHeight: 120)
                    .accessibilityLabel("Configuração MCP em JSON, sem segredos")
                Text("Local: {\"type\":\"local\",\"command\":[\"programa\",\"argumento\"]}").font(.caption)
                Button("Revisar cadastro sem ativar") { add() }.disabled(locked)
            }
            Section {
                if let notice { Text(notice).foregroundStyle(.secondary) }
                if uncertain {
                    Text("Há alteração não confirmada neste computador. Nenhuma escrita será repetida automaticamente.").foregroundStyle(.red)
                    Button("Revisar estado consultado e liberar novas alterações") {
                        reviewConnection = api.connectionID; reviewServer = api.server
                        reviewRevision = registry?.revision; reviewed = true
                    }.disabled(busy || registry == nil || loadedConnection != api.connectionID)
                }
                Button(busy ? "Consultando…" : "Consultar registro atual") { Task { await load() } }.disabled(busy)
            }
        }
        .navigationTitle("Gerenciar MCPs")
        .task(id: api.connectionID) { await load() }
        .onDisappear { viewTicket = UUID(); pending = nil }
        .alert(pending?.title ?? "Revisar alteração", isPresented: Binding(get: { pending != nil }, set: { if !$0 { pending = nil } }), presenting: pending) { mutation in
            Button("Confirmar", role: mutation.operation == "remove" ? .destructive : nil) {
                pending = nil; Task { await write(mutation) }
            }
            Button("Cancelar", role: .cancel) { pending = nil }
        } message: { mutation in Text(mutation.detail) }
        .confirmationDialog("Estado atual revisado?", isPresented: $reviewed, titleVisibility: .visible) {
            Button("Confirmar revisão") {
                guard !busy, registry != nil, loadedConnection == api.connectionID,
                      reviewConnection == api.connectionID, reviewServer == api.server,
                      reviewRevision == registry?.revision, privacy.allowsAccess else { return }
                fence.clearAfterAcknowledgement(api.server); uncertain = fence.pending(api.server)
                notice = uncertain ? "Não foi possível limpar trava local; escritas permanecem bloqueadas." : "Revisão reconhecida. Nenhuma alteração anterior foi reenviada."
            }
            Button("Cancelar", role: .cancel) {}
        } message: { Text("Confira cadastro, acesso e revisão exibidos. Esta confirmação só libera novas alterações; não repete nem desfaz a anterior e não confirma estado em execução.") }
    }

    private func prepare(_ operation: String, name: String, config: MCPRegistry.Configuration?) {
        guard !locked, let registry else { return }
        pending = MCPRegistryMutation(revision: registry.revision, operation: operation, name: name,
            directory: directory, connectionID: api.connectionID, server: api.server, config: config)
    }

    private func add() {
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.range(of: "^[a-z][a-z0-9_-]{0,47}$", options: .regularExpression) != nil else {
            notice = "Nome inválido: use letras minúsculas, números, _ ou -."; return
        }
        do { prepare("add", name: trimmed, config: try MCPRegistry.Configuration.parse(configuration)) }
        catch { notice = "Configuração inválida. Use HTTPS sem credenciais na URL ou comando em array; ambiente só aceita referências {env:NOME}." }
    }

    private func load() async {
        let connection = api.connectionID; let ticket = UUID(); viewTicket = ticket
        pending = nil; reviewed = false; registry = nil; loadedConnection = nil
        uncertain = fence.pending(api.server); busy = true
        defer { if connection == api.connectionID && ticket == viewTicket { busy = false } }
        do {
            let result: MCPRegistryResponse = try await api.request("/phone/connections/registry")
            guard !Task.isCancelled, connection == api.connectionID, ticket == viewTicket else { return }
            guard result.registry.version == 1, result.registry.revision >= 0 else { throw MCPRegistryError.invalidConfiguration }
            registry = result.registry
            loadedConnection = connection
            notice = "Registro consultado. Ativação e permissões de ferramentas devem ser verificadas separadamente."
        } catch {
            guard !Task.isCancelled, connection == api.connectionID, ticket == viewTicket else { return }
            notice = "Registro indisponível. Verifique conexão e gateway. Escritas bloqueadas."
        }
    }

    private func write(_ mutation: MCPRegistryMutation) async {
        guard !locked, api.connectionID == mutation.connectionID, api.server == mutation.server,
              registry?.revision == mutation.revision else { return }
        busy = true
        let ticket = viewTicket
        // Recheck binding after local authentication; the user may switch computers.
        guard await privacy.confirm("Alterar cadastro ou acesso MCP") else { busy = false; return }
        guard api.connectionID == mutation.connectionID, api.server == mutation.server, ticket == viewTicket,
              privacy.allowsAccess else { busy = false; return }
        guard fence.begin(mutation.server) else {
            busy = false; uncertain = true; registry = nil
            notice = "Trava de alteração pendente. Consulte e revise registro antes de continuar."; return
        }
        uncertain = true; registry = nil
        defer { if api.connectionID == mutation.connectionID && ticket == viewTicket { busy = false } }
        do {
            let result: MCPRegistryResponse = try await api.request("/phone/connections/registry", method: "POST", body: mutation.body)
            guard !Task.isCancelled, api.connectionID == mutation.connectionID, ticket == viewTicket else { return }
            guard result.registry.version == 1, result.registry.revision == mutation.revision + 1 else { throw MCPRegistryError.invalidConfiguration }
            fence.clearAfterAcknowledgement(mutation.server); uncertain = fence.pending(mutation.server)
            registry = result.registry
            loadedConnection = mutation.connectionID
            notice = "Registro salvo. Isso não comprova conexão ou revogação em execução; consulte Conexões."
        } catch {
            guard api.connectionID == mutation.connectionID, ticket == viewTicket else { return }
            notice = "Alteração não confirmada. Nada será reenviado. Consulte registro e revise estado antes de outra escrita."
        }
    }
}
