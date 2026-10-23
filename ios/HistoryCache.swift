import Foundation
import CryptoKit

/// Bounded, private, non-authoritative history. Never caches permissions or writes.
enum HistoryCache {
    static var root: URL {
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("HistoryCache", isDirectory: true)
    }
    static func key(_ value: String) -> String {
        SHA256.hash(data: Data(value.utf8)).map { String(format: "%02x", $0) }.joined()
    }
    static func allowed(_ path: String) -> Bool {
        guard let url = URLComponents(string: path), url.queryItems?.contains(where: { ["cursor", "search", "type"].contains($0.name) }) != true else { return false }
        let parts = url.path.split(separator: "/")
        return url.path == "/api/session" || (parts.count == 3 && parts[0] == "api" && parts[1] == "session") ||
            (parts.count == 4 && parts[0] == "api" && parts[1] == "session" && parts[3] == "message")
    }
    static func file(server: String, path: String) -> URL { root.appendingPathComponent(key(server + "|" + path) + ".json") }
    static func read<T: Decodable>(server: String, path: String) -> T? {
        guard allowed(path), let size = try? file(server: server, path: path).resourceValues(forKeys: [.fileSizeKey]).fileSize,
              size <= 4 * 1024 * 1024, let data = try? Data(contentsOf: file(server: server, path: path)) else { return nil }
        return try? JSONDecoder().decode(T.self, from: data)
    }
    static func save(_ data: Data, server: String, path: String) {
        guard allowed(path), data.count <= 4 * 1024 * 1024 else { return }
        if (try? Data(contentsOf: file(server: server, path: path))) == data { return }
        do {
            #if os(iOS)
            try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true, attributes: [.protectionKey: FileProtectionType.complete])
            #else
            try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
            #endif
            var excluded = URLResourceValues(); excluded.isExcludedFromBackup = true
            var folder = root; try folder.setResourceValues(excluded)
            #if os(iOS)
            try data.write(to: file(server: server, path: path), options: [.atomic, .completeFileProtection])
            #else
            try data.write(to: file(server: server, path: path), options: [.atomic])
            #endif
            let files = try FileManager.default.contentsOfDirectory(at: root, includingPropertiesForKeys: [.fileSizeKey, .contentModificationDateKey])
                .filter { $0.pathExtension == "json" }
                .sorted { ((try? $0.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast) > ((try? $1.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast) }
            var bytes = 0
            for (index, file) in files.enumerated() {
                bytes += (try? file.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0
                if index >= 80 || bytes > 32 * 1024 * 1024 { try FileManager.default.removeItem(at: file) }
            }
        } catch { /* Cache failure never loses a draft or blocks a live read. */ }
    }
    static func clear() throws {
        guard FileManager.default.fileExists(atPath: root.path) else { return }
        for item in try FileManager.default.contentsOfDirectory(at: root, includingPropertiesForKeys: nil)
            where item.pathExtension == "json" && item.deletingPathExtension().lastPathComponent.count == 64 {
            try FileManager.default.removeItem(at: item)
        }
    }
}

enum ConnectionAdvice {
    static func describe(_ error: Error) -> String {
        guard let error = error as? URLError else { return error.localizedDescription }
        switch error.code {
        case .cannotFindHost, .dnsLookupFailed: return "DNS do notebook não resolveu. Confira Tailscale/MagicDNS e endereço. Histórico salvo continua disponível."
        case .notConnectedToInternet: return "iPhone sem conexão de rede. Histórico salvo continua disponível."
        case .cannotConnectToHost: return "Notebook não respondeu. Confira se está ligado, Tailscale conectado e gateway ativo."
        case .timedOut: return "Conexão demorou além do prazo. Confira rede, Tailscale e notebook; nenhum envio será repetido automaticamente."
        case .networkConnectionLost: return "Conexão interrompida. Leituras serão retomadas; confira conversa antes de repetir envio."
        default: return "Falha de conexão (\(error.code.rawValue)). Confira rede, Tailscale e notebook."
        }
    }
}
