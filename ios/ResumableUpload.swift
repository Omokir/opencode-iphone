import Foundation
import CryptoKit

extension API {
    private struct ChunkProgress: Decodable { let offset: Int64; let chunkBytes: Int }
    func uploadResumable(_ file: StagedUpload, path: String,
                         permitted: @MainActor () -> Bool,
                         progress: @MainActor (Int64) -> Void) async throws {
        let query = "?path=" + Self.escape(path) + "&id=" + file.id.uuidString.lowercased()
            + "&size=" + String(file.size) + "&sha256=" + file.sha256
        let start: ChunkProgress = try await request("/phone/inbox/progress" + query)
        guard (0...file.size).contains(start.offset), (1...4 * 1024 * 1024).contains(start.chunkBytes) else {
            throw TransferFailure.message("Posição de retomada inválida. Original preservado.")
        }
        var offset = start.offset
        progress(offset)
        repeat {
            try Task.checkCancellation()
            guard permitted() else { throw CancellationError() }
            if offset == file.size && file.size != 0 { break }
            let current = offset
            let count = Int(min(Int64(start.chunkBytes), file.size - offset))
            let chunk = try await Task.detached(priority: .utility) {
                let input = try FileHandle(forReadingFrom: file.url); defer { try? input.close() }
                try input.seek(toOffset: UInt64(current))
                let data = try input.read(upToCount: count) ?? Data()
                guard data.count == count else { throw TransferFailure.message("Arquivo mudou durante envio. Original preservado.") }
                return data
            }.value
            guard permitted() else { throw CancellationError() }
            var request = try makeRequest("/phone/inbox/chunk" + query + "&offset=" + String(offset), method: "POST")
            request.setValue("application/octet-stream", forHTTPHeaderField: "Content-Type")
            request.setValue(SHA256.hash(data: chunk).map { String(format: "%02x", $0) }.joined(), forHTTPHeaderField: "X-Chunk-SHA256")
            request.httpBody = chunk
            request.timeoutInterval = 120
            let (data, response) = try await transport.data(for: request)
            guard (response as? HTTPURLResponse)?.statusCode == 200 else {
                throw TransferFailure.message((try? JSONDecoder().decode(TransferIssue.self, from: data))?.error ?? "Bloco não confirmado. Próxima tentativa consultará posição antes de enviar.")
            }
            let accepted = try JSONDecoder().decode(ChunkProgress.self, from: data)
            guard accepted.offset == offset + Int64(chunk.count) else { throw TransferFailure.message("Posição confirmada não confere.") }
            offset = accepted.offset; progress(offset)
        } while offset < file.size
        guard permitted() else { throw CancellationError() }
        var commit = try makeRequest("/phone/inbox/commit" + query, method: "POST")
        commit.timeoutInterval = 3600
        let (_, response) = try await transport.data(for: commit)
        guard (response as? HTTPURLResponse)?.statusCode == 200 else {
            throw TransferFailure.message("Confirmação final incerta. Arquivo original permanece; verificação precede próxima tentativa.")
        }
        // Caller MUST perform separate actual-content verification before removal.
    }
}
