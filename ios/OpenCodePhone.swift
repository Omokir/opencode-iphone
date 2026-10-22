import SwiftUI

enum Style {
    static let ink = Color(red: 0.11, green: 0.17, blue: 0.25)
    static let blue = Color(red: 0.13, green: 0.32, blue: 0.76)
    static let paper = Color(uiColor: .systemGroupedBackground)
}

@main
struct OpenCodePhoneApp: App {
    @StateObject private var api = API()
    var body: some Scene {
        WindowGroup {
            Group {
                if api.connected { SessionsView() } else { ConnectView() }
            }
            .environmentObject(api)
            .tint(Style.blue)
        }
    }
}

struct ConnectView: View {
    @EnvironmentObject var api: API
    @State private var address = ""
    @State private var code = ""
    @State private var busy = false
    @State private var error: String?
    var body: some View {
        NavigationStack {
            Form {
                Section {
                    VStack(alignment: .leading, spacing: 12) {
                        Text("[oc]").font(.system(size: 52, weight: .bold, design: .monospaced)).foregroundStyle(Style.blue)
                        Text("Seu notebook.\nNo seu bolso.").font(.system(.largeTitle, design: .rounded, weight: .bold))
                        Text("As conversas e ferramentas continuam no notebook. Este app é seu controle remoto.")
                            .foregroundStyle(.secondary)
                    }.padding(.vertical, 20)
                }.listRowBackground(Color.clear)
                Section("Conectar ao notebook") {
                    TextField("https://notebook.…ts.net:8443", text: $address)
                        .keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
                        .accessibilityLabel("Endereço do notebook")
                    TextField("Código de 6 dígitos", text: $code)
                        .keyboardType(.numberPad).onChange(of: code) { _, value in code = String(value.filter(\.isNumber).prefix(6)) }
                    Button {
                        busy = true
                        Task {
                            defer { busy = false }
                            do { try await api.pair(server: address, code: code) }
                            catch { self.error = error.localizedDescription }
                        }
                    } label: {
                        HStack { Text("Conectar"); Spacer(); if busy { ProgressView() } else { Image(systemName: "arrow.right") } }
                    }.disabled(busy || code.count != 6 || address.isEmpty)
                }
                Section {
                    Label("Ative Tailscale no iPhone.", systemImage: "network")
                    Label("No notebook, abra “Conectar iPhone” para gerar código de uso único.", systemImage: "laptopcomputer")
                } header: { Text("Antes de começar") }
                if let error { Section { Text(error).foregroundStyle(.red).textSelection(.enabled) } }
            }
            .navigationTitle("OpenCode Pocket").navigationBarTitleDisplayMode(.inline)
            .onAppear { address = api.server }
        }
    }
}

