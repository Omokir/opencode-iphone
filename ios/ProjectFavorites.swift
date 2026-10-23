import Foundation
import CryptoKit
import Combine

@MainActor final class ProjectFavorites: ObservableObject {
    struct Project: Codable, Identifiable {
        let id: UUID
        var name: String
        let directory: String
    }
    @Published private var revision = 0
    private let defaults: UserDefaults
    init(defaults: UserDefaults = .standard) { self.defaults = defaults }
    private func key(_ server: String) -> String {
        "projects." + SHA256.hash(data: Data(server.utf8)).map { String(format: "%02x", $0) }.joined()
    }
    func list(server: String) -> [Project] {
        guard let data = defaults.data(forKey: key(server)), data.count <= 256 * 1024 else { return [] }
        return Array(((try? JSONDecoder().decode([Project].self, from: data)) ?? []).prefix(30))
    }
    func add(server: String, name: String, directory: String) throws {
        var path = directory.trimmingCharacters(in: .whitespacesAndNewlines)
        while path.count > 1 && path.hasSuffix("/") { path.removeLast() }
        guard path.hasPrefix("/"), path.utf8.count <= 4096, !path.contains("\0"), !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, name.count <= 80 else {
            throw PhoneError.message("Informe nome (até 80 caracteres) e pasta absoluta no notebook.")
        }
        var values = list(server: server)
        if let index = values.firstIndex(where: { $0.directory == path }) { values[index].name = name }
        else {
            guard values.count < 30 else { throw PhoneError.message("Limite de 30 projetos favoritos por notebook.") }
            values.append(Project(id: UUID(), name: name, directory: path))
        }
        defaults.set(try JSONEncoder().encode(values), forKey: key(server)); revision &+= 1
    }
    func remove(_ id: UUID, server: String) {
        let values = list(server: server).filter { $0.id != id }
        if let data = try? JSONEncoder().encode(values) { defaults.set(data, forKey: key(server)); revision &+= 1 }
    }
}
