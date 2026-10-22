import Foundation

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
    let metadata: Metadata?
    struct Metadata: Decodable { let phoneControl: Bool? }
    var isPhoneControl: Bool { metadata?.phoneControl == true }
    struct Location: Decodable { let directory: String }
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
    static func == (lhs: Self, rhs: Self) -> Bool { lhs.id == rhs.id }
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

indirect enum JSONValue: Codable {
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
}
struct Awake: Decodable { let awake: Bool }
struct PairResponse: Decodable { let token: String }
struct Accepted: Decodable { let data: AcceptedID; struct AcceptedID: Decodable { let id: String } }
struct EmptyResponse: Decodable {}
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
    let id = UUID()
    let name: String
    let mime: String
    let data: Data
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
