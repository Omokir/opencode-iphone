import Foundation
import CryptoKit

enum PrivateTransferFiles {
    static let maxBytes = 64 * 1024 * 1024
    static func folder() throws -> URL {
        let directory = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("PrivateTransfers", isDirectory: true).appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true, attributes: [.protectionKey: FileProtectionType.complete])
        return directory
    }
    static func name(_ value: String) throws -> String {
        guard !value.isEmpty, value != ".", value != "..", !value.contains("/"), !value.contains("\\"), !value.contains("\0") else { throw TransferFailure.message("Nome de arquivo inválido.") }
        return value
    }
    static func digest(_ url: URL) throws -> String {
        let file = try FileHandle(forReadingFrom: url)
        defer { try? file.close() }
        var hash = SHA256()
        while let data = try file.read(upToCount: 65536), !data.isEmpty { hash.update(data: data) }
        return hash.finalize().map { String(format: "%02x", $0) }.joined()
    }
    static func stage(_ url: URL) throws -> StagedUpload {
        let access = url.startAccessingSecurityScopedResource()
        defer { if access { url.stopAccessingSecurityScopedResource() } }
        let before = try url.resourceValues(forKeys: [.fileSizeKey, .isRegularFileKey, .contentModificationDateKey])
        guard before.isRegularFile == true, let size = before.fileSize, size <= maxBytes else { throw TransferFailure.message("Selecione arquivo regular de até 64 MB.") }
        let filename = try name(url.lastPathComponent)
        let target = try folder().appendingPathComponent(filename)
        guard FileManager.default.createFile(atPath: target.path, contents: nil, attributes: [.protectionKey: FileProtectionType.complete]) else { throw TransferFailure.message("Não foi possível preparar cópia protegida.") }
        let input = try FileHandle(forReadingFrom: url)
        let output = try FileHandle(forWritingTo: target)
        defer { try? input.close(); try? output.close() }
        var remaining = size
        while remaining > 0 {
            try Task.checkCancellation()
            guard let data = try input.read(upToCount: min(65536, remaining)), !data.isEmpty else { throw TransferFailure.message("Arquivo mudou durante cópia.") }
            try output.write(contentsOf: data)
            remaining -= data.count
        }
        if let extra = try input.read(upToCount: 1), !extra.isEmpty { throw TransferFailure.message("Arquivo cresceu durante cópia. Selecione novamente.") }
        try output.synchronize()
        var refreshedURL = url; refreshedURL.removeAllCachedResourceValues()
        let after = try refreshedURL.resourceValues(forKeys: [.fileSizeKey, .contentModificationDateKey])
        let copied = try target.resourceValues(forKeys: [.fileSizeKey]).fileSize
        guard before.fileSize == after.fileSize, before.contentModificationDate == after.contentModificationDate, copied == size else { throw TransferFailure.message("Arquivo mudou durante cópia. Selecione novamente.") }
        return StagedUpload(id: UUID(), url: target, name: filename, size: Int64(size), sha256: try digest(target))
    }
    static func preview(_ file: PendingFile) throws -> LocalPreview {
        let target = try folder().appendingPathComponent(name(file.name))
        try file.data.write(to: target, options: [.atomic, .completeFileProtection])
        return LocalPreview(url: target, name: file.name)
    }
}

extension API {
    func downloadFile(root: String, file: RemoteFile) async throws -> LocalPreview {
        #if SNAPSHOT
        return try PrivateTransferFiles.preview(PendingFile(name: file.name, mime: "text/plain", data: Data("Arquivo de exemplo".utf8)))
        #else
        guard (file.size ?? 0) <= PrivateTransferFiles.maxBytes else { throw TransferFailure.message("Limite de 64 MB por transferência.") }
        let path = "/phone/files/download?root=" + Self.escape(root) + "&path=" + Self.escape(file.path)
        var request = try makeRequest(path)
        request.timeoutInterval = 300
        if let version = file.version { request.setValue(version, forHTTPHeaderField: "If-Match") }
        let (temporary, response) = try await transport.download(for: request)
        guard let http = response as? HTTPURLResponse else { throw TransferFailure.message("Resposta inválida.") }
        guard http.statusCode == 200 else {
            let data = try Data(contentsOf: temporary)
            let issue = try? JSONDecoder().decode(TransferIssue.self, from: data)
            throw TransferFailure.message(issue?.error ?? "Download falhou: HTTP \(http.statusCode).")
        }
        let destination = try PrivateTransferFiles.folder().appendingPathComponent(PrivateTransferFiles.name(file.name))
        try FileManager.default.moveItem(at: temporary, to: destination)
        try FileManager.default.setAttributes([.protectionKey: FileProtectionType.complete], ofItemAtPath: destination.path)
        let actualSize = try destination.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? Int.max
        guard actualSize <= PrivateTransferFiles.maxBytes, let expected = http.value(forHTTPHeaderField: "X-Content-SHA256"),
              try await Task.detached(priority: .userInitiated, operation: { try PrivateTransferFiles.digest(destination) }).value == expected else {
            try? FileManager.default.removeItem(at: destination)
            throw TransferFailure.message("Checksum/tamanho do download não confere. Arquivo não será aberto.")
        }
        return LocalPreview(url: destination, name: file.name)
        #endif
    }
    func uploadFile(_ file: StagedUpload, root: String, path: String, expected: String?, inbox: Bool = false) async throws -> UploadReceipt {
        #if SNAPSHOT
        return UploadReceipt(uploadID: file.id.uuidString, root: root, path: path, size: file.size, sha256: file.sha256, version: "fixture-version")
        #else
        var request = try makeRequest((inbox ? "/phone/inbox/upload?root=" : "/phone/files/upload?root=") + Self.escape(root) + "&path=" + Self.escape(path), method: "POST")
        request.timeoutInterval = inbox ? 86400 : 300
        request.setValue("application/octet-stream", forHTTPHeaderField: "Content-Type")
        request.setValue(String(file.size), forHTTPHeaderField: "Content-Length")
        request.setValue(file.id.uuidString, forHTTPHeaderField: "X-Upload-ID")
        request.setValue(file.sha256, forHTTPHeaderField: "X-Content-SHA256")
        if let expected { request.setValue(expected, forHTTPHeaderField: "If-Match") }
        else { request.setValue("*", forHTTPHeaderField: "If-None-Match") }
        let (data, response) = try await transport.upload(for: request, fromFile: file.url)
        guard let http = response as? HTTPURLResponse else { throw TransferFailure.message("Envio não confirmado. Confira pasta e recibo antes de tentar novamente.") }
        if http.statusCode == 409 {
            let issue = try? JSONDecoder().decode(TransferIssue.self, from: data)
            if let existing = issue?.existing { throw TransferFailure.conflict(existing, issue?.error ?? "Destino já existe.") }
            throw TransferFailure.message(issue?.error ?? "Destino mudou. Atualize pasta.")
        }
        guard http.statusCode == 200 else {
            let issue = try? JSONDecoder().decode(TransferIssue.self, from: data)
            throw TransferFailure.message(issue?.error ?? "Envio não confirmado. Confira recibo e pasta.")
        }
        let receipt = try JSONDecoder().decode(UploadReceipt.self, from: data)
        guard receipt.uploadID.lowercased() == file.id.uuidString.lowercased(), receipt.sha256 == file.sha256 else { throw TransferFailure.message("Recibo não confere. Verifique pasta antes de novo envio.") }
        return receipt
        #endif
    }
}
