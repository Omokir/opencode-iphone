import SwiftUI

struct ConnectionInventory: Decodable {
    let directory: String
    let readOnly: Bool
    let mcp: [Server]
    let integrations: [Integration]
    let unavailable: [String]
    struct Server: Decodable {
        let name: String
        let status: String
        var statusLabel: String {
            switch status {
            case "connected": return "Conectado"
            case "pending": return "Conectando"
            case "disabled": return "Desativado"
            case "failed": return "Falhou"
            case "needs_auth": return "Precisa autenticar"
            default: return "Não confirmado"
            }
        }
    }
    struct Integration: Decodable {
        let id: String
        let name: String
        let methods: [String]
        let connectionCount: Int
    }
}

struct ConnectionsView: View {
    @EnvironmentObject var api: API
    let directory: String
    @State private var inventory: ConnectionInventory?
    @State private var error: String?
    @State private var busy = false

    var body: some View {
        List {
            Section("Projeto") {
                Text(directory).font(.caption).textSelection(.enabled)
                Text("Consulta somente leitura. Não instala MCPs, autentica contas nem concede permissões.").font(.caption)
                NavigationLink("Gerenciar cadastros e acesso MCP") { MCPRegistryView(directory: directory) }
            }
            if let inventory {
                Section("Servidores MCP") {
                    ForEach(Array(inventory.mcp.enumerated()), id: \.offset) { _, server in
                        LabeledContent(server.name, value: server.statusLabel)
                    }
                    if inventory.unavailable.contains("mcp") { Text("Consulta indisponível.") }
                    else if inventory.mcp.isEmpty { Text("Nenhum servidor neste projeto.") }
                }
                Section("Contas e integrações") {
                    ForEach(Array(inventory.integrations.enumerated()), id: \.offset) { _, integration in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(integration.name)
                            Text("Métodos: \(integration.methods.joined(separator: ", "))").font(.caption)
                            Text("Conexões registradas: \(integration.connectionCount)").font(.caption)
                        }
                    }
                    if inventory.unavailable.contains("integration") { Text("Consulta indisponível.") }
                    else if inventory.integrations.isEmpty { Text("Nenhuma integração neste projeto.") }
                }
            }
            Section {
                Text("API OpenAI é cobrada por uso, separadamente da assinatura ChatGPT. Métodos disponíveis não comprovam saldo, assinatura ou acesso a um modelo.").font(.caption)
                Text("Conectado não significa autorização para executar ações.").font(.caption)
                if let error { Text(error).foregroundStyle(.red) }
                Button(busy ? "Consultando…" : "Atualizar conexões") { Task { await load() } }.disabled(busy)
            }
        }
        .navigationTitle("Conexões")
        .task(id: api.connectionID) { await load() }
    }

    @MainActor
    private func load() async {
        // Bind responses to both the selected computer and this project.
        let connection = api.connectionID
        inventory = nil; error = nil; busy = true
        defer { if connection == api.connectionID { busy = false } }
        do {
            var query = URLComponents()
            query.queryItems = [URLQueryItem(name: "directory", value: directory)]
            let result: ConnectionInventory = try await api.request("/phone/connections?" + (query.percentEncodedQuery ?? ""))
            guard !Task.isCancelled, connection == api.connectionID else { return }
            guard result.directory == directory, result.readOnly else {
                throw PhoneError.message("Resposta de outro projeto recusada.")
            }
            inventory = result
        } catch {
            guard !Task.isCancelled, connection == api.connectionID else { return }
            self.error = "Conexões indisponíveis. Verifique pareamento, gateway e versão instalada."
        }
    }
}
