import Foundation

enum SessionSearch {
    static func path(query: String, cursor: String? = nil) -> String {
        var components = URLComponents()
        components.path = "/api/session"
        components.queryItems = [URLQueryItem(name: "limit", value: "30"), URLQueryItem(name: "archived", value: "false"), URLQueryItem(name: "parentID", value: "null"), URLQueryItem(name: "search", value: query.trimmingCharacters(in: .whitespacesAndNewlines))]
        components.queryItems?.append(URLQueryItem(name: cursor == nil ? "order" : "cursor", value: cursor ?? "desc"))
        return components.string!
    }
}

enum RequestID {
    static func message() -> String {
        "msg_" + UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased()
    }
}

struct Page<T: Decodable>: Decodable {
    let data: [T]
    let cursor: Cursor?
    struct Cursor: Decodable { let next: String?; let previous: String? }
}
struct Item<T: Decodable>: Decodable { let data: T }
struct Session: Decodable, Identifiable, Hashable {
    let id: String
    var title: String?
    let location: Location
    let model: Model?
    let agent: String?
    let time: Time?
    let outcome: String?
    struct Time: Decodable, Equatable { let created: Double; let updated: Double; let idle: Double? }
    var completionStamp: Double? {
        guard ["succeeded", "failed", "interrupted"].contains(outcome ?? "") else { return nil }
        return time?.idle
    }
    let metadata: Metadata?
    struct Metadata: Decodable, Equatable { let phoneControl: Bool? }
    var isPhoneControl: Bool { metadata?.phoneControl == true }
    struct Location: Decodable, Equatable { let directory: String }
    struct Model: Decodable, Equatable {
        let providerID: String
        let id: String
        let variant: String?
        var key: String { providerID + "/" + id }
        var payload: [String: Any] {
            var value: [String: Any] = ["providerID": providerID, "id": id]
            if let variant { value["variant"] = variant }
            return value
        }
    }
    func hash(into hasher: inout Hasher) { hasher.combine(id) }
}
struct Message: Decodable, Identifiable {
    let id: String
    let type: String
    let text: String?
    let content: [Part]?
    let time: Time
    let error: Failure?
    let files: [FileInfo]?
    struct Failure: Decodable { let message: String?; let type: String? }
    struct FileInfo: Decodable { let name: String?; let mime: String }
    struct Time: Decodable { let created: Double; let completed: Double? }
    struct Part: Decodable {
        let id: String?
        let type: String
        let text: String?
        let name: String?
        let state: State?
        struct State: Decodable { let status: String; let input: JSONValue? }
    }
    var visible: Bool { type == "user" || type == "assistant" }
}
struct Permission: Decodable, Identifiable {
    let id: String
    let action: String
    let resources: [String]
    let message: String?
    let source: Source?
    struct Source: Decodable { let id: String; let messageID: String }
}

indirect enum JSONValue: Codable, Equatable {
    case string(String), number(Double), bool(Bool), object([String: JSONValue]), array([JSONValue]), null
    init(from decoder: Decoder) throws {
        let value = try decoder.singleValueContainer()
        if value.decodeNil() { self = .null }
        else if let v = try? value.decode(Bool.self) { self = .bool(v) }
        else if let v = try? value.decode(String.self) { self = .string(v) }
        else if let v = try? value.decode(Double.self) { self = .number(v) }
        else if let v = try? value.decode([String: JSONValue].self) { self = .object(v) }
        else { self = .array(try value.decode([JSONValue].self)) }
    }
    func encode(to encoder: Encoder) throws {
        var value = encoder.singleValueContainer()
        switch self {
        case .string(let v): try value.encode(v)
        case .number(let v): try value.encode(v)
        case .bool(let v): try value.encode(v)
        case .object(let v): try value.encode(v)
        case .array(let v): try value.encode(v)
        case .null: try value.encodeNil()
        }
    }
    var pretty: String {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
        return (try? String(data: encoder.encode(self), encoding: .utf8)) ?? ""
    }
    var object: Any {
        switch self {
        case .string(let value): return value
        case .number(let value): return value
        case .bool(let value): return value
        case .object(let value): return value.mapValues(\.object)
        case .array(let value): return value.map(\.object)
        case .null: return NSNull()
        }
    }
}
struct QuestionForm: Decodable, Identifiable {
    let id: String
    let title: String
    let fields: [Field]
    struct Field: Decodable, Identifiable {
        let key: String
        let type: String
        let title: String?
        let description: String?
        let required: Bool?
        let hidden: Bool?
        let when: [Condition]?
        let options: [Option]?
        let custom: Bool?
        let placeholder: String?
        let defaultValue: JSONValue?
        var id: String { key }
        enum CodingKeys: String, CodingKey {
            case key, type, title, description, required, hidden, when, options, custom, placeholder
            case defaultValue = "default"
        }
    }
    struct Option: Decodable, Identifiable { let value: String; let label: String; let description: String?; var id: String { value } }
    struct Condition: Decodable { let key: String; let op: String; let value: JSONValue }
    func visible(_ field: Field, answers: [String: JSONValue]) -> Bool {
        guard field.hidden != true else { return false }
        return (field.when ?? []).allSatisfy { condition in
            let equal = answers[condition.key] == condition.value
            return condition.op == "eq" ? equal : condition.op == "neq" ? !equal : false
        }
    }
}
struct Awake: Decodable { let awake: Bool }
struct HostStatus: Decodable {
    let awake: Bool
    let battery: Battery?
    let storage: StorageCapacity?
    struct Battery: Decodable {
        let available: Bool
        let percentage: Int?
        let charging: Bool?
        let onAC: Bool?
        let state: String?
    }
}
struct StorageCapacity: Decodable {
    let totalBytes: Int64
    let freeBytes: Int64
    var usedPercent: Double { totalBytes > 0 ? min(100, max(0, 100 * (1 - Double(freeBytes) / Double(totalBytes)))) : 0 }
    var freeGB: Double { Double(max(0, freeBytes)) / 1_000_000_000 }
    var totalGB: Double { Double(max(0, totalBytes)) / 1_000_000_000 }
}
struct CodexQuota: Decodable {
    let available: Bool
    let source: String
    let checkedAt: Double
    let accountLabel: String?
    let plan: String?
    let weekly: Window?
    let shortWindow: Window?
    let reason: String?
    struct Window: Decodable {
        let usedPercent: Double
        let windowMinutes: Double
        let resetsAt: Double?
        var remainingPercent: Double { max(0, 100 - usedPercent) }
    }
}
struct PairResponse: Decodable { let token: String }
struct Accepted: Decodable { let data: AcceptedID; struct AcceptedID: Decodable { let id: String } }
struct EmptyResponse: Decodable {}

