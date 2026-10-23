import SwiftUI

struct ChatSearchPage: Decodable {
    let matches: [Hit]
    let scanned: Int
    let cursor: String?
    struct Hit: Decodable, Identifiable {
        let id: String
        let type: String
        let snippet: String
        let created: Double
    }
}

struct FullChatSearchView: View {
    @EnvironmentObject var api: API
    @Environment(\.dismiss) var dismiss
    let sessionID: String
    @State private var query = ""
    @State private var hits: [ChatSearchPage.Hit] = []
    @State private var cursor: String?
    @State private var scanned = 0
    @State private var loading = false
    @State private var ticket = UUID()
    @State private var error: String?
    @State private var selected: ChatSearchPage.Hit?
    var body: some View {
        NavigationStack {
            List {
                Section {
                    Text("Pesquisa texto de mensagens do usuário e assistente no notebook, inclusive páginas não carregadas no chat. Anexos e saída de ferramentas não são indexados.").font(.caption)
                    if scanned > 0 { Text("\(scanned) mensagens consultadas · \(hits.count) resultados").font(.caption.monospacedDigit()) }
                    if loading { ProgressView("Consultando histórico…") }
                    if let error { Text(error).foregroundStyle(.red); Button("Tentar novamente") { Task { await scan() } }.disabled(loading) }
                    if cursor != nil && !loading { Button("Continuar busca no histórico mais antigo") { Task { await scan() } } }
                    if !query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !loading && scanned > 0 && cursor == nil {
                        Text(hits.isEmpty ? "Histórico percorrido: nenhum resultado." : "Fim do histórico consultado.").font(.caption).foregroundStyle(.secondary)
                    }
                }
                ForEach(hits) { hit in
                    Button { selected = hit } label: {
                        VStack(alignment: .leading, spacing: 6) {
                            Text(hit.type == "user" ? "Você" : "OpenCode").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                            Text(hit.snippet).foregroundStyle(.primary).lineLimit(7)
                            Text(Date(timeIntervalSince1970: hit.created > 100_000_000_000 ? hit.created / 1000 : hit.created), style: .date).font(.caption2).foregroundStyle(.secondary)
                        }
                    }
                }
            }.navigationTitle("Buscar no histórico")
                .searchable(text: $query, prompt: "Texto em toda a conversa")
                .toolbar { Button("Fechar") { dismiss() } }
                .task(id: query) {
                    ticket = UUID(); hits = []; cursor = nil; scanned = 0; error = nil; loading = false
                    guard !query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
                    do { try await Task.sleep(for: .milliseconds(400)) } catch { return }
                    await scan()
                }
                .sheet(item: $selected) { hit in SearchMessageDetail(sessionID: sessionID, messageID: hit.id) }
                .onDisappear { ticket = UUID(); loading = false }
        }
    }
    func scan() async {
        guard !loading else { return }
        let text = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        guard text.count <= 200 else { error = "Use até 200 caracteres."; return }
        let current = ticket
        loading = true; defer { if ticket == current { loading = false } }
        do {
            var visited = Set<String>()
            for _ in 0..<100 {
                try Task.checkCancellation()
                guard ticket == current else { return }
                let previous = cursor
                if let previous, !visited.insert(previous).inserted { throw PhoneError.message("Servidor repetiu cursor; busca interrompida sem assumir fim do histórico.") }
                var path = "/phone/session/\(sessionID)/search?q=" + API.escape(text)
                if let cursor { path += "&cursor=" + API.escape(cursor) }
                let page: ChatSearchPage = try await api.request(path)
                try Task.checkCancellation()
                guard ticket == current else { return }
                hits += page.matches.filter { item in !hits.contains { $0.id == item.id } }
                scanned += page.scanned; cursor = page.cursor; error = nil
                if cursor == nil { return }
            }
        } catch is CancellationError { }
        catch { if ticket == current { self.error = ConnectionAdvice.describe(error) } }
    }
}

struct SearchMessageDetail: View {
    @EnvironmentObject var api: API
    @Environment(\.dismiss) var dismiss
    let sessionID: String
    let messageID: String
    @State private var message: Message?
    @State private var error: String?
    var body: some View {
        NavigationStack {
            ScrollView {
                if let message { MessageView(message: message).padding() }
                else if let error { Text(error).foregroundStyle(.red).padding() }
                else { ProgressView().padding() }
            }.navigationTitle("Mensagem encontrada").navigationBarTitleDisplayMode(.inline)
                .toolbar { Button("Fechar") { dismiss() } }
                .task {
                    do { let result: Item<Message> = try await api.request("/api/session/\(sessionID)/message/\(messageID)"); message = result.data }
                    catch { self.error = ConnectionAdvice.describe(error) }
                }
        }
    }
}
