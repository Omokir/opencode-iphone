import Foundation
import Combine

@MainActor
final class ChatStore: ObservableObject {
    @Published var messages: [Message] = []
    @Published private(set) var latestPage: [Message] = []
    @Published var permissions: [Permission] = []
    @Published var error: String?
    @Published var sending = false
    @Published var sendError: String?
    @Published var sendUnconfirmed = false
    @Published var permissionDetails: [String: String] = [:]
    @Published var sessionSnapshot: Session?
    @Published var questions: [QuestionForm] = []
    @Published var loadingOlder = false
    @Published var olderCursor: String?
    @Published var refreshed = false
    @Published var liveConnected = false
    @Published var renderRevision = 0
    @Published var showingCache = false
    var activity: String {
        if showingCache { return "Histórico salvo · estado atual não confirmado" }
        if !permissions.isEmpty { return "Aguardando permissão" }
        if !questions.isEmpty { return "Aguardando sua resposta" }
        guard let last = messages.last else { return "Pronto" }
        if last.type == "user" { return "Aguardando resposta do notebook" }
        if last.error != nil { return "Resposta com erro" }
        return last.time.completed == nil ? "Executando" : "Finalizado"
    }
    private var pendingID: String?
    private var pendingFingerprint: Data?
    private var metadataRevision = 0
    private var ticket = 0
    private var appliedMessages = 0
    private var appliedMetadata = 0
    private var appliedFull = 0
    private var pump: Task<Void, Never>?
    private var pumpRevision = 0
    private var dirty = false
    private var fullDirty = false

    private func nextTicket() -> Int { ticket &+= 1; return ticket }
    private func applyMessages(_ page: Page<Message>, ticket: Int, older: Bool = false) {
        guard older || ticket >= appliedMessages else { return }
        var merged = Dictionary(messages.map { ($0.id, $0) }, uniquingKeysWith: { _, last in last })
        for message in page.data where message.visible {
            if !older || merged[message.id] == nil { merged[message.id] = message }
        }
        messages = merged.values.sorted { $0.time.created == $1.time.created ? $0.id < $1.id : $0.time.created < $1.time.created }
        if !older { appliedMessages = ticket }
        renderRevision &+= 1
    }
    private func applySession(_ value: Session, ticket: Int, revision: Int) {
        guard revision == metadataRevision, ticket >= appliedMetadata else { return }
        if let current = sessionSnapshot?.time?.updated, let next = value.time?.updated, next < current { return }
        sessionSnapshot = value
        appliedMetadata = ticket
    }

    func refresh(_ api: API, session: Session, olderPage: Bool = false) async {
        let refreshedServer = api.server
        if messages.isEmpty, !refreshed, !olderPage,
           let page: Page<Message> = api.cached("/api/session/\(session.id)/message?limit=50&order=desc") {
            applyMessages(page, ticket: 0)
            olderCursor = page.cursor?.next
            showingCache = true
        }
        let currentTicket = nextTicket()
        let revision = metadataRevision
        do {
            let sessionInfo: Item<Session> = try await api.request("/api/session/\(session.id)")
            var path = "/api/session/\(session.id)/message?limit=50"
            if olderPage, let cursor = olderCursor { path += "&cursor=" + API.escape(cursor) }
            else { path += "&order=desc" }
            let page: Page<Message> = try await api.request(path)
            guard api.connected, api.server == refreshedServer else { return }
            if !olderPage { latestPage = page.data }
            if olderPage || !refreshed { olderCursor = page.cursor?.next }
            applyMessages(page, ticket: currentTicket, older: olderPage)
            showingCache = false
            let requests: Page<Permission> = try await api.request("/api/session/\(session.id)/permission")
            let questionsPage: Page<QuestionForm> = try await api.request("/api/session/\(session.id)/form")
            guard currentTicket >= appliedFull else { return }
            appliedFull = currentTicket
            permissions = requests.data
            for permission in requests.data {
                PocketNotifications.shared.post(key: "permission|\(api.server)|\(session.id)|\(permission.id)", title: "Permissão aguardando revisão", body: "Abra Pocket e leia pedido antes de autorizar.")
            }
            questions = questionsPage.data
            permissionDetails = permissionDetails.filter { key, _ in requests.data.contains { $0.id == key } }
            for request in requests.data {
                guard permissionDetails[request.id] == nil, let source = request.source else { continue }
                var message = messages.first { $0.id == source.messageID }
                if message == nil {
                    let full: Item<Message> = try await api.request("/api/session/\(session.id)/message/\(source.messageID)")
                    message = full.data
                }
                if let input = message?.content?.first(where: { $0.id == source.id })?.state?.input {
                    permissionDetails[request.id] = input.pretty
                }
            }
            error = nil
            applySession(sessionInfo.data, ticket: currentTicket, revision: revision)
            refreshed = true
            if !olderPage, api.connected, api.server == refreshedServer {
                TaskHistory.shared.reconcile(server: refreshedServer, session: sessionInfo.data, messages: page.data, waitingPermission: !permissions.isEmpty, waitingQuestion: !questions.isEmpty)
            }
        } catch is CancellationError { }
        catch let failure as URLError where failure.code == .cancelled { }
        catch { self.error = ConnectionAdvice.describe(error) }
    }

