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
    }
}
