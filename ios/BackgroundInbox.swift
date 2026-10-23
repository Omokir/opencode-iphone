import Foundation
import UIKit
import Combine

/// All mutable state is accessed on the main queue, including URLSession delegates.
/// Background completion NEVER removes an original or treats a receipt as verification.
final class BackgroundInbox: NSObject, ObservableObject, URLSessionDataDelegate, @unchecked Sendable {
    static let identifier = "com.omokir.opencodepocket.inbox.background.v1"
    static let shared = BackgroundInbox()
    struct Job: Codable, Identifiable {
        let id: UUID
        let serverKey: String
        let name: String
        let path: String
        let size: Int64
        let sha256: String
        var state: String
        var sent: Int64
        var taskID: Int?
    }
    @Published private(set) var jobs: [Job] = []
    private var responses: [Int: Data] = [:]
    private var completion: (() -> Void)?
    private static var root: URL { FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("BackgroundInbox", isDirectory: true) }
    private static var manifest: URL { root.appendingPathComponent("jobs.json") }
    private static func stageURL(_ id: UUID) -> URL { root.appendingPathComponent(id.uuidString.lowercased() + ".body") }
    private lazy var session: URLSession = {
        let config = URLSessionConfiguration.background(withIdentifier: Self.identifier)
        config.isDiscretionary = false
        config.sessionSendsLaunchEvents = true
        config.waitsForConnectivity = true
        config.httpShouldSetCookies = false
        config.timeoutIntervalForResource = 24 * 3600
        return URLSession(configuration: config, delegate: self, delegateQueue: .main)
    }()
    override init() {
        super.init()
        if let data = try? Data(contentsOf: Self.manifest), data.count <= 1024 * 1024 {
            jobs = Array(((try? JSONDecoder().decode([Job].self, from: data)) ?? []).prefix(100))
        }
    }
    private func save() throws {
        try FileManager.default.createDirectory(at: Self.root, withIntermediateDirectories: true, attributes: [.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication])
        var values = URLResourceValues(); values.isExcludedFromBackup = true
        var root = Self.root; try root.setResourceValues(values)
        try JSONEncoder().encode(jobs).write(to: Self.manifest, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
    }
    func reconnect(completion: (() -> Void)? = nil) {
        if let completion { self.completion = completion }
        let known = Set(jobs.map(\.id))
        session.getAllTasks { tasks in
            DispatchQueue.main.async {
                let active = Set(tasks.compactMap { $0.taskDescription })
                let enabledServer = UserDefaults.standard.string(forKey: "inbox.enabledServer") ?? ""
                let authorized = UserDefaults.standard.bool(forKey: "inbox.background") && !enabledServer.isEmpty
                    && UserDefaults.standard.string(forKey: "server") == enabledServer && Vault.read() != nil
                for task in tasks {
                    if !authorized || task.state == .suspended || !self.jobs.contains(where: { $0.id.uuidString.lowercased() == task.taskDescription && $0.taskID == task.taskIdentifier && $0.serverKey == HistoryCache.key(enabledServer) }) { task.cancel() }
                }
                for index in self.jobs.indices where known.contains(self.jobs[index].id) && ["queued", "sending"].contains(self.jobs[index].state) && !active.contains(self.jobs[index].id.uuidString.lowercased()) {
                    self.jobs[index].state = "uncertain"
                }
                if !self.jobs.isEmpty { try? self.save() }
            }
        }
    }
    func active(server: String) -> Job? {
        jobs.first { $0.serverKey == HistoryCache.key(server) && ["queued", "sending"].contains($0.state) }
    }
    @MainActor func enqueue(_ api: API, file: StagedUpload, path: String, permitted: @MainActor () -> Bool) async throws {
        guard jobs.count < 100 || jobs.contains(where: { $0.id == file.id }) else { throw TransferFailure.message("Histórico de segundo plano cheio. Limpe registros encerrados no painel.") }
        if let existing = jobs.first(where: { $0.id == file.id }), ["queued", "sending"].contains(existing.state) { return }
        let server = api.server
        let tasks: [URLSessionTask] = await withCheckedContinuation { continuation in session.getAllTasks { continuation.resume(returning: $0) } }
        guard !tasks.contains(where: { $0.taskDescription == file.id.uuidString.lowercased() }) else { return }
        let copy = try await Task.detached(priority: .utility) { try PrivateTransferFiles.stage(file.url) }.value
        defer { try? FileManager.default.removeItem(at: copy.url) }
        guard copy.sha256 == file.sha256, copy.size == file.size else { throw TransferFailure.message("Arquivo mudou ao preparar segundo plano. Original preservado.") }
        try Task.checkCancellation()
        guard api.connected, api.server == server, permitted() else { throw CancellationError() }
        try save()
        let staged = Self.stageURL(file.id)
        if FileManager.default.fileExists(atPath: staged.path) { try FileManager.default.removeItem(at: staged) }
        try FileManager.default.copyItem(at: copy.url, to: staged)
        try FileManager.default.setAttributes([.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication], ofItemAtPath: staged.path)
        var request = try api.makeRequest("/phone/inbox/upload?path=" + API.escape(path), method: "POST")
        request.timeoutInterval = 3600
        request.setValue("application/octet-stream", forHTTPHeaderField: "Content-Type")
        request.setValue(file.id.uuidString, forHTTPHeaderField: "X-Upload-ID")
        request.setValue(file.sha256, forHTTPHeaderField: "X-Content-SHA256")
        let job = Job(id: file.id, serverKey: HistoryCache.key(server), name: file.name, path: path, size: file.size, sha256: file.sha256, state: "queued", sent: 0, taskID: nil)
        jobs.removeAll { $0.id == file.id }; jobs.append(job)
        try save() // Persist identity BEFORE the OS can admit the upload.
        let task = session.uploadTask(with: request, fromFile: staged)
        task.taskDescription = file.id.uuidString.lowercased()
        if let index = jobs.firstIndex(where: { $0.id == file.id }) { jobs[index].taskID = task.taskIdentifier }
        do { try save() } catch { task.cancel(); throw error }
        task.resume()
    }
    func cancelAll() {
        session.getAllTasks { tasks in tasks.forEach { $0.cancel() } }
        for index in jobs.indices where ["queued", "sending"].contains(jobs[index].state) { jobs[index].state = "cancelled" }
        try? save()
    }
    @MainActor func clearFinished() async {
        let tasks: [URLSessionTask] = await withCheckedContinuation { continuation in session.getAllTasks { continuation.resume(returning: $0) } }
        let activeIDs = Set(tasks.compactMap(\.taskDescription))
        let finished = jobs.filter { !["queued", "sending"].contains($0.state) && !activeIDs.contains($0.id.uuidString.lowercased()) }
        for job in finished { try? FileManager.default.removeItem(at: Self.stageURL(job.id)) }
        let ids = Set(finished.map(\.id)); jobs.removeAll { ids.contains($0.id) }
        try? save()
    }
    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
        let old = responses[dataTask.taskIdentifier] ?? Data()
        guard old.count + data.count <= 16384 else { dataTask.cancel(); return }
        responses[dataTask.taskIdentifier] = old + data
    }
    func urlSession(_ session: URLSession, task: URLSessionTask, didSendBodyData bytesSent: Int64,
                    totalBytesSent: Int64, totalBytesExpectedToSend: Int64) {
        guard let index = jobs.firstIndex(where: { $0.id.uuidString.lowercased() == task.taskDescription && $0.taskID == task.taskIdentifier }) else { return }
        jobs[index].state = "sending"; jobs[index].sent = min(totalBytesSent, jobs[index].size)
    }
    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        let data = responses.removeValue(forKey: task.taskIdentifier) ?? Data()
        guard let index = jobs.firstIndex(where: { $0.id.uuidString.lowercased() == task.taskDescription && $0.taskID == task.taskIdentifier }) else { return }
        let job = jobs[index]
        let receipt = try? JSONDecoder().decode(UploadReceipt.self, from: data)
        let accepted = error == nil && (task.response as? HTTPURLResponse)?.statusCode == 200
            && receipt?.matches(id: job.id, path: job.path, size: job.size, sha256: job.sha256) == true
        jobs[index].state = accepted ? "uploaded" : "uncertain"
        if accepted { jobs[index].sent = job.size }
        try? save()
        // Own immutable staging copy only; original belongs to InboxSync foreground verification.
        try? FileManager.default.removeItem(at: Self.stageURL(job.id))
        if accepted {
            Task { @MainActor in PocketNotifications.shared.post(key: "background-upload|\(job.id)", title: "Upload recebido pelo notebook", body: "Abra Pocket para verificar arquivo. Original ainda preservado no iPhone.") }
        }
    }
    func urlSessionDidFinishEvents(forBackgroundURLSession session: URLSession) {
        let handler = completion; completion = nil
        DispatchQueue.main.async { handler?() }
    }
}

final class PocketAppDelegate: NSObject, UIApplicationDelegate {
    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        BackgroundInbox.shared.reconnect()
        return true
    }
    func application(_ application: UIApplication, handleEventsForBackgroundURLSession identifier: String, completionHandler: @escaping () -> Void) {
        guard identifier == BackgroundInbox.identifier else { completionHandler(); return }
        BackgroundInbox.shared.reconnect(completion: completionHandler)
    }
}
