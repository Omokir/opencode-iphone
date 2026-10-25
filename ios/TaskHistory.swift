import Foundation
import CryptoKit
import Combine

@MainActor final class TaskHistory: ObservableObject {
    struct Record: Codable, Identifiable {
        let id: UUID
        let serverKey: String
        let sessionID: String
        let requestID: String
        let title: String
        let date: Date
        var state: String
        var resultID: String?
    }
    static let shared = TaskHistory()
    @Published private(set) var records: [Record]
    @Published private(set) var storageError: String?
    private let archive: PrivateActivityArchive<Record>
    init(url: URL? = nil) {
        archive = PrivateActivityArchive(url: url ?? PrivateActivityArchive<Record>.appURL("tasks.json"))
        records = Array(archive.load().prefix(100))
        for index in records.indices where !Self.terminal(records[index].state) { records[index].state = "uncertain" }
    }
    static func serverKey(_ server: String) -> String { SHA256.hash(data: Data(server.utf8)).map { String(format: "%02x", $0) }.joined() }
    private static func terminal(_ state: String) -> Bool { ["completed", "failed", "interrupted", "uncertain"].contains(state) }
    func begin(server: String, sessionID: String, requestID: String, text: String) throws {
        guard !records.contains(where: { $0.serverKey == Self.serverKey(server) && $0.requestID == requestID }) else { return }
        if records.count >= 100, let index = records.lastIndex(where: { Self.terminal($0.state) }) { records.remove(at: index) }
        guard records.count < 100 else { throw PhoneError.message("Histórico de tarefas cheio; revise pendências antes de enviar mais.") }
        let item = Record(id: UUID(), serverKey: Self.serverKey(server), sessionID: sessionID, requestID: requestID,
                          title: text.isEmpty ? "Mensagem com anexos" : String(text.prefix(160)), date: Date(), state: "sending", resultID: nil)
        var next = records; next.insert(item, at: 0)
        try archive.save(next) // Must persist identity before a new write is admitted.
        records = next; storageError = nil
    }
    func set(_ requestID: String, server: String, state: String, resultID: String? = nil) {
        guard let index = records.firstIndex(where: { $0.requestID == requestID && $0.serverKey == Self.serverKey(server) }) else { return }
        let confirmed = ["completed", "failed", "interrupted"]
        if confirmed.contains(records[index].state) && !confirmed.contains(state) { return }
        records[index].state = state
        if let resultID { records[index].resultID = resultID }
        do { try archive.save(records); storageError = nil }
        catch { storageError = "Histórico de tarefa não pôde ser salvo. Confira conversa; não reenvie automaticamente." }
    }
    func reconcile(server: String, session: Session, messages: [Message], waitingPermission: Bool, waitingQuestion: Bool) {
        let candidates = records.filter { $0.serverKey == Self.serverKey(server) && $0.sessionID == session.id && !["completed", "failed", "interrupted"].contains($0.state) }
        for record in candidates {
            switch TaskReplyMatch.find(requestID: record.requestID, messages: messages) {
            case .completed(let id, let failed):
                set(record.requestID, server: server, state: failed ? "failed" : "completed", resultID: id)
            case .ambiguous: set(record.requestID, server: server, state: "uncertain")
            case .waiting:
                guard let request = messages.first(where: { $0.id == record.requestID }),
                      messages.filter({ $0.type == "user" && $0.time.created > request.time.created }).isEmpty else { continue }
                if session.outcome == "interrupted", (session.time?.idle ?? 0) >= request.time.created { set(record.requestID, server: server, state: "interrupted") }
                else if session.outcome == "failed", (session.time?.idle ?? 0) >= request.time.created { set(record.requestID, server: server, state: "failed") }
                else { set(record.requestID, server: server, state: waitingPermission ? "permission" : waitingQuestion ? "question" : "running") }
            }
        }
    }
    static func label(_ state: String) -> String {
        switch state {
        case "sending": return "Envio iniciado · aguardando confirmação"
        case "admitted": return "Admitida pelo notebook"
        case "running": return "Em acompanhamento"
        case "permission": return "Conversa aguarda permissão"
        case "question": return "Conversa aguarda sua resposta"
        case "completed": return "Resposta concluída · consulte resultado"
        case "failed": return "Resposta com erro"
        case "interrupted": return "Interrupção confirmada pelo notebook"
        default: return "Resultado incerto · não reenviar automaticamente"
        }
    }
}
