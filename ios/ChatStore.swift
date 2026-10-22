import Foundation
import Combine

@MainActor
final class ChatStore: ObservableObject {
    @Published var messages: [Message] = []
    @Published var permissions: [Permission] = []
    @Published var error: String?
    @Published var sending = false
    @Published var loadingOlder = false
    @Published var olderCursor: String?
    @Published var refreshed = false
    private var pendingID: String?
    private var pendingText: String?
    private var newest: [Message] = []
    private var older: [Message] = []

    func refresh(_ api: API, session: Session, olderPage: Bool = false) async {
        do {
            var path = "/api/session/\(session.id)/message?limit=50"
            if olderPage, let cursor = olderCursor { path += "&cursor=" + API.escape(cursor) }
            else { path += "&order=desc" }
            let page: Page<Message> = try await api.request(path)
            if olderPage { older += page.data } else { newest = page.data }
            if olderPage || !refreshed { olderCursor = page.cursor?.next }
            var merged = Dictionary(older.map { ($0.id, $0) }, uniquingKeysWith: { _, last in last })
            // Preserve already-seen messages even when the newest page moves forward.
            for message in messages { merged[message.id] = message }
            for message in newest { merged[message.id] = message }
            messages = merged.values.filter(\.visible).sorted {
                $0.time.created == $1.time.created ? $0.id < $1.id : $0.time.created < $1.time.created
            }
            let requests: Page<Permission> = try await api.request("/api/session/\(session.id)/permission")
            permissions = requests.data
            error = nil
            refreshed = true
        } catch is CancellationError { }
        catch let failure as URLError where failure.code == .cancelled { }
        catch { self.error = error.localizedDescription }
    }

    func send(_ api: API, session: Session, text: String) async -> Bool {
        guard !sending else { return false }
        sending = true
        defer { sending = false }
        if pendingText != text || pendingID == nil {
            pendingID = "msg" + UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased()
            pendingText = text
        }
        do {
            let _: Accepted = try await api.request("/api/session/\(session.id)/prompt", method: "POST",
                                                  body: ["id": pendingID!, "text": text])
            pendingID = nil
            pendingText = nil
            await refresh(api, session: session)
            return true
        } catch {
            self.error = "Envio não confirmado: \(error.localizedDescription) Confira conversa antes de tentar novamente."
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
