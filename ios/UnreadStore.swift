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
        let previous = state
        state.initialize(server: server, sessions: sessions)
        let markers = sessions.compactMap { session -> (String, Double)? in
            guard let stamp = session.time?.viewed else { return nil }
            return (session.id, stamp)
        }
        state.synchronize(server: server, markers: Dictionary(markers, uniquingKeysWith: { max($0, $1) }))
        if previous.baselines != state.baselines || previous.viewed != state.viewed { save() }
    }
    func synchronize(server: String, markers: [String: Double]) {
        let previous = state.viewed
        state.synchronize(server: server, markers: markers)
        if previous != state.viewed { save() }
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
