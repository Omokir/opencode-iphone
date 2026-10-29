import Foundation
import Security
import Combine
import UIKit

private final class PrivateAPITransport: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
    func urlSession(_ session: URLSession, task: URLSessionTask,
                    willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest,
                    completionHandler: @escaping @Sendable (URLRequest?) -> Void) { completionHandler(nil) }
}

enum Vault {
    private static var query: [String: Any] {
        [kSecClass as String: kSecClassGenericPassword,
         kSecAttrService as String: "com.omokir.opencodephone",
         kSecAttrAccount as String: "mobile-token"]
    }
    static func read() -> String? {
        var q = query
        q[kSecReturnData as String] = true
        q[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        guard SecItemCopyMatching(q as CFDictionary, &result) == errSecSuccess,
              let data = result as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }
    static func save(_ value: String) throws {
        var q = query
        let data = Data(value.utf8)
        let status = SecItemUpdate(q as CFDictionary, [kSecValueData as String: data] as CFDictionary)
        if status == errSecItemNotFound {
            q[kSecValueData as String] = data
            q[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            guard SecItemAdd(q as CFDictionary, nil) == errSecSuccess else {
                throw PhoneError.message("Não foi possível salvar conexão no Chaves do iPhone.")
            }
        } else if status != errSecSuccess {
            throw PhoneError.message("Não foi possível atualizar conexão segura.")
        }
    }
    static func clear() { SecItemDelete(query as CFDictionary) }
}

@MainActor
final class API: ObservableObject {
    @Published var connected = false
    @Published var server: String
    @Published var reachable: Bool?
    @Published var connectionIssue: String?
    @Published private(set) var connectionID = UUID()
    private var token: String?
    let transport: URLSession
    private let eventTransport: URLSession

    init() {
        server = UserDefaults.standard.string(forKey: "server") ?? ""
        token = Vault.read()
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 15
        configuration.timeoutIntervalForResource = 3600
        configuration.waitsForConnectivity = false
        configuration.httpShouldSetCookies = false
        configuration.urlCache = nil
        transport = URLSession(configuration: configuration, delegate: PrivateAPITransport(), delegateQueue: nil)
        eventTransport = URLSession(configuration: configuration, delegate: PrivateAPITransport(), delegateQueue: nil)
        connected = token != nil && !server.isEmpty
    }

    static func validate(_ value: String) throws -> URL {
        guard let parts = URLComponents(string: value.trimmingCharacters(in: .whitespacesAndNewlines)),
              parts.scheme == "https", let host = parts.host,
              host.hasSuffix(".ts.net"), parts.user == nil, parts.password == nil,
              parts.query == nil, parts.fragment == nil,
              parts.path.isEmpty || parts.path == "/", let url = parts.url else {
            throw PhoneError.message("Use endereço HTTPS do notebook no Tailscale, incluindo :8443.")
        }
        return url
    }

    func request<T: Decodable>(_ path: String, method: String = "GET", body: [String: Any]? = nil,
                               authenticated: Bool = true) async throws -> T {
        #if SNAPSHOT
        return try JSONDecoder().decode(T.self, from: Snapshot.response(path, method: method, body: body))
        #else
        var request = try makeRequest(path, method: method, authenticated: authenticated)
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let body { request.httpBody = try JSONSerialization.data(withJSONObject: body) }
        let data: Data
        let response: URLResponse
        let requestServer = server
        do {
            (data, response) = try await transport.data(for: request)
        } catch {
            if (error as? URLError)?.code != .cancelled { reachable = false; connectionIssue = ConnectionAdvice.describe(error) }
            throw error
        }
        reachable = true
        connectionIssue = nil
        guard let http = response as? HTTPURLResponse else { throw PhoneError.message("Resposta inválida.") }
        guard (200..<300).contains(http.statusCode) else {
            let object = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
            let nested = object?["error"] as? [String: Any]
            let message = object?["message"] as? String ?? object?["error"] as? String ?? nested?["message"] as? String ?? "Notebook respondeu HTTP \(http.statusCode)."
            throw PhoneError.message(message)
        }
        let payload = data.isEmpty ? Data("{}".utf8) : data
        let decoded = try JSONDecoder().decode(T.self, from: payload)
        if method == "GET", requestServer == server { HistoryCache.save(payload, server: requestServer, path: path) }
        return decoded
        #endif
    }

    func makeRequest(_ path: String, method: String = "GET", authenticated: Bool = true) throws -> URLRequest {
        guard path.hasPrefix("/"), !path.hasPrefix("//") else { throw PhoneError.message("Caminho inválido.") }
        let base = try Self.validate(server).absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        guard let url = URL(string: base + path) else { throw PhoneError.message("Endereço inválido.") }
        var request = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData)
        request.httpMethod = method
        request.setValue(connectionID.uuidString, forHTTPHeaderField: "X-Pocket-Connection-ID")
        if authenticated {
            guard let token else { throw PhoneError.message("Conecte novamente ao notebook.") }
            request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
        }
        return request
    }

    func watchSession(_ id: String, changed: @MainActor (String) -> Void) async throws {
        #if SNAPSHOT
        changed("connected")
        while !Task.isCancelled {
            try await Task.sleep(for: .seconds(1))
            changed("session.changed")
        }
        #else
        var request = try makeRequest("/phone/session/\(id)/events")
        request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        request.timeoutInterval = 65
        let (bytes, response) = try await eventTransport.bytes(for: request)
        defer { bytes.task.cancel() }
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw PhoneError.message("Atualização ao vivo indisponível; consulta periódica continua.")
        }
        struct Hint: Decodable { let type: String }
        for try await line in bytes.lines {
            try Task.checkCancellation()
            if line.hasPrefix("data:"), let data = String(line.dropFirst(5)).trimmingCharacters(in: .whitespaces).data(using: .utf8),
               let hint = try? JSONDecoder().decode(Hint.self, from: data) { changed(hint.type) }
        }
        #endif
    }

