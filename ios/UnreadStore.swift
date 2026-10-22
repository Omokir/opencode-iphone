import Foundation
import Combine

@MainActor final class UnreadStore: ObservableObject {
    @Published private var state: ReadState
    private let defaults: UserDefaults
    private let key = "opencode.read-state.v1"
    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        state = defaults.data(forKey: key).flatMap { try? JSONDecoder().decode(ReadState.self, from: $0) } ?? ReadState()
    }
    func isUnread(_ session: Session, server: String) -> Bool { state.isUnread(session, server: server) }
    func initialize(server: String, sessions: [Session]) {
        guard state.baselines[server] == nil else { return }
        state.initialize(server: server, sessions: sessions)
        save()
    }
    func markRead(_ session: Session, server: String) {
        guard state.isUnread(session, server: server) else { return }
        state.markRead(session, server: server)
        save()
    }
    private func save() {
        // Only conversation IDs and server completion timestamps, no chat text.
        if let data = try? JSONEncoder().encode(state) { defaults.set(data, forKey: key) }
    }
}
