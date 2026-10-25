import Foundation
import Combine

@MainActor final class TransferActivity: ObservableObject {
    struct Record: Codable, Identifiable {
        let id: UUID
        let serverKey: String
        let name: String
        let destination: String
        let direction: String
        let date: Date
        var state: String
        var completed: Int64
        let total: Int64?
        var uploadID: UUID?
        var root: String?
        var remotePath: String?
        var digest: String?
    }
    static let shared = TransferActivity()
    @Published private(set) var records: [Record]
    private let archive: PrivateActivityArchive<Record>
    private var cancellations: [UUID: () -> Void] = [:]
    init(url: URL? = nil) {
        archive = PrivateActivityArchive(url: url ?? PrivateActivityArchive<Record>.appURL("transfers.json"))
        records = Array(archive.load().prefix(100))
        for index in records.indices where ["sending", "receiving", "verifying"].contains(records[index].state) { records[index].state = "uncertain" }
    }
    func begin(server: String, name: String, destination: String, direction: String, total: Int64?, uploadID: UUID? = nil, root: String? = nil, remotePath: String? = nil, digest: String? = nil) throws -> UUID {
        let id = UUID()
        var next = records
        if next.count >= 100 {
            guard let index = next.lastIndex(where: { !["sending", "receiving", "verifying"].contains($0.state) }) else { throw PhoneError.message("Muitas transferências ativas; conclua ou cancele antes de iniciar outra.") }
            next.remove(at: index)
        }
        next.insert(Record(id: id, serverKey: TaskHistory.serverKey(server), name: name, destination: destination, direction: direction, date: Date(), state: direction == "upload" ? "sending" : "receiving", completed: 0, total: total, uploadID: uploadID, root: root, remotePath: remotePath, digest: digest), at: 0)
        try archive.save(next); records = next
        return id
    }
    func bind(_ id: UUID, cancel: @escaping () -> Void) { cancellations[id] = cancel }
    func stage(_ id: UUID, state: String) {
        guard let index = records.firstIndex(where: { $0.id == id }) else { return }
        records[index].state = state; try? archive.save(records)
    }
    func cancel(_ id: UUID) { cancellations[id]?(); finish(id, state: "uncertain") }
    func finish(_ id: UUID, state: String) {
        guard let index = records.firstIndex(where: { $0.id == id }) else { return }
        records[index].state = state
        if state == "completed", let total = records[index].total { records[index].completed = total }
        cancellations[id] = nil; try? archive.save(records)
    }
    func observe(_ api: API) async {
        let server = api.server
        let tasks: [URLSessionTask] = await withCheckedContinuation { continuation in api.transport.getAllTasks { continuation.resume(returning: $0) } }
        guard server == api.server else { return }
        for task in tasks {
            guard let raw = task.originalRequest?.value(forHTTPHeaderField: "X-Transfer-ID"), let id = UUID(uuidString: raw),
                  let index = records.firstIndex(where: { $0.id == id && $0.serverKey == TaskHistory.serverKey(server) }) else { continue }
            records[index].completed = max(0, records[index].direction == "upload" ? task.countOfBytesSent : task.countOfBytesReceived)
        }
    }
    static func label(_ state: String) -> String {
        switch state {
        case "sending": return "Enviando"
        case "receiving": return "Baixando"
        case "verifying": return "Verificando"
        case "completed": return "Transferência concluída"
        case "blocked": return "Bloqueada por conflito · destino não substituído"
        case "receipt": return "Recibo encontrado · consulte estado atual da pasta"
        default: return "Resultado incerto · confira destino antes de repetir"
        }
    }
}
