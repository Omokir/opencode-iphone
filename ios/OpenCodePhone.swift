import SwiftUI
import PhotosUI
import UniformTypeIdentifiers

enum Style {
    static let ink = Color(red: 0.11, green: 0.17, blue: 0.25)
    static let blue = Color(red: 0.13, green: 0.32, blue: 0.76)
    static let paper = Color(uiColor: .systemGroupedBackground)
}

@main
struct OpenCodePhoneApp: App {
    @UIApplicationDelegateAdaptor(PocketAppDelegate.self) private var appDelegate
    @Environment(\.scenePhase) private var phase
    @StateObject private var inbox = InboxSync()
    @StateObject private var api = API()
    @StateObject private var privacy = PrivacyLock()
    @StateObject private var projects = ProjectFavorites()
    @StateObject private var receiver = DocumentReceiver.shared
    #if SNAPSHOT
    @StateObject private var unread = UnreadStore(defaults: UserDefaults(suiteName: "snapshot-" + UUID().uuidString)!)
    @StateObject private var pins = PinStore(defaults: UserDefaults(suiteName: "pins-snapshot-" + UUID().uuidString)!)
    #else
    @StateObject private var unread = UnreadStore()
    @StateObject private var pins = PinStore()
    #endif
    var body: some Scene {
        WindowGroup {
            ZStack {
              if privacy.allowsAccess {
                #if SNAPSHOT
                SnapshotRoot()
                #else
                if api.connected { SessionsView() } else { ConnectView() }
                #endif
              } else { PocketLockView() }
            }
            .environmentObject(api)
            .environmentObject(unread)
            .environmentObject(pins)
            .environmentObject(inbox)
            .environmentObject(privacy)
            .environmentObject(projects)
            .onOpenURL { url in receiver.offer(url) }
            .sheet(item: Binding(get: { privacy.allowsAccess ? receiver.incoming : nil }, set: { if $0 == nil && privacy.allowsAccess { receiver.close() } })) { item in DocumentImportView(item: item) }
            .onChange(of: phase) { _, value in if value == .background { privacy.lock() } }
            .task(id: "\(phase)-\(privacy.allowsAccess)-\(api.connected)") {
                guard phase == .active else { return }
                await privacy.unlock()
                guard privacy.allowsAccess else { return }
                while !Task.isCancelled {
                    if privacy.allowsAccess { await inbox.sync(api) }
                    do { try await Task.sleep(for: .seconds(8)) } catch { break }
                }
            }
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
                        Text("Seu notebook.\nNo seu bolso.").font(.system(.largeTitle, design: .rounded, weight: .bold)).fixedSize(horizontal: false, vertical: true)
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
    @EnvironmentObject var unread: UnreadStore
    @EnvironmentObject var pins: PinStore
    @Environment(\.scenePhase) var phase
    @State private var sessions: [Session] = []
    @State private var cursor: String?
    @State private var path: [Session] = []
    @State private var error: String?
    @State private var busy = false
    @State private var settings = false
    @State private var create = false
    @State private var phoneControl = false
    @State private var fileBrowser = false
    @State private var inboxSettings = false
    @State private var projectPicker = false
    @State private var hostStatus: HostStatus?
    @State private var hostChecked: Date?
    @State private var hostStatusFailed = false
    @State private var codexQuota: CodexQuota?
    @State private var quotaFailed = false
    @State private var quotaLoading = false
    @State private var quotaChecked = Date.distantPast
    @State private var directory = ""
    @State private var pinsChecked = Date.distantPast
    @State private var pinLoadFailed = false
    @State private var loadedMore = false
    @State private var searchText = ""
    @State private var searchPresented = false
    @State private var searchResults: [Session] = []
    @State private var searchCursor: String?
    @State private var searchBusy = false
    @State private var searchError: String?
    @State private var searchTicket = UUID()
    @State private var dashboardExpanded = false
    @State private var listFilter = "Todas"
    @State private var cachedList = false
    var searching: Bool { !searchText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
    var displayedSessions: [Session] {
        (searching ? searchResults : sessions).filter { session in
            switch listFilter {
            case "Não lidas": return unread.isUnread(session, server: api.server)
            case "Em execução": return session.outcome == nil && session.time?.idle == nil
            default: return true
            }
        }
    }
    var displayedPins: [String] { searching || listFilter != "Todas" ? pinnedIDs.filter { id in displayedSessions.contains { $0.id == id } } : pinnedIDs }
    var pinnedIDs: [String] { pins.ids(server: api.server) }
    var otherSessions: [Session] { displayedSessions.filter { !pins.contains($0.id, server: api.server) } }
    var body: some View {
        NavigationStack(path: $path) {
            List {
                if let error { Section { Text(error).foregroundStyle(.red) } }
                Section {
                    DisclosureGroup(isExpanded: $dashboardExpanded) {
                        HostBatteryView(status: hostStatus, stale: hostStatusFailed || api.reachable == false)
                        StorageDashboard(host: hostStatus?.storage, stale: hostStatusFailed || api.reachable == false)
                        CodexQuotaView(quota: codexQuota, failed: quotaFailed, loading: quotaLoading) { Task { await loadQuota(refresh: true) } }
                    } label: {
                        Label(api.reachable == false ? "Notebook indisponível" : "Notebook · indicadores", systemImage: "laptopcomputer")
                            .font(.subheadline.weight(.semibold))
                    }
                    if cachedList { Label("Histórico salvo · atualizando…", systemImage: "internaldrive").font(.caption).foregroundStyle(.secondary) }
                    Picker("Filtrar conversas", selection: $listFilter) {
                        Text("Todas").tag("Todas")
                        Text("Não lidas").tag("Não lidas")
                        Text("Em execução").tag("Em execução")
                    }.pickerStyle(.segmented)
                }
                if !displayedPins.isEmpty {
                    Section("Fixadas") {
                        ForEach(displayedPins, id: \.self) { id in
                            if let session = displayedSessions.first(where: { $0.id == id }) {
                                row(session, pinned: true)
                            } else if !busy {
                                HStack {
                                    Label("Conversa fixada indisponível", systemImage: "pin.fill").font(.caption).foregroundStyle(.secondary)
                                    Spacer()
                                    Button("Desafixar") { pins.toggle(id, server: api.server) }.font(.caption)
                                }
                            }
                        }
                        if pinLoadFailed { Text("Algumas fixadas não carregaram. Puxe para atualizar.").font(.caption).foregroundStyle(.secondary) }
                    }
                }
                Section(pinnedIDs.isEmpty ? "Conversas" : "Outras conversas") {
                    ForEach(otherSessions) { session in
                        row(session, pinned: false)
                    }
                    if searching {
                        if searchBusy { ProgressView("Buscando conversas…") }
                        if let searchError { Text(searchError).foregroundStyle(.red) }
                        if searchResults.isEmpty && !searchBusy && searchError == nil { Text("Nenhuma conversa encontrada.").foregroundStyle(.secondary) }
                        if searchCursor != nil { Button("Mais resultados") { Task { await search(more: true) } }.disabled(searchBusy) }
                    } else {
                        if sessions.isEmpty && !busy { Text("Crie conversa ou puxe para atualizar.").foregroundStyle(.secondary) }
                        if cursor != nil { Button("Carregar mais") { Task { await load(more: true) } }.disabled(busy) }
                    }
                }
            }
            .navigationTitle("Conversas")
            .searchable(text: $searchText, isPresented: $searchPresented, placement: .navigationBarDrawer, prompt: "Nome da conversa")
            .task(id: searchText) {
                searchTicket = UUID()
                searchBusy = false
                searchResults = []
                searchCursor = nil
                searchError = nil
                guard searching else { return }
                searchBusy = true
                do { try await Task.sleep(for: .milliseconds(350)) } catch { return }
                await search()
            }
            .navigationDestination(for: Session.self) { ChatView(session: $0) }
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    HStack(spacing: 16) {
                        Button("Ajustes", systemImage: "slider.horizontal.3") { settings = true }
                        Button("Arquivos do notebook", systemImage: "folder") { fileBrowser = true }
                        Button("Procurar conversas", systemImage: "magnifyingglass") { searchPresented = true }
                        Menu {
                            Button("Projetos favoritos", systemImage: "star") { projectPicker = true }
                            Button("Pasta automática do iPhone", systemImage: "arrow.up.doc") { inboxSettings = true }
                            Button("Controlar meu iPhone (USB)", systemImage: "cable.connector") { phoneControl = true }
                        } label: { Image(systemName: "ellipsis.circle") }.accessibilityLabel("Recursos do Pocket")
                    }
                }
                ToolbarItem(placement: .topBarTrailing) { Button("Nova conversa", systemImage: "square.and.pencil") { create = true } }
            }
            .overlay { if busy && sessions.isEmpty { ProgressView() } }
            .refreshable { await load(resetPagination: true) }
            .onAppear {
                if sessions.isEmpty, let page: Page<Session> = api.cached("/api/session?limit=30&archived=false&parentID=null&order=desc") {
                    sessions = page.data; cursor = page.cursor?.next; cachedList = true
                }
            }
            .task(id: phase) {
                guard phase == .active else { return }
                while !Task.isCancelled {
                    if path.isEmpty && !settings && !phoneControl && !fileBrowser {
                        await load()
                        if Date().timeIntervalSince(quotaChecked) > 60 { await loadQuota() }
                    }
                    do { try await Task.sleep(for: .seconds(5)) } catch { break }
                }
            }
            .onChange(of: path.count) { _, count in if count == 0 { Task { await load() } } }
            .sheet(isPresented: $settings) { SettingsView() }
            .sheet(isPresented: $projectPicker) { ProjectsView { session in sessions.insert(session, at: 0); path.append(session) } }
            .sheet(isPresented: $phoneControl) { PhoneControlView() }
            .sheet(isPresented: $fileBrowser) { FileBrowserView() }
            .sheet(isPresented: $inboxSettings) { InboxSyncView() }
            .alert("Nova conversa", isPresented: $create) {
                TextField("Pasta no notebook", text: $directory).textInputAutocapitalization(.never).autocorrectionDisabled()
                Button("Criar") { Task { await newSession() } }
                Button("Cancelar", role: .cancel) { }
            } message: { Text("Use caminho absoluto da pasta onde OpenCode vai trabalhar.") }
        }
    }
    func row(_ session: Session, pinned: Bool) -> some View {
        ConversationRow(session: session, pinned: pinned, unread: unread.isUnread(session, server: api.server)) {
            pins.toggle(session.id, server: api.server)
        }
    }
    func search(more: Bool = false) async {
        let query = searchText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !query.isEmpty else { return }
        let ticket = UUID()
        searchTicket = ticket
        searchBusy = true
        defer { if searchTicket == ticket { searchBusy = false } }
        do {
            let page: Page<Session> = try await api.request(SessionSearch.path(query: query, cursor: more ? searchCursor : nil))
            try Task.checkCancellation()
            guard searchTicket == ticket, query == searchText.trimmingCharacters(in: .whitespacesAndNewlines) else { return }
            if more { searchResults += page.data.filter { item in !searchResults.contains { $0.id == item.id } } }
            else { searchResults = page.data }
            searchCursor = page.cursor?.next
            searchError = nil
        } catch {
            guard searchTicket == ticket, !Task.isCancelled else { return }
            searchError = "Busca indisponível: \(error.localizedDescription)"
        }
    }
    func load(more: Bool = false, resetPagination: Bool = false) async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            if resetPagination { loadedMore = false }
            var url = "/api/session?limit=30&archived=false&parentID=null"
            if more, let cursor { url += "&cursor=" + API.escape(cursor) } else { url += "&order=desc" }
            let page: Page<Session> = try await api.request(url)
            unread.initialize(server: api.server, sessions: page.data)
            PocketNotifications.shared.observe(page.data, server: api.server)
            if more {
                sessions += page.data.filter { s in !sessions.contains(where: { $0.id == s.id }) }
                loadedMore = true
            }
            else {
                let previous = sessions
                var loaded = page.data
                if loadedMore {
                    let older = previous.filter { old in !loaded.contains { $0.id == old.id } }
                    loaded += older
                }
                var failed = false
                var refreshedPins = false
                for id in pinnedIDs where !loaded.contains(where: { $0.id == id }) {
                    let cached = previous.first { $0.id == id }
                    let valid = id.hasPrefix("ses") && id.unicodeScalars.allSatisfy { CharacterSet(charactersIn: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-").contains($0) }
                    guard valid else { failed = true; continue }
                    if cached == nil || Date().timeIntervalSince(pinsChecked) > 30 {
                        refreshedPins = true
                        do {
                            let value: Item<Session> = try await api.request("/api/session/\(id)")
                            loaded.append(value.data)
                        } catch {
                            failed = true
                            if let cached { loaded.append(cached) }
                        }
                    } else if let cached { loaded.append(cached) }
                }
                sessions = loaded
                if refreshedPins { pinsChecked = Date() }
                pinLoadFailed = failed
            }
            if more || !loadedMore { cursor = page.cursor?.next }
            error = nil
            cachedList = false
            do {
                hostStatus = try await api.request("/phone/status")
                hostChecked = Date()
                hostStatusFailed = false
            } catch { hostStatusFailed = true }
        } catch { self.error = ConnectionAdvice.describe(error) }
    }
    func newSession() async {
        guard directory.hasPrefix("/") else { error = "Use pasta com caminho absoluto, começando por /."; return }
        do {
            let response: Item<Session> = try await api.request("/api/session", method: "POST", body: ["location": ["directory": directory]])
            sessions.insert(response.data, at: 0)
            path.append(response.data)
        } catch { self.error = error.localizedDescription }
    }
    func loadQuota(refresh: Bool = false) async {
        guard !quotaLoading else { return }
        quotaLoading = true
        defer { quotaLoading = false }
        do {
            codexQuota = try await api.request("/phone/codex/usage" + (refresh ? "?refresh=1" : ""))
            quotaChecked = Date()
            quotaFailed = false
        } catch let failure as URLError where failure.code == .cancelled { }
        catch { quotaFailed = true; quotaChecked = Date() }
    }
}

@MainActor struct ChatView: View {
    @EnvironmentObject var api: API
    @EnvironmentObject var unread: UnreadStore
    @EnvironmentObject var projects: ProjectFavorites
    @Environment(\.scenePhase) var phase
    @State private var session: Session
    @StateObject private var store = ChatStore()
    @State private var draft = ""
    @State private var stop = false
    @State private var options = false
    @State private var selectingFiles = false
    @State private var selectingPhotos = false
    @State private var photos: [PhotosPickerItem] = []
    @State private var attachments: [PendingFile] = []
    @State private var importing = false
    @State private var changingAgent = false
    @State private var controlPanel = false
    @State private var question: QuestionForm?
    @State private var controlAllowed = false
    @State private var controlSummary = "Consultando automação…"
    @State private var controlCheck = Date.distantPast
    @State private var stoppingControl = false
    @State private var modeError: String?
    @State private var fileBrowser = false
    @State private var preview: LocalPreview?
    @State private var following = true
    @State private var scrollInteracting = false
    @State private var bottomY: CGFloat = 0
    @State private var viewportHeight: CGFloat = 0
    @State private var draftLoaded = false
    @State private var draftRecoveryBlocked = false
    @State private var draftSavedAt: Date?
    @State private var draftError: String?
    @State private var draftSaveTask: Task<Void, Never>?
    @State private var chatQuery = ""
    @State private var showChatSearch = false
    @State private var showFullSearch = false
    @State private var visibleMessage: String?
    @State private var restoredPosition = false
    private let drafts = DraftStore()
    init(session: Session) {
        _session = State(initialValue: session)
        #if SNAPSHOT
        _attachments = State(initialValue: [PendingFile(name: "requisitos.txt", mime: "text/plain", data: Data("Projeto de exemplo".utf8))])
        #endif
    }
    var body: some View { lifecycleContent }
    private var chatContent: some View {
        VStack(spacing: 0) {
            controlHeader
            modeHeader
            connectionStrip
            Text(store.activity).font(.caption2.weight(.semibold)).foregroundStyle(.secondary).frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal)
            if showChatSearch {
                TextField("Buscar nas mensagens carregadas", text: $chatQuery).textFieldStyle(.roundedBorder).padding(.horizontal)
            }
            messageTimeline
            notices
            questionCards
            permissionCards
            attachmentStrip
            composer
        }
    }
    @ViewBuilder private var controlHeader: some View {
            if session.isPhoneControl {
                HStack {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(controlSummary).font(.caption.weight(.semibold))
                        Button("Abrir painel") { controlPanel = true }.font(.caption2)
                    }
                    Spacer()
                    Button("Parar", systemImage: "stop.circle.fill", role: .destructive) { Task { await stopControl() } }
                        .disabled(stoppingControl).accessibilityLabel("Parar automação do iPhone")
                }.padding(.horizontal).padding(.vertical, 8).background(Color.orange.opacity(0.08))
            }
    }
    private var modeHeader: some View {
            HStack(spacing: 10) {
                ForEach(["plan", "build"], id: \.self) { agent in
                    Button {
                        Task { await switchAgent(agent) }
                    } label: {
                        Label(agent.capitalized, systemImage: agent == "plan" ? "list.bullet.clipboard" : "hammer")
                            .font(.subheadline.weight(.semibold)).padding(.horizontal, 12).padding(.vertical, 8)
                            .background((session.agent ?? "build") == agent ? Style.blue.opacity(0.12) : Color.clear, in: Capsule())
                            .contentShape(Capsule())
                    }.disabled(changingAgent || store.sending)
                        .buttonStyle(.plain)
                        .accessibilityIdentifier("chat.mode." + agent)
                        .accessibilityValue((session.agent ?? "build") == agent ? "Selecionado" : "")
                        .accessibilityAddTraits((session.agent ?? "build") == agent ? .isSelected : [])
                }
                Spacer(minLength: 0)
                Button { options = true } label: {
                    Text(session.model?.id ?? "Modelo").font(.system(.caption, design: .monospaced)).lineLimit(1)
                }.accessibilityLabel("Selecionar modelo e ajustar conversa")
            }.padding(.horizontal).padding(.vertical, 6).background(.bar)
    }
    private var connectionStrip: some View {
            HStack {
                Label(store.showingCache ? "Histórico salvo" : store.liveConnected ? "Ao vivo" : "Consulta periódica", systemImage: store.showingCache ? "internaldrive" : store.liveConnected ? "dot.radiowaves.left.and.right" : "arrow.clockwise")
                    .foregroundStyle(store.liveConnected ? Color.green : .secondary)
                Spacer()
                if draftError != nil { Text("Rascunho não salvo").foregroundStyle(.red) }
                else if draftSavedAt != nil && (!draft.isEmpty || !attachments.isEmpty) { Text("Rascunho salvo").foregroundStyle(.secondary) }
                else if !draft.isEmpty || !attachments.isEmpty { Text("Salvando rascunho…").foregroundStyle(.secondary) }
            }.font(.caption2).padding(.horizontal).padding(.vertical, 3)
    }
    private var messageTimeline: some View {
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
                        ForEach(store.messages.filter { message in
                            chatQuery.isEmpty || ([message.text ?? ""] + (message.content ?? []).compactMap(\.text)).joined(separator: "\n").localizedCaseInsensitiveContains(chatQuery)
                        }) { message in MessageView(message: message).id(message.id) }
                        if store.messages.isEmpty && store.refreshed {
                            ContentUnavailableView("Converse com notebook", systemImage: "text.bubble", description: Text("Envie tarefa para começar."))
                        }
                        Color.clear.frame(height: 1).id("bottom").background(GeometryReader { geometry in
                            Color.clear.preference(key: ChatBottomPreference.self, value: geometry.frame(in: .named("chat-scroll")).maxY)
                        })
                    }.scrollTargetLayout().padding()
                }
                .scrollPosition(id: $visibleMessage, anchor: .top)
                .onChange(of: visibleMessage) { _, value in
                    if restoredPosition && scrollInteracting && chatQuery.isEmpty, let value { UserDefaults.standard.set(value, forKey: "chat.position." + HistoryCache.key(api.server + "|" + session.id)) }
                }
                .coordinateSpace(name: "chat-scroll")
                .background(GeometryReader { geometry in Color.clear.preference(key: ChatHeightPreference.self, value: geometry.size.height) })
                .defaultScrollAnchor(.bottom)
                .modifier(ChatScrollInteraction(following: $following, interacting: $scrollInteracting, bottom: bottomY, height: viewportHeight))
                .onPreferenceChange(ChatHeightPreference.self) { viewportHeight = $0 }
                .onPreferenceChange(ChatBottomPreference.self) { value in
                    bottomY = value
                    if !scrollInteracting && value <= viewportHeight + 80 { following = true }
                }
                .onChange(of: store.renderRevision) { _, _ in
                    if !restoredPosition, !store.messages.isEmpty {
                        restoredPosition = true
                        if let saved = UserDefaults.standard.string(forKey: "chat.position." + HistoryCache.key(api.server + "|" + session.id)), store.messages.contains(where: { $0.id == saved }) {
                            following = false; proxy.scrollTo(saved, anchor: .top); return
                        }
                    }
                    if following && !scrollInteracting && !store.loadingOlder { proxy.scrollTo("bottom", anchor: .bottom) }
                }
                .overlay(alignment: .bottomTrailing) {
                    if !following {
                        Button("Últimas mensagens", systemImage: "arrow.down") {
                            following = true; proxy.scrollTo("bottom", anchor: .bottom)
                            UserDefaults.standard.removeObject(forKey: "chat.position." + HistoryCache.key(api.server + "|" + session.id))
                        }
                            .font(.caption.weight(.semibold)).buttonStyle(.borderedProminent).padding(10)
                    }
                }
            }
    }
    @ViewBuilder private var notices: some View {
            if let error = store.error {
                Text(error).font(.caption).foregroundStyle(.red).padding(10).frame(maxWidth: .infinity).background(.red.opacity(0.06))
            }
            if api.reachable == false {
                Label("Sem conexão com notebook. Verifique Tailscale. Nenhuma mensagem será reenviada automaticamente.", systemImage: "wifi.exclamationmark")
                    .font(.caption).foregroundStyle(.orange).padding(8)
            }
            if let sendError = store.sendError {
                HStack(alignment: .top) {
                    Text(sendError).font(.caption).foregroundStyle(.red)
                    Button("Fechar aviso") { store.sendError = nil }.font(.caption2)
                }.padding(10)
            }
            if let draftError { Text(draftError).font(.caption).foregroundStyle(.red).padding(.horizontal) }
    }
    private var questionCards: some View {
            ForEach(store.questions) { form in
                Button { question = form } label: {
                    HStack {
                        Image(systemName: "questionmark.bubble.fill")
                        VStack(alignment: .leading, spacing: 3) {
                            Text("A IA fez uma pergunta").font(.caption.weight(.semibold))
                            Text(form.title).font(.subheadline).lineLimit(2)
                        }
                        Spacer()
                        Image(systemName: "chevron.right")
                    }.padding(12).frame(maxWidth: .infinity, alignment: .leading).background(Style.blue.opacity(0.08))
                }.accessibilityLabel("Responder: \(form.title)")
            }
    }
    @ViewBuilder private var permissionCards: some View {
            if !store.permissions.isEmpty {
                ScrollView {
                    VStack(spacing: 1) {
            ForEach(store.permissions) { permission in
                PermissionCard(permission: permission, details: store.permissionDetails[permission.id], strict: session.isPhoneControl) { decision in
                    await store.reply(api, session: session, permission: permission, decision: decision)
                }
            }
                    }
                }.frame(maxHeight: 270)
            }
    }
    @ViewBuilder private var attachmentStrip: some View {
            if !attachments.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack {
                        ForEach(attachments) { file in
                            AttachmentChip(file: file, disabled: store.sending) {
                                do { preview = try PrivateTransferFiles.preview(file) }
                                catch { store.sendError = error.localizedDescription }
                            } remove: { attachments.removeAll { $0.id == file.id } }
                        }
                    }.padding(.horizontal).padding(.top, 8)
                }
            }
    }
    private var composer: some View {
            HStack(alignment: .bottom, spacing: 12) {
                Menu {
                    Button("Buscar no histórico completo", systemImage: "text.magnifyingglass") { showFullSearch = true }
                    Button("Favoritar projeto", systemImage: "star") {
                        do { try projects.add(server: api.server, name: URL(fileURLWithPath: session.location.directory).lastPathComponent.isEmpty ? "Projeto" : URL(fileURLWithPath: session.location.directory).lastPathComponent, directory: session.location.directory) }
                        catch { store.sendError = error.localizedDescription }
                    }
                    Button("Buscar nesta conversa", systemImage: "magnifyingglass") { showChatSearch.toggle(); if !showChatSearch { chatQuery = "" } }
                    Button("Arquivos", systemImage: "folder") { selectingFiles = true }
                    Button("Fotos", systemImage: "photo") { selectingPhotos = true }
                } label: {
                    Image(systemName: importing ? "hourglass" : "plus.circle").font(.system(size: 28)).padding(.bottom, 4)
                }.disabled(importing || store.sending || attachments.count >= 5).accessibilityLabel("Anexar fotos ou arquivos")
                TextField("Peça algo ao OpenCode…", text: $draft, axis: .vertical)
                    .lineLimit(1...6).padding(12).background(Style.paper, in: RoundedRectangle(cornerRadius: 16))
                    .accessibilityLabel("Mensagem")
                    .accessibilityIdentifier("chat.composer")
                Button {
                    let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
                    let submitted = attachments
                    Task {
                        if await store.send(api, session: session, text: text, files: submitted) {
                            if draft.trimmingCharacters(in: .whitespacesAndNewlines) == text { draft = "" }
                            attachments.removeAll { file in submitted.contains { $0.id == file.id } }
                        }
                    }
                } label: {
                    Image(systemName: store.sending ? "ellipsis" : "arrow.up.circle.fill").font(.system(size: 36))
                }.disabled(store.sending || importing || changingAgent || api.reachable == false || (session.isPhoneControl && !controlAllowed) || (draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && attachments.isEmpty))
                    .accessibilityLabel("Enviar mensagem")
            }.padding().background(.bar)
    }
    private var navigationContent: some View {
        chatContent
        .navigationTitle(session.title ?? "Conversa").navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Menu {
                    Button("Nome, modo e modelo", systemImage: "slider.horizontal.3") { options = true }
                    Button("Arquivos do projeto", systemImage: "folder") { fileBrowser = true }
                    Button("Interromper tarefa", systemImage: "stop.circle", role: .destructive) { stop = true }
                } label: { Image(systemName: "ellipsis.circle") }.accessibilityLabel("Opções da conversa")
            }
        }
    }
    private var presentationContent: some View {
        navigationContent
        .sheet(isPresented: $options) { ChatOptionsView(session: $session) }
        .sheet(isPresented: $controlPanel) { PhoneControlView() }
        .sheet(isPresented: $showFullSearch) { FullChatSearchView(sessionID: session.id) }
        .sheet(isPresented: $fileBrowser) { FileBrowserView(initialDirectory: session.location.directory) }
        .sheet(item: $preview) { FilePreviewView(file: $0) }
        .sheet(item: $question) { form in
            QuestionFormView(question: form, session: session) { Task { await store.refresh(api, session: session) } }
        }
        .photosPicker(isPresented: $selectingPhotos, selection: $photos, maxSelectionCount: max(1, 5 - attachments.count), matching: .images, preferredItemEncoding: .compatible)
        .fileImporter(isPresented: $selectingFiles, allowedContentTypes: [.item], allowsMultipleSelection: true) { result in
            Task {
                importing = true
                defer { importing = false }
                do {
                    for url in try result.get() {
                        let file = try await Task.detached(priority: .userInitiated) { try FileLoader.read(url) }.value
                        try append(file)
                    }
                } catch { store.error = error.localizedDescription }
            }
        }
        .onChange(of: photos) { _, selection in
            guard !selection.isEmpty else { return }
            Task {
                importing = true
                defer { importing = false; photos = [] }
                do {
                    for item in selection {
                        guard let data = try await item.loadTransferable(type: Data.self) else { throw PhoneError.message("Não foi possível carregar foto.") }
                        try append(FileLoader.photo(data, index: attachments.count + 1))
                    }
                } catch { store.error = error.localizedDescription }
            }
        }
        .confirmationDialog("Interromper tarefa no notebook?", isPresented: $stop) {
            Button("Interromper", role: .destructive) { Task { await store.interrupt(api, session: session) } }
        }
        .alert("Troca de modo não confirmada", isPresented: Binding(get: { modeError != nil }, set: { if !$0 { modeError = nil } })) {
            Button("Entendi", role: .cancel) { modeError = nil }
        } message: { Text(modeError ?? "") }
    }
    private var lifecycleContent: some View {
        presentationContent
        .onAppear { restoreDraft() }
        .onDisappear { draftSaveTask?.cancel(); saveDraft(); store.stopLiveUpdates() }
        .onChange(of: draft) { _, _ in scheduleDraft() }
        .onChange(of: attachments.map(\.id)) { _, _ in scheduleDraft() }
        .onChange(of: store.sendUnconfirmed) { _, _ in scheduleDraft() }
        .onChange(of: phase) { _, value in if value != .active { draftSaveTask?.cancel(); saveDraft() } }
        .onChange(of: store.sessionSnapshot) { _, value in
            guard !changingAgent, let value, value.id == session.id else { return }
            session = value
            markReadIfVisible(value)
        }
        .task(id: phase) {
            guard phase == .active else { return }
            defer { store.liveConnected = false }
            var delay = 1
            while !Task.isCancelled {
                do {
                    try await api.watchSession(session.id) { type in store.receiveEvent(type, api: api, session: session) }
                    delay = 1
                    store.liveConnected = false
                } catch { store.liveConnected = false }
                do { try await Task.sleep(for: .seconds(delay)) } catch { break }
                delay = min(10, delay * 2)
            }
        }
        .task(id: phase) {
            guard phase == .active else { return }
            while !Task.isCancelled {
                await store.refresh(api, session: session)
                guard phase == .active && !Task.isCancelled else { return }
                if let snapshot = store.sessionSnapshot { markReadIfVisible(snapshot) }
                if session.isPhoneControl && Date().timeIntervalSince(controlCheck) > 5 {
                    await refreshControl()
                }
                do { try await Task.sleep(for: .seconds(5)) } catch { break }
            }
        }
    }
    func markReadIfVisible(_ snapshot: Session) {
        if phase == .active && store.error == nil && !options && !controlPanel && !fileBrowser && preview == nil && !selectingFiles && !selectingPhotos && question == nil {
            unread.markRead(snapshot, server: api.server)
        }
    }
    func restoreDraft() {
        guard !draftLoaded && !draftRecoveryBlocked else { return }
        do {
            if let restored = try drafts.load(server: api.server, sessionID: session.id) {
                draft = restored.text; attachments = restored.files; store.sendUnconfirmed = restored.unconfirmed
                if restored.unconfirmed { store.sendError = "Rascunho de envio não confirmado recuperado. Confira conversa antes de enviar de novo; nada foi reenviado automaticamente." }
            }
        } catch {
            draftRecoveryBlocked = true
            draftError = "Não foi possível recuperar rascunho: \(error.localizedDescription). Original foi preservado; alterações atuais não serão salvas por cima dele."
            return
        }
        draftLoaded = true
        scheduleDraft()
    }
    func scheduleDraft() {
        guard draftLoaded else { return }
        draftSavedAt = nil
        draftSaveTask?.cancel()
        draftSaveTask = Task { do { try await Task.sleep(for: .milliseconds(350)); saveDraft() } catch { } }
    }
    func saveDraft() {
        guard draftLoaded else { return }
        do {
            try drafts.save(server: api.server, sessionID: session.id, text: draft, files: attachments, unconfirmed: store.sendUnconfirmed)
            draftSavedAt = Date(); draftError = nil
        } catch { draftError = "Rascunho não salvo: \(error.localizedDescription)" }
    }
    func append(_ file: PendingFile) throws {
        try PendingFile.validate(attachments + [file])
        attachments.append(file)
        store.error = nil
    }
    func refreshControl() async {
        do {
            let status: ControlStatus = try await api.request("/phone/control/status")
            controlAllowed = status.enabled
            controlSummary = status.enabled ? status.activity : "Automação pausada — libere no painel"
            controlCheck = Date()
        } catch { controlSummary = "Estado da automação não confirmado" }
    }
    func stopControl() async {
        stoppingControl = true
        defer { stoppingControl = false }
        do {
            let result: ControlStopped = try await api.request("/phone/control/stop", method: "POST", body: [:])
            guard !result.enabled else { throw PhoneError.message("Bloqueio não confirmado.") }
            controlAllowed = false
            controlSummary = "Automação pausada"
            store.sendError = result.warnings.isEmpty ? "Novas ações bloqueadas; interrupção solicitada. Ações anteriores não foram desfeitas." : result.warnings.joined(separator: " ")
        } catch { store.sendError = "Parada não confirmada. Bloqueie iPhone ou desconecte cabo. \(error.localizedDescription)" }
    }
    func switchAgent(_ agent: String) async {
        guard !changingAgent, agent != (session.agent ?? "build") else { return }
        changingAgent = true
        defer { changingAgent = false }
        do {
            session = try await store.changeAgent(agent, api: api, session: session)
            modeError = nil
        } catch { modeError = error.localizedDescription }
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
            if let text = message.text { MarkdownMessage(text: text) }
            if let failure = message.error {
                Label(failure.message ?? "Modelo não conseguiu responder. Confira conta e modelo nos ajustes do chat.", systemImage: "exclamationmark.triangle")
                    .foregroundStyle(.red).textSelection(.enabled)
            }
            ForEach(Array((message.files ?? []).enumerated()), id: \.offset) { _, file in
                Label(file.name ?? file.mime, systemImage: file.mime.hasPrefix("image/") ? "photo" : "paperclip")
                    .font(.caption).foregroundStyle(.secondary)
            }
            ForEach(Array((message.content ?? []).enumerated()), id: \.offset) { _, part in
                if part.type == "text", let text = part.text {
                    MarkdownMessage(text: text)
                } else if part.type == "tool" {
                    DisclosureGroup {
                        if let input = part.state?.input { Text(input.pretty).font(.system(.caption, design: .monospaced)).textSelection(.enabled) }
                        if let detail = part.state?.detail { Text(detail).font(.system(.caption, design: .monospaced)).textSelection(.enabled) }
                        if part.state?.input == nil && part.state?.detail == nil { Text("Detalhes não disponíveis nesta página. Confira notebook.").font(.caption) }
                    } label: { HStack(alignment: .top) {
                        Image(systemName: part.state?.status == "error" ? "exclamationmark.circle" : "terminal")
                        Text(part.name ?? "Ferramenta").font(.system(.caption, design: .monospaced))
                        Spacer()
                        Text(status(part.state?.status)).font(.caption2)
                    } }.foregroundStyle(.secondary).padding(10).background(Style.paper, in: RoundedRectangle(cornerRadius: 8))
                }
            }
        }
        .padding(16).frame(maxWidth: .infinity, alignment: .leading)
        .background(message.type == "user" ? Style.blue.opacity(0.07) : Color(uiColor: .secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 16))
        .contextMenu { Button("Copiar mensagem", systemImage: "doc.on.doc") { UIPasteboard.general.string = ([message.text ?? ""] + (message.content ?? []).compactMap(\.text)).joined(separator: "\n") } }
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
    @EnvironmentObject var privacy: PrivacyLock
    @State private var advanced = UserDefaults.standard.bool(forKey: "settings.advanced")
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
                    Text("Bolinha na lista indica resposta concluída ainda não aberta neste iPhone. Atualiza com app ativo ou ao reabrir; não é notificação em segundo plano.")
                    Text("Código de conexão é de uso único. Acesso fica no Chaves deste iPhone. Nunca informe senha Apple aqui.")
                    LabeledContent("Versão", value: Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "—")
                }
                if let error { Section { Text(error).foregroundStyle(.red) } }
                Section("Privacidade") {
                    Toggle("Face ID ou código ao abrir", isOn: Binding(get: { privacy.enabled }, set: { value in Task { await privacy.setEnabled(value) } }))
                    Text("Bloqueia acesso ao voltar do segundo plano. Também confirma operações sensíveis. Não impede captura de tela pelo sistema.").font(.caption)
                    Button("Limpar histórico offline") { do { try HistoryCache.clear() } catch { self.error = "Não foi possível limpar cache." } }
                    Toggle("Mostrar diagnósticos experimentais", isOn: $advanced).onChange(of: advanced) { _, value in UserDefaults.standard.set(value, forKey: "settings.advanced") }
                }
                Section("Manutenção") {
                    NavigationLink("Notificações opcionais") { NotificationSettingsView() }
                    NavigationLink("Aparelhos pareados") { PairedDevicesView() }
                    NavigationLink("Diagnóstico e atualização") { MaintenanceView() }
                }
                Button("Desconectar este iPhone", role: .destructive) { api.disconnect(); dismiss() }
            }
            .navigationTitle("Ajustes")
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
