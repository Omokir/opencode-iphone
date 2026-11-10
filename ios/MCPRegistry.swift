import Foundation
import CryptoKit

struct MCPRegistryResponse: Decodable {
    let registry: MCPRegistry
    let runtimeConfirmed: Bool
}

struct MCPRegistry: Decodable {
    let version: Int
    let revision: Int
    let servers: [String: Server]

    struct Server: Decodable {
        let config: Configuration
        let projects: [String]
    }

    struct Configuration: Codable {
        let type: String
        let url: String?
        let command: [String]?
        let environment: [String: String]?

        var reviewText: String {
            guard let data = try? JSONEncoder().encode(self), let text = String(data: data, encoding: .utf8) else { return "Configuração indisponível" }
            return text
        }

        static func parse(_ text: String) throws -> Configuration {
            guard text.utf8.count <= 24_000,
                  let raw = text.data(using: .utf8),
                  let object = try JSONSerialization.jsonObject(with: raw) as? [String: Any],
                  let type = object["type"] as? String else { throw MCPRegistryError.invalidConfiguration }
            let allowed = type == "local" ? Set(["type", "command", "environment"]) : Set(["type", "url"])
            guard Set(object.keys).isSubset(of: allowed) else { throw MCPRegistryError.invalidConfiguration }
            let result = try JSONDecoder().decode(Configuration.self, from: raw)
            if type == "remote" {
                guard let url = result.url, url.count <= 2048,
                      let parts = URLComponents(string: url), parts.scheme == "https",
                      let host = parts.host, !host.isEmpty, parts.user == nil, parts.password == nil,
                      parts.query == nil, parts.fragment == nil, parts.url != nil else { throw MCPRegistryError.invalidConfiguration }
            } else if type == "local" {
                guard let command = result.command, (1...64).contains(command.count),
                      command.allSatisfy({ !$0.isEmpty && $0.count <= 4096 && !$0.contains("\0") }),
                      (result.environment?.count ?? 0) <= 64 else { throw MCPRegistryError.invalidConfiguration }
                for (key, value) in result.environment ?? [:] {
                    guard key.range(of: "^[A-Z_][A-Z0-9_]{0,99}$", options: .regularExpression) != nil,
                          value.range(of: "^\\{env:[A-Z_][A-Z0-9_]{0,99}\\}$", options: .regularExpression) != nil else { throw MCPRegistryError.invalidConfiguration }
                }
            } else { throw MCPRegistryError.invalidConfiguration }
            return result
        }
    }
}

enum MCPRegistryError: Error { case invalidConfiguration }

struct MCPRegistryMutation: Identifiable {
    let id = UUID()
    let revision: Int
    let operation: String
    let name: String
    let directory: String
    let connectionID: UUID
    let server: String
    let config: MCPRegistry.Configuration?

    var title: String {
        switch operation {
        case "add": return "Salvar cadastro sem ativar?"
        case "grant": return "Habilitar MCP neste projeto?"
        case "revoke": return "Revogar MCP neste projeto?"
        default: return "Remover cadastro de todos os projetos?"
        }
    }
    var detail: String {
        "Servidor: \(name)\nProjeto: \(directory)\nRevisão: \(revision)\n\(config?.reviewText ?? "")\nHabilitar MCP local executa seu comando no computador. Revogar não cancela ações já admitidas. Ferramentas continuam sujeitas às permissões do OpenCode."
    }
    var body: [String: Any] {
        var result: [String: Any] = ["revision": revision, "operation": operation, "name": name]
        if operation == "grant" || operation == "revoke" { result["directory"] = directory }
        if operation == "add", let config, let data = try? JSONEncoder().encode(config),
           let object = try? JSONSerialization.jsonObject(with: data) { result["config"] = object }
        return result
    }
}

/// Stores only a pending-write bit under an opaque computer hash, never a token,
/// server URL, command, project, configuration or provider credential.
struct MCPRegistryFence {
    let root: URL
    init(root: URL? = nil) {
        self.root = root ?? FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("MCPRegistryFence", isDirectory: true)
    }
    private func file(_ server: String) -> URL {
        root.appendingPathComponent(SHA256.hash(data: Data(server.utf8)).map { String(format: "%02x", $0) }.joined() + ".pending")
    }
    func pending(_ server: String) -> Bool { FileManager.default.fileExists(atPath: file(server).path) }
    func begin(_ server: String) -> Bool {
        guard !pending(server) else { return false }
        do {
            #if os(iOS)
            try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true,
                attributes: [.protectionKey: FileProtectionType.complete])
            let options: Data.WritingOptions = [.withoutOverwriting, .completeFileProtection]
            #else
            try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true,
                attributes: [.posixPermissions: 0o700])
            let options: Data.WritingOptions = [.withoutOverwriting]
            #endif
            var folder = root
            var values = URLResourceValues(); values.isExcludedFromBackup = true
            try folder.setResourceValues(values)
            // Exclusive creation fences concurrent views. Even a partial/empty
            // marker means pending; its existence is intentionally fail-closed.
            try Data([1]).write(to: file(server), options: options)
            try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: file(server).path)
            let handle = try FileHandle(forWritingTo: file(server))
            defer { try? handle.close() }
            try handle.synchronize()
            return true
        } catch { return false }
    }
    func clearAfterAcknowledgement(_ server: String) {
        try? FileManager.default.removeItem(at: file(server))
    }
}
