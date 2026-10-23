import Foundation

@main @MainActor struct StoreTests {
    static func main() throws {
        let suite = "opencode-store-test-" + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let pins = PinStore(defaults: defaults)
        pins.toggle("ses_first", server: "host")
        pins.toggle("ses_second", server: "host")
        let restored = PinStore(defaults: defaults)
        precondition(restored.ids(server: "host") == ["ses_second", "ses_first"])
        restored.toggle("ses_first", server: "host")
        precondition(PinStore(defaults: defaults).ids(server: "host") == ["ses_second"])
        precondition(PinStore(defaults: defaults).ids(server: "other").isEmpty)
        print("PASS: pin persistence, order, unpin and server isolation in UserDefaults")
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("draft-test-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let drafts = DraftStore(root: directory)
        let file = PendingFile(name: "notes.txt", mime: "text/plain", data: Data("private draft fixture".utf8))
        try drafts.save(server: "host", sessionID: "ses_one", text: "Keep this", files: [file], unconfirmed: true)
        let recovered = try DraftStore(root: directory).load(server: "host", sessionID: "ses_one")
        precondition(recovered?.text == "Keep this" && recovered?.files.first?.id == file.id && recovered?.unconfirmed == true)
        precondition(recovered?.files.first?.data == file.data)
        let scoped = try FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil).first!
        let unrelated = scoped.appendingPathComponent("unrelated-note.txt")
        try Data("preserve fixture".utf8).write(to: unrelated)
        let otherDraft = try drafts.load(server: "other", sessionID: "ses_one")
        precondition(otherDraft == nil)
        try drafts.save(server: "host", sessionID: "ses_one", text: "", files: [], unconfirmed: false)
        let cleared = try drafts.load(server: "host", sessionID: "ses_one")
        precondition(cleared == nil)
        precondition(FileManager.default.fileExists(atPath: unrelated.path), "Clear only removes owned draft files")
        try drafts.save(server: "host", sessionID: "ses_one", text: "saved", files: [], unconfirmed: false)
        let manifest = scoped.appendingPathComponent("draft.json")
        try Data("corrupt fixture".utf8).write(to: manifest)
        do {
            try drafts.save(server: "host", sessionID: "ses_one", text: "", files: [], unconfirmed: false)
            preconditionFailure("Unreadable existing draft must not be cleared")
        } catch { }
        let preserved = try String(contentsOf: manifest, encoding: .utf8)
        precondition(preserved == "corrupt fixture")
        print("PASS: draft text/attachment recovery, uncertainty flag, isolation and clear-on-empty")
        let inboxFile = directory.appendingPathComponent("move-fixture.txt")
        try Data("first".utf8).write(to: inboxFile)
        let originalHash = try InboxLocalFiles.digest(inboxFile)
        try Data("other".utf8).write(to: inboxFile)
        do {
            try InboxLocalFiles.removeUnchanged(inboxFile, digest: originalHash, size: 5)
            preconditionFailure("Same-sized modified source must remain")
        } catch { }
        precondition(FileManager.default.fileExists(atPath: inboxFile.path))
        let actualHash = try InboxLocalFiles.digest(inboxFile)
        try InboxLocalFiles.removeUnchanged(inboxFile, digest: actualHash, size: 5)
        precondition(!FileManager.default.fileExists(atPath: inboxFile.path))
        let link = directory.appendingPathComponent("link.txt")
        try FileManager.default.createSymbolicLink(at: link, withDestinationURL: unrelated)
        let unrelatedHash = try InboxLocalFiles.digest(unrelated)
        do {
            try InboxLocalFiles.removeUnchanged(link, digest: unrelatedHash, size: 16)
            preconditionFailure("Symlink must not be removed as synced source")
        } catch { }
        precondition(FileManager.default.fileExists(atPath: unrelated.path))
        print("PASS: inbox cleanup preserves changed files and links; removes only matching content")
    }
}
