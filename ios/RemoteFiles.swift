import Foundation

struct BrowserRoots: Decodable {
    let roots: [Root]
    let maxBytes: Int
    struct Root: Decodable, Identifiable { let id: String; let name: String }
}
struct BrowserLocation: Decodable { let root: String; let path: String }
struct BrowserListing: Decodable {
    let root: String
    let path: String
    let parent: String?
    let entries: [RemoteFile]
    let truncated: Bool
}
struct RemoteFile: Decodable, Identifiable {
    let name: String
    let path: String
    let kind: String
    let size: Int64?
    let modifiedAt: Double?
    let version: String?
    let readable: Bool
    var id: String { path }
}
struct UploadReceipt: Decodable {
    let uploadID: String
    let root: String
    let path: String
    let size: Int64
    let sha256: String
    let version: String
}
struct TransferIssue: Decodable { let error: String; let existing: RemoteFile? }
enum TransferFailure: LocalizedError {
    case conflict(RemoteFile, String)
    case message(String)
    var errorDescription: String? {
        switch self { case .conflict(_, let message), .message(let message): return message }
    }
}
struct LocalPreview: Identifiable {
    let id = UUID()
    let url: URL
    let name: String
}
struct StagedUpload: Identifiable, Sendable {
    let id: UUID
    let url: URL
    let name: String
    let size: Int64
    let sha256: String
}
