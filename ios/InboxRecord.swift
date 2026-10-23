import Foundation

struct InboxRecord: Codable, Identifiable {
    let id: UUID
    let name: String
    let path: String
    let serverKey: String
    let date: Date
    let removed: Bool
    private static var url: URL {
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("inbox-history.json")
    }
    static func load() -> [InboxRecord] {
        guard let data = try? Data(contentsOf: url), data.count < 1024 * 1024 else { return [] }
        return Array(((try? JSONDecoder().decode([InboxRecord].self, from: data)) ?? []).prefix(100))
    }
    static func save(_ records: [InboxRecord]) {
        do {
            try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
            try JSONEncoder().encode(Array(records.prefix(100))).write(to: url, options: [.atomic, .completeFileProtection])
            var excluded = URLResourceValues(); excluded.isExcludedFromBackup = true
            var file = url; try file.setResourceValues(excluded)
        } catch { /* Transfer verification does not depend on local activity history. */ }
    }
}
