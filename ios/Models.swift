import Foundation

struct Page<T: Decodable>: Decodable {
    let data: [T]
    let cursor: Cursor?
    struct Cursor: Decodable { let next: String?; let previous: String? }
}
struct Item<T: Decodable>: Decodable { let data: T }
struct Session: Decodable, Identifiable, Hashable {
    let id: String
    let title: String?
    let location: Location
    let model: Model?
    struct Location: Decodable { let directory: String }
    struct Model: Decodable { let providerID: String; let id: String }
    static func == (lhs: Self, rhs: Self) -> Bool { lhs.id == rhs.id }
    func hash(into hasher: inout Hasher) { hasher.combine(id) }
}
struct Message: Decodable, Identifiable {
    let id: String
    let type: String
    let text: String?
    let content: [Part]?
    let time: Time
    struct Time: Decodable { let created: Double; let completed: Double? }
    struct Part: Decodable {
        let type: String
        let text: String?
        let name: String?
        let state: State?
        struct State: Decodable { let status: String }
    }
    var visible: Bool { type == "user" || type == "assistant" }
}
struct Permission: Decodable, Identifiable {
    let id: String
    let action: String
    let resources: [String]
    let message: String?
}
struct Awake: Decodable { let awake: Bool }
struct PairResponse: Decodable { let token: String }
struct Accepted: Decodable { let data: AcceptedID; struct AcceptedID: Decodable { let id: String } }

enum PhoneError: LocalizedError {
    case message(String)
    var errorDescription: String? { if case .message(let text) = self { return text }; return nil }
}