    func pair(server address: String, code: String) async throws {
        _ = try Self.validate(address)
        let previous = server
        server = address.trimmingCharacters(in: .whitespacesAndNewlines)
        do {
            let response: PairResponse = try await request("/pair", method: "POST", body: ["code": code, "name": UIDevice.current.model], authenticated: false)
            try Vault.save(response.token)
            token = response.token
            UserDefaults.standard.set(server, forKey: "server")
            connected = true
        } catch {
            server = previous
            throw error
        }
    }

    func watchKzL(revision: String, changed: @MainActor () -> Void) async throws {
        var request = try makeRequest("/phone/kzl/events?revision=" + Self.escape(revision))
        request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        request.timeoutInterval = 20
        let (bytes, response) = try await eventTransport.bytes(for: request)
        defer { bytes.task.cancel() }
        guard (response as? HTTPURLResponse)?.statusCode == 200 else { throw PhoneError.message("Acompanhamento indisponível.") }
        for try await line in bytes.lines {
            try Task.checkCancellation()
            if line.hasPrefix("data:") { changed(); return }
        }
    }

    func disconnect() {
        BackgroundInbox.shared.cancelAll()
        let previousConnection = connectionID.uuidString
        connectionID = UUID()
        transport.getAllTasks { tasks in
            tasks.filter { $0.originalRequest?.value(forHTTPHeaderField: "X-Pocket-Connection-ID") == previousConnection }.forEach { $0.cancel() }
        }
        eventTransport.getAllTasks { tasks in tasks.forEach { $0.cancel() } }
        Vault.clear()
        token = nil
        connected = false
        reachable = nil
        connectionIssue = nil
    }

    func cached<T: Decodable>(_ path: String) -> T? { HistoryCache.read(server: server, path: path) }

    static func escape(_ value: String) -> String {
        value.addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? ""
    }
}