struct SessionsView: View {
    @EnvironmentObject var api: API
    @State private var sessions: [Session] = []
    @State private var cursor: String?
    @State private var path: [Session] = []
    @State private var error: String?
    @State private var busy = false
    @State private var settings = false
    @State private var create = false
    @State private var directory = "/home/omoki"
    var body: some View {
        NavigationStack(path: $path) {
            List {
                Section {
                    HStack(spacing: 12) {
                        Image(systemName: "laptopcomputer").font(.title).foregroundStyle(Style.blue)
                        VStack(alignment: .leading) {
                            Text("OpenCode Pocket").font(.system(.title3, design: .rounded, weight: .bold))
                            Text("Conversas do notebook").font(.caption).foregroundStyle(.secondary)
                        }
                    }.padding(.vertical, 10)
                }
                if let error { Section { Text(error).foregroundStyle(.red) } }
                Section("Conversas") {
                    ForEach(sessions) { session in
                        NavigationLink(value: session) {
                            VStack(alignment: .leading, spacing: 5) {
                                Text(session.title ?? "Sem título").font(.headline).lineLimit(2)
                                Text(session.location.directory).font(.system(.caption, design: .monospaced)).foregroundStyle(.secondary).lineLimit(1)
                            }.padding(.vertical, 5)
                        }
                    }
                    if sessions.isEmpty && !busy { Text("Crie conversa ou puxe para atualizar.").foregroundStyle(.secondary) }
                    if cursor != nil { Button("Carregar mais") { Task { await load(more: true) } }.disabled(busy) }
                }
            }
            .navigationTitle("Conversas")
            .navigationDestination(for: Session.self) { ChatView(session: $0) }
            .toolbar {
                ToolbarItem(placement: .topBarLeading) { Button("Ajustes", systemImage: "slider.horizontal.3") { settings = true } }
                ToolbarItem(placement: .topBarTrailing) { Button("Nova conversa", systemImage: "square.and.pencil") { create = true } }
            }
            .overlay { if busy && sessions.isEmpty { ProgressView() } }
            .refreshable { await load() }
            .task { await load() }
            .sheet(isPresented: $settings) { SettingsView() }
            .alert("Nova conversa", isPresented: $create) {
                TextField("Pasta no notebook", text: $directory).textInputAutocapitalization(.never).autocorrectionDisabled()
                Button("Criar") { Task { await newSession() } }
                Button("Cancelar", role: .cancel) { }
            } message: { Text("Use caminho absoluto da pasta onde OpenCode vai trabalhar.") }
        }
    }
    func load(more: Bool = false) async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            var url = "/api/session?limit=30&archived=false&parentID=null"
            if more, let cursor { url += "&cursor=" + API.escape(cursor) } else { url += "&order=desc" }
            let page: Page<Session> = try await api.request(url)
            if more { sessions += page.data.filter { s in !sessions.contains(where: { $0.id == s.id }) } }
            else { sessions = page.data }
            cursor = page.cursor?.next
            error = nil
        } catch { self.error = "Não foi possível acessar notebook: \(error.localizedDescription)" }
    }
    func newSession() async {
        guard directory.hasPrefix("/") else { error = "Use pasta com caminho absoluto, começando por /."; return }
        do {
            let response: Item<Session> = try await api.request("/api/session", method: "POST", body: ["location": ["directory": directory]])
            sessions.insert(response.data, at: 0)
            path.append(response.data)
        } catch { self.error = error.localizedDescription }
    }
}

struct ChatView: View {
    @EnvironmentObject var api: API
    @Environment(\.scenePhase) var phase
    let session: Session
    @StateObject private var store = ChatStore()
    @State private var draft = ""
    @State private var stop = false
    var body: some View {
        VStack(spacing: 0) {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 20) {
                        if store.olderCursor != nil {
                            Button("Mensagens anteriores") {
                                Task {
                                    store.loadingOlder = true
                                    await store.refresh(api, session: session, olderPage: true)
                                    store.loadingOlder = false
                                }
                            }.disabled(store.loadingOlder)
                        }
                        ForEach(store.messages) { message in MessageView(message: message).id(message.id) }
                        if store.messages.isEmpty && store.refreshed {
                            ContentUnavailableView("Converse com notebook", systemImage: "text.bubble", description: Text("Envie tarefa para começar."))
                        }
                        Color.clear.frame(height: 1).id("bottom")
                    }.padding()
                }
                .defaultScrollAnchor(.bottom)
                .onChange(of: store.messages.count) { old, new in
                    if old == 0 || (new > old && !store.loadingOlder) { proxy.scrollTo("bottom", anchor: .bottom) }
                }
            }
            if let error = store.error {
                Text(error).font(.caption).foregroundStyle(.red).padding(10).frame(maxWidth: .infinity).background(.red.opacity(0.06))
            }
            ForEach(store.permissions) { permission in
                VStack(alignment: .leading, spacing: 10) {
                    Label("Permissão solicitada", systemImage: "hand.raised.fill").font(.headline)
                    Text(permission.message ?? permission.action).textSelection(.enabled)
                    Text(permission.resources.joined(separator: "\n")).font(.system(.caption, design: .monospaced)).lineLimit(6)
                    HStack {
                        Button("Negar", role: .destructive) { Task { await store.reply(api, session: session, permission: permission, decision: "reject") } }
                        Spacer()
                        Button("Permitir uma vez") { Task { await store.reply(api, session: session, permission: permission, decision: "once") } }.buttonStyle(.borderedProminent)
                    }
                }.padding().background(Color.orange.opacity(0.12))
            }
            HStack(alignment: .bottom, spacing: 12) {
                TextField("Peça algo ao OpenCode…", text: $draft, axis: .vertical)
                    .lineLimit(1...6).padding(12).background(Style.paper, in: RoundedRectangle(cornerRadius: 16))
                Button {
                    let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
                    Task { if await store.send(api, session: session, text: text), draft.trimmingCharacters(in: .whitespacesAndNewlines) == text { draft = "" } }
                } label: {
                    Image(systemName: store.sending ? "ellipsis" : "arrow.up.circle.fill").font(.system(size: 36))
                }.disabled(store.sending || draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    .accessibilityLabel("Enviar mensagem")
            }.padding().background(.bar)
        }
        .navigationTitle(session.title ?? "Conversa").navigationBarTitleDisplayMode(.inline)
        .toolbar { Button("Interromper", systemImage: "stop.circle") { stop = true } }
        .confirmationDialog("Interromper tarefa no notebook?", isPresented: $stop) {
            Button("Interromper", role: .destructive) { Task { await store.interrupt(api, session: session) } }
        }
        .task(id: phase) {
            guard phase == .active else { return }
            while !Task.isCancelled {
                await store.refresh(api, session: session)
                do { try await Task.sleep(for: .seconds(store.error == nil ? 2 : 5)) } catch { break }
            }
        }
    }
}