struct ReadState: Codable {
    var baselines: [String: Double] = [:]
    var viewed: [String: Double] = [:]
    mutating func initialize(server: String, sessions: [Session]) {
        guard baselines[server] == nil else { return }
        // Baseline uses server timestamps, never the iPhone's possibly skewed clock.
        baselines[server] = sessions.compactMap { $0.time?.updated }.max() ?? 0
    }
    func isUnread(_ session: Session, server: String) -> Bool {
        guard let stamp = session.completionStamp, stamp > 0 else { return false }
        return stamp > (viewed[server + "|" + session.id] ?? baselines[server] ?? 0)
    }
    mutating func markRead(_ session: Session, server: String) {
        guard let stamp = session.completionStamp else { return }
        let key = server + "|" + session.id
        viewed[key] = max(viewed[key] ?? 0, stamp)
    }
}
struct PinState: Codable {
    var conversations: [String: [String]] = [:]
    func ids(server: String) -> [String] { conversations[server] ?? [] }
    func contains(_ id: String, server: String) -> Bool { ids(server: server).contains(id) }
    mutating func toggle(_ id: String, server: String) {
        var values = ids(server: server)
        if values.contains(id) { values.removeAll { $0 == id } }
        else { values.insert(id, at: 0) }
        conversations[server] = values
    }
}
struct ControlStatus: Decodable {
    let configured: Bool
    let enabled: Bool
    let expiresAt: Double?
    let sessionID: String?
    let device: Device
    let running: Bool
    let pending: Int
    let activity: String
    let ready: Bool
    struct Device: Decodable {
        let connected: Bool
        let agentInstalled: Bool
        let name: String
        let locked: Bool?
    }
}
struct ControlStopped: Decodable { let enabled: Bool; let warnings: [String] }
struct Catalog: Decodable { let models: [CatalogModel]; let agents: [AgentChoice] }
struct AgentChoice: Decodable, Identifiable { let id: String; let name: String }
struct CatalogModel: Decodable, Identifiable {
    let id: String
    let providerID: String
    let name: String
    let capabilities: Capabilities
    let variants: [Variant]
    let status: String
    struct Capabilities: Decodable { let input: [String] }
    struct Variant: Decodable, Identifiable { let id: String }
    var key: String { providerID + "/" + id }
}

struct PendingFile: Identifiable {
    static let maxFileBytes = 4 * 1024 * 1024
    static let maxTotalBytes = 8 * 1024 * 1024
    let id: UUID
    let name: String
    let mime: String
    let data: Data
    init(id: UUID = UUID(), name: String, mime: String, data: Data) {
        self.id = id; self.name = name; self.mime = mime; self.data = data
    }
    var category: String { mime.hasPrefix("image/") ? "image" : mime == "application/pdf" ? "pdf" : "text" }
    var payload: [String: Any] { ["uri": "data:\(mime);base64,\(data.base64EncodedString())", "name": name] }
    static func validate(_ files: [Self]) throws {
        guard files.count <= 5 else { throw PhoneError.message("Envie no máximo 5 anexos por mensagem.") }
        guard files.allSatisfy({ !$0.data.isEmpty && $0.data.count <= maxFileBytes }) else {
            throw PhoneError.message("Cada anexo precisa ter conteúdo e no máximo 4 MB.")
        }
        guard files.reduce(0, { $0 + $1.data.count }) <= maxTotalBytes else {
            throw PhoneError.message("Anexos juntos podem ter até 8 MB por mensagem.")
        }
    }
}

enum PhoneError: LocalizedError {
    case message(String)
    var errorDescription: String? { if case .message(let text) = self { return text }; return nil }
}
