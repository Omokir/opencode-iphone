import Foundation
import CryptoKit

struct RestoredDraft {
    let text: String
    let files: [PendingFile]
    let unconfirmed: Bool
}

@MainActor final class DraftStore {
    private let root: URL
    private struct Record: Codable {
        let text: String
        let unconfirmed: Bool
        let files: [Attachment]
        struct Attachment: Codable { let id: UUID; let name: String; let mime: String }
    }
    init(root: URL? = nil) {
        self.root = root ?? FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("PrivateDrafts", isDirectory: true)
    }
    private func directory(server: String, sessionID: String) -> URL {
        let hash = SHA256.hash(data: Data((server + "|" + sessionID).utf8)).map { String(format: "%02x", $0) }.joined()
        return root.appendingPathComponent(hash, isDirectory: true)
    }
    private func write(_ data: Data, to url: URL) throws {
        #if os(iOS)
        try data.write(to: url, options: [.atomic, .completeFileProtection])
        #else
        try data.write(to: url, options: [.atomic])
        #endif
    }
    func save(server: String, sessionID: String, text: String, files: [PendingFile], unconfirmed: Bool) throws {
        guard text.utf8.count <= 1024 * 1024 else { throw PhoneError.message("Rascunho excede limite de 1 MB de texto.") }
        try PendingFile.validate(files)
        let folder = directory(server: server, sessionID: sessionID)
        let manifest = folder.appendingPathComponent("draft.json")
        if FileManager.default.fileExists(atPath: manifest.path) {
            // Do not replace/clear an existing draft we cannot understand.
            _ = try JSONDecoder().decode(Record.self, from: Data(contentsOf: manifest))
        }
        if text.isEmpty && files.isEmpty {
            if FileManager.default.fileExists(atPath: folder.path) {
                for item in try FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: nil) {
                    if item.lastPathComponent == "draft.json" || item.pathExtension == "blob" && UUID(uuidString: item.deletingPathExtension().lastPathComponent) != nil {
                        try FileManager.default.removeItem(at: item)
                    }
                }
                if try FileManager.default.contentsOfDirectory(atPath: folder.path).isEmpty { try FileManager.default.removeItem(at: folder) }
            }
            return
        }
        #if os(iOS)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true, attributes: [.protectionKey: FileProtectionType.complete])
        #else
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        #endif
        var excluded = URLResourceValues(); excluded.isExcludedFromBackup = true
        var protectedFolder = folder; try protectedFolder.setResourceValues(excluded)
        for file in files {
            let blob = folder.appendingPathComponent(file.id.uuidString + ".blob")
            if !FileManager.default.fileExists(atPath: blob.path) { try write(file.data, to: blob) }
        }
        let record = Record(text: text, unconfirmed: unconfirmed, files: files.map { .init(id: $0.id, name: $0.name, mime: $0.mime) })
        try write(JSONEncoder().encode(record), to: manifest)
        let retained = Set(files.map { $0.id.uuidString + ".blob" })
        for item in try FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: nil) {
            if item.pathExtension == "blob", UUID(uuidString: item.deletingPathExtension().lastPathComponent) != nil, !retained.contains(item.lastPathComponent) {
                try FileManager.default.removeItem(at: item)
            }
        }
    }
    func load(server: String, sessionID: String) throws -> RestoredDraft? {
        let folder = directory(server: server, sessionID: sessionID)
        let manifest = folder.appendingPathComponent("draft.json")
        guard FileManager.default.fileExists(atPath: manifest.path) else { return nil }
        let record = try JSONDecoder().decode(Record.self, from: Data(contentsOf: manifest))
        guard record.files.count <= 5, record.text.utf8.count <= 1024 * 1024 else { throw PhoneError.message("Rascunho inválido.") }
        let files = try record.files.map { attachment -> PendingFile in
            let blob = folder.appendingPathComponent(attachment.id.uuidString + ".blob")
            let size = try blob.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? Int.max
            guard size <= PendingFile.maxFileBytes else { throw PhoneError.message("Anexo salvo excede limite.") }
            return PendingFile(id: attachment.id, name: attachment.name, mime: attachment.mime, data: try Data(contentsOf: blob))
        }
        try PendingFile.validate(files)
        return RestoredDraft(text: record.text, files: files, unconfirmed: record.unconfirmed)
    }
}
