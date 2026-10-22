import Foundation
import UniformTypeIdentifiers
import UIKit

enum FileLoader {
    static func read(_ url: URL) throws -> PendingFile {
        let access = url.startAccessingSecurityScopedResource()
        defer { if access { url.stopAccessingSecurityScopedResource() } }
        let values = try url.resourceValues(forKeys: [.fileSizeKey, .isRegularFileKey, .contentTypeKey])
        guard values.isRegularFile == true else { throw PhoneError.message("Selecione arquivo, não pasta.") }
        guard let size = values.fileSize, size > 0, size <= PendingFile.maxFileBytes else {
            throw PhoneError.message("\(url.lastPathComponent): limite de 4 MB por arquivo.")
        }
        let data = try Data(contentsOf: url)
        let mime: String
        if values.contentType?.conforms(to: .image) == true {
            guard ["image/jpeg", "image/png", "image/gif", "image/webp"].contains(values.contentType?.preferredMIMEType ?? "") else {
                throw PhoneError.message("Para HEIC e outros formatos, use opção Fotos. Ela converte imagem para JPEG.")
            }
            mime = values.contentType!.preferredMIMEType!
        } else if values.contentType?.conforms(to: .pdf) == true { mime = "application/pdf" }
        else if String(data: data, encoding: .utf8) != nil { mime = "text/plain" }
        else { throw PhoneError.message("Envie imagens, PDF ou arquivos de texto/código. Este formato binário ainda não é suportado.") }
        let file = PendingFile(name: url.lastPathComponent, mime: mime, data: data)
        try PendingFile.validate([file])
        return file
    }

    @MainActor static func photo(_ data: Data, index: Int) throws -> PendingFile {
        guard let image = UIImage(data: data), image.size.width > 0, image.size.height > 0 else {
            throw PhoneError.message("Não foi possível abrir foto selecionada.")
        }
        let ratio = min(1, 2048 / max(image.size.width, image.size.height))
        let size = CGSize(width: image.size.width * ratio, height: image.size.height * ratio)
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        format.opaque = true
        let scaled = UIGraphicsImageRenderer(size: size, format: format).image { context in
            UIColor.white.setFill()
            context.fill(CGRect(origin: .zero, size: size))
            image.draw(in: CGRect(origin: .zero, size: size))
        }
        guard let jpeg = scaled.jpegData(compressionQuality: 0.85) else {
            throw PhoneError.message("Não foi possível converter foto.")
        }
        let file = PendingFile(name: "foto-\(index).jpg", mime: "image/jpeg", data: jpeg)
        try PendingFile.validate([file])
        return file
    }
}
