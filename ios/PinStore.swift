import Foundation
import Combine

@MainActor final class PinStore: ObservableObject {
    @Published private var state: PinState
    private let defaults: UserDefaults
    private let key = "opencode.pinned-conversations.v1"
    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        state = defaults.data(forKey: key).flatMap { try? JSONDecoder().decode(PinState.self, from: $0) } ?? PinState()
    }
    func ids(server: String) -> [String] { state.ids(server: server) }
    func contains(_ id: String, server: String) -> Bool { state.contains(id, server: server) }
    func toggle(_ id: String, server: String) {
        state.toggle(id, server: server)
        // Preference contains IDs only. No chat text or notebook mutations.
        if let data = try? JSONEncoder().encode(state) { defaults.set(data, forKey: key) }
    }
}