    func receiveEvent(_ type: String, api: API, session: Session) {
        liveConnected = true
        dirty = true
        let lower = type.lowercased()
        fullDirty = fullDirty || lower.contains("permission") || lower.contains("form") || type == "connected" || !refreshed
        guard pump == nil else { return }
        let generation = pumpRevision
        pump = Task {
            defer { if generation == pumpRevision { pump = nil } }
            while dirty && !Task.isCancelled && generation == pumpRevision {
                let full = fullDirty
                dirty = false
                fullDirty = false
                do { try await Task.sleep(for: .milliseconds(300)) } catch { break }
                if full { await refresh(api, session: session) }
                else { await refreshStreaming(api, session: session) }
            }
        }
    }
    func stopLiveUpdates() {
        pumpRevision &+= 1
        pump?.cancel()
        pump = nil
        dirty = false
        liveConnected = false
    }
    private func refreshStreaming(_ api: API, session: Session) async {
        let currentTicket = nextTicket()
        let revision = metadataRevision
        do {
            let info: Item<Session> = try await api.request("/api/session/\(session.id)")
            let page: Page<Message> = try await api.request("/api/session/\(session.id)/message?limit=5&order=desc&type=assistant")
            try Task.checkCancellation()
            applyMessages(page, ticket: currentTicket)
            applySession(info.data, ticket: currentTicket, revision: revision)
        } catch { liveConnected = false }
    }
    func changeAgent(_ agent: String, api: API, session: Session) async throws -> Session {
        metadataRevision &+= 1
        let _: EmptyResponse = try await api.request("/api/session/\(session.id)/agent", method: "POST", body: ["agent": agent])
        let confirmed: Item<Session> = try await api.request("/api/session/\(session.id)")
        guard confirmed.data.agent == agent else { throw PhoneError.message("Servidor ainda não confirmou modo solicitado. Confira estado antes de tentar novamente.") }
        metadataRevision &+= 1
        sessionSnapshot = confirmed.data
        return confirmed.data
    }

    func send(_ api: API, session: Session, text: String, files: [PendingFile] = []) async -> Bool {
        guard !sending else { return false }
        sending = true
        defer { sending = false }
        var attempted = false
        let submittedServer = api.server
        do {
            try PendingFile.validate(files)
            if !files.isEmpty, let model = session.model {
                let catalog: Catalog = try await api.request("/phone/catalog?directory=" + API.escape(session.location.directory))
                if let selected = catalog.models.first(where: { $0.key == model.key }) {
                    let unsupported = files.filter { !selected.capabilities.input.contains($0.category) }
                    if !unsupported.isEmpty {
                        throw PhoneError.message("Modelo selecionado não aceita estes anexos: \(unsupported.map(\.name).joined(separator: ", ")). Selecione modelo com suporte a \(Set(unsupported.map(\.category)).sorted().joined(separator: ", ")).")
                    }
                }
            }
            let content: [String: Any] = ["text": text, "files": files.map(\.payload)]
            let fingerprint = try JSONSerialization.data(withJSONObject: content, options: [.sortedKeys])
            if pendingFingerprint != fingerprint || pendingID == nil {
                pendingID = RequestID.message()
                pendingFingerprint = fingerprint
            }
            var body = content
            body["id"] = pendingID!
            guard api.connected, api.server == submittedServer else { throw PhoneError.message("Conexão mudou antes do envio.") }
            try TaskHistory.shared.begin(server: submittedServer, sessionID: session.id, requestID: pendingID!, text: text)
            attempted = true
            let _: Accepted = try await api.request("/api/session/\(session.id)/prompt", method: "POST",
                                                  body: body)
            TaskHistory.shared.set(pendingID!, server: submittedServer, state: "admitted")
            pendingID = nil
            pendingFingerprint = nil
            sendError = nil
            sendUnconfirmed = false
            if api.server == submittedServer && api.connected { await refresh(api, session: session) }
            return true
        } catch {
            if attempted { sendUnconfirmed = true }
            if attempted, let pendingID { TaskHistory.shared.set(pendingID, server: submittedServer, state: "uncertain") }
            self.sendError = (attempted ? "Envio não confirmado: " : "Não foi enviado: ") + error.localizedDescription + " Confira conversa antes de tentar novamente. Texto e anexos foram mantidos."
            return false
        }
    }

    func reply(_ api: API, session: Session, permission: Permission, decision: String) async {
        struct Empty: Decodable {}
        do {
            let _: Empty = try await api.request("/api/session/\(session.id)/permission/\(permission.id)/reply",
                                                 method: "POST", body: ["decision": decision])
            await refresh(api, session: session)
        } catch { self.error = error.localizedDescription }
    }

    func interrupt(_ api: API, session: Session) async {
        struct Response: Decodable {}
        do {
            let _: Response = try await api.request("/api/session/\(session.id)/interrupt", method: "POST", body: [:])
            await refresh(api, session: session)
        } catch { self.error = error.localizedDescription }
    }
}