struct MessageView: View {
    let message: Message
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(message.type == "user" ? "VOCÊ" : "OPENCODE").font(.system(.caption2, design: .monospaced, weight: .bold)).foregroundStyle(Style.blue)
                Spacer()
                if message.type == "assistant" && message.time.completed == nil { ProgressView().controlSize(.mini).accessibilityLabel("Em execução") }
            }
            if let text = message.text { Text(text).textSelection(.enabled) }
            ForEach(Array((message.content ?? []).enumerated()), id: \.offset) { _, part in
                if part.type == "text", let text = part.text {
                    Text(.init(text)).textSelection(.enabled)
                } else if part.type == "tool" {
                    HStack(alignment: .top) {
                        Image(systemName: part.state?.status == "error" ? "exclamationmark.circle" : "terminal")
                        Text(part.name ?? "Ferramenta").font(.system(.caption, design: .monospaced))
                        Spacer()
                        Text(status(part.state?.status)).font(.caption2)
                    }.foregroundStyle(.secondary).padding(10).background(Style.paper, in: RoundedRectangle(cornerRadius: 8))
                }
            }
        }
        .padding(16).frame(maxWidth: .infinity, alignment: .leading)
        .background(message.type == "user" ? Style.blue.opacity(0.07) : Color(uiColor: .secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 16))
    }
    func status(_ value: String?) -> String {
        switch value { case "completed": return "Concluída"; case "error": return "Erro"; default: return "Executando" }
    }
}

struct SettingsView: View {
    @EnvironmentObject var api: API
    @Environment(\.dismiss) var dismiss
    @State private var awake = false
    @State private var loaded = false
    @State private var busy = false
    @State private var error: String?
    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text(api.server).font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                    Toggle("Manter notebook acordado", isOn: Binding(get: { awake }, set: { value in Task { await setAwake(value) } })).disabled(!loaded || busy)
                } header: { Text("Notebook") } footer: {
                    Text("Ligado: evita suspensão com tampa fechada. Mantenha notebook ventilado e na tomada. Desligado: restaura energia; conexão pode cair se notebook suspender.")
                }
                Section {
                    Text("Tarefas continuam no notebook ao sair do app. Atualizações aparecem quando você volta. Sem notificações push nesta versão.")
                    Text("Código de conexão é de uso único. Acesso fica no Chaves deste iPhone. Nunca informe senha Apple aqui.")
                }
                if let error { Section { Text(error).foregroundStyle(.red) } }
                Button("Desconectar este iPhone", role: .destructive) { api.disconnect(); dismiss() }
            }
            .navigationTitle("Conexão")
            .toolbar { Button("Concluir") { dismiss() } }
            .task {
                do { let status: Awake = try await api.request("/phone/status"); awake = status.awake; loaded = true }
                catch { self.error = error.localizedDescription }
            }
        }
    }
    func setAwake(_ value: Bool) async {
        busy = true
        defer { busy = false }
        do {
            let status: Awake = try await api.request("/phone/mode", method: "POST", body: ["awake": value])
            awake = status.awake
            error = nil
        } catch { self.error = error.localizedDescription }
    }
}
