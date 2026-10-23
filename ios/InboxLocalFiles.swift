import Foundation
import CryptoKit

enum InboxLocalFiles {
    static func inspect(_ source: URL) throws -> StagedUpload {
        let coordinator = NSFileCoordinator(filePresenter: nil)
        var coordinationError: NSError?
        var result: Result<StagedUpload, Error>?
        coordinator.coordinate(readingItemAt: source, options: .withoutChanges, error: &coordinationError) { url in
            result = Result {
                let before = try url.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey, .contentModificationDateKey])
                guard before.isRegularFile == true, before.isSymbolicLink != true, let size = before.fileSize else {
                    throw PhoneError.message("Somente arquivos regulares podem ser sincronizados.")
                }
                let hash = try digest(url)
                var fresh = url; fresh.removeAllCachedResourceValues()
                let after = try fresh.resourceValues(forKeys: [.fileSizeKey, .contentModificationDateKey])
                guard before.fileSize == after.fileSize, before.contentModificationDate == after.contentModificationDate else {
                    throw PhoneError.message("Arquivo mudou durante leitura. Original preservado.")
                }
                return StagedUpload(id: UUID(), url: source, name: source.lastPathComponent, size: Int64(size), sha256: hash)
            }
        }
        if let coordinationError { throw coordinationError }
        guard let result else { throw PhoneError.message("Leitura coordenada indisponível.") }
        return try result.get()
    }
    static func digest(_ url: URL) throws -> String {
        let file = try FileHandle(forReadingFrom: url)
        defer { try? file.close() }
        var hash = SHA256()
        while let data = try file.read(upToCount: 65536), !data.isEmpty {
            try Task.checkCancellation()
            hash.update(data: data)
        }
        return hash.finalize().map { String(format: "%02x", $0) }.joined()
    }

    // Called only after server content verification, for a direct inbox child.
    static func removeUnchanged(_ source: URL, digest expected: String, size: Int64) throws {
        let initial = try source.resourceValues(forKeys: [.isSymbolicLinkKey])
        guard initial.isSymbolicLink != true else { throw PhoneError.message("Link local preservado; não será removido.") }
        let coordinator = NSFileCoordinator(filePresenter: nil)
        var coordinationError: NSError?
        var removalError: Error?
        coordinator.coordinate(writingItemAt: source, options: .forDeleting, error: &coordinationError) { url in
            do {
                guard url.standardizedFileURL == source.standardizedFileURL else {
                    throw PhoneError.message("Arquivo foi movido durante coordenação. Original preservado.")
                }
                let value = try url.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
                guard value.isRegularFile == true, value.isSymbolicLink != true, Int64(value.fileSize ?? -1) == size,
                      try digest(url) == expected else {
                    throw PhoneError.message("Arquivo local mudou. Nova versão preservada.")
                }
                try FileManager.default.removeItem(at: url)
            } catch { removalError = error }
        }
        if let coordinationError { throw coordinationError }
        if let removalError { throw removalError }
    }
}
