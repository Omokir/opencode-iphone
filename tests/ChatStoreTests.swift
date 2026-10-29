import Foundation
import Darwin

// Transport and side effects are fixtures. The executable links the real ChatStore.
@MainActor final class API {
    var connected = true
    var server = "https://fixture.ts.net:8443"
    var connectionID = UUID()
    var cache: [String: Data] = [:]
    var handler: (String) async throws -> Data
    init(handler: @escaping (String) async throws -> Data) { self.handler = handler }
    func request<T: Decodable>(_ path: String, method: String = "GET", body: [String: Any]? = nil) async throws -> T {
        let data = try await handler(path)
        return try JSONDecoder().decode(T.self, from: data)
    }
    func cached<T: Decodable>(_ path: String) -> T? { cache[path].flatMap { try? JSONDecoder().decode(T.self, from: $0) } }
    static func escape(_ value: String) -> String { value.addingPercentEncoding(withAllowedCharacters: .alphanumerics)! }
}
enum ConnectionAdvice { static func describe(_ error: Error) -> String { "Fixture unavailable" } }
@MainActor struct PocketNotifications {
    static let shared = Self()
    func post(key: String, title: String, body: String) {}
}
@MainActor struct TaskHistory {
    static let shared = Self()
    func begin(server: String, sessionID: String, requestID: String, text: String) throws {}
    func set(_ id: String, server: String, state: String) {}
    func reconcile(server: String, session: Session, messages: [Message], waitingPermission: Bool, waitingQuestion: Bool) {}
}

@MainActor final class Signal {
    private var fired = false
    private var waiters: [CheckedContinuation<Void, Never>] = []
    func send() { fired = true; let pending = waiters; waiters = []; pending.forEach { $0.resume() } }
    func wait() async { if fired { return }; await withCheckedContinuation { waiters.append($0) } }
}

@main struct ChatStoreTests {
    @MainActor static func main() async throws {
        var failures = 0
        func check(_ value: Bool, _ name: String) {
            print((value ? "PASS: " : "FAIL: ") + name)
            if !value { failures += 1 }
        }
        let sessionJSON = Data(#"{"data":{"id":"ses_fixture","location":{"directory":"/fixture"},"title":"Fixture","time":{"created":1,"updated":2}}}"#.utf8)
        let session = try JSONDecoder().decode(Item<Session>.self, from: sessionJSON).data
        let history = Data(#"{"data":[{"id":"msg_user","type":"user","text":"Earlier question","time":{"created":1}},{"id":"msg_answer","type":"assistant","time":{"created":2},"content":[{"type":"text","text":"Old response"}]}],"cursor":{"next":"older"}}"#.utf8)
        let live = Data(#"{"data":[{"id":"msg_answer","type":"assistant","time":{"created":2},"content":[{"type":"text","text":"New response"}]}]}"#.utf8)
        let empty = Data(#"{"data":[]}"#.utf8)

        let metadataFailure = API { path in
            if path.contains("/message?") { return history }
            throw URLError(.cannotConnectToHost)
        }
        let first = ChatStore()
        await first.refresh(metadataFailure, session: session)
        check(first.messages.map(\.id).contains("msg_user"), "opening chat loads history even when metadata is unavailable")
        check(first.refreshed, "history readiness does not depend on permissions/forms")

        let pendingFailure = API { path in
            if path.contains("/message?") { return history }
            if path.hasSuffix("/permission") || path.hasSuffix("/form") { throw URLError(.timedOut) }
            return sessionJSON
        }
        let second = ChatStore()
        await second.refresh(pendingFailure, session: session)
        check(second.refreshed && second.messages.count == 2, "auxiliary endpoint failure never hides loaded history")

        let offline = API { _ in throw URLError(.notConnectedToInternet) }
        offline.cache["/api/session/ses_fixture/message?limit=50&order=desc"] = history
        let cached = ChatStore()
        await cached.refresh(offline, session: session)
        check(cached.showingCache && cached.messages.count == 2, "cached history remains visible offline")

        let requested = Signal(), release = Signal(), streamed = Signal()
        let racing = API { path in
            if path.contains("/message?") { return live }
            if path.hasSuffix("/permission") || path.hasSuffix("/form") { return empty }
            return sessionJSON
        }
        let store = ChatStore()
        await store.refresh(racing, session: session)
        racing.handler = { path in
            if path.contains("type=assistant") { streamed.send(); return live }
            if path.contains("/message?") { requested.send(); await release.wait(); return history }
            if path.hasSuffix("/permission") || path.hasSuffix("/form") { return empty }
            return sessionJSON
        }
        let loading = Task { await store.refresh(racing, session: session) }
        await requested.wait()
        store.receiveEvent("message.updated", api: racing, session: session)
        await streamed.wait()
        // The fixture transport completes on this actor; let its caller finish applying.
        await Task.yield()
        release.send()
        await loading.value
        store.stopLiveUpdates()
        check(store.messages.contains { $0.id == "msg_user" }, "newer assistant-only stream cannot discard older full history page")
        let response = store.messages.first { $0.id == "msg_answer" }?.content?.first?.text
        check(response == "New response", "late full page cannot overwrite newer streamed text")

        let waiting = Signal(), finish = Signal()
        let switched = API { path in
            if path.contains("/message?") { waiting.send(); await finish.wait(); return history }
            if path.hasSuffix("/permission") || path.hasSuffix("/form") { return empty }
            return sessionJSON
        }
        let isolated = ChatStore()
        let request = Task { await isolated.refresh(switched, session: session) }
        await waiting.wait()
        switched.connectionID = UUID()
        finish.send()
        await request.value
        check(isolated.messages.isEmpty, "reply from old pairing cannot populate new connection")

        if failures != 0 { exit(1) }
    }
}
