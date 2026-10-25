import Foundation

struct PrivateActivityArchive<T: Codable> {
    let url: URL
    func load() -> [T] {
        guard let size = try? url.resourceValues(forKeys: [.fileSizeKey]).fileSize, size <= 1024 * 1024,
              let data = try? Data(contentsOf: url) else { return [] }
        return (try? JSONDecoder().decode([T].self, from: data)) ?? []
    }
    func save(_ records: [T]) throws {
        let data = try JSONEncoder().encode(records)
        guard data.count <= 1024 * 1024 else { throw PhoneError.message("Histórico local excedeu limite.") }
        #if os(iOS)
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true, attributes: [.protectionKey: FileProtectionType.complete])
        try data.write(to: url, options: [.atomic, .completeFileProtection])
        var values = URLResourceValues(); values.isExcludedFromBackup = true
        var file = url; try file.setResourceValues(values)
        #else
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        try data.write(to: url, options: [.atomic])
        #endif
    }
    static func appURL(_ name: String) -> URL {
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("Activity", isDirectory: true).appendingPathComponent(name)
    }
}
