import Foundation

@main struct MCPRegistryTests {
    static func main() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("kzl-registry-fixture-" + UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let fence = MCPRegistryFence(root: root)
        let host = "https://fixture.ts.net:8443"
        precondition(!fence.pending(host))
        precondition(fence.begin(host))
        precondition(!fence.begin(host), "Duplicate write must be fenced")
        precondition(MCPRegistryFence(root: root).pending(host), "Pending survives new store instance")
        precondition(!fence.pending("https://other.ts.net:8443"), "Computers must be isolated")
        let files = try FileManager.default.contentsOfDirectory(at: root, includingPropertiesForKeys: nil)
        precondition(files.count == 1 && !files[0].lastPathComponent.contains("fixture.ts.net"))
        let marker = try Data(contentsOf: files[0])
        let permissions = try FileManager.default.attributesOfItem(atPath: files[0].path)[.posixPermissions] as? NSNumber
        precondition(marker == Data([1]))
        precondition(permissions?.intValue == 0o600)
        fence.clearAfterAcknowledgement(host)
        precondition(!fence.pending(host))

        let remote = try MCPRegistry.Configuration.parse("{\"type\":\"remote\",\"url\":\"https://example.com/mcp\"}")
        precondition(remote.type == "remote")
        let local = try MCPRegistry.Configuration.parse("{\"type\":\"local\",\"command\":[\"fixture\"],\"environment\":{\"API_KEY\":\"{env:API_KEY}\"}}")
        precondition(local.command == ["fixture"])
        let invalid = [
            "{\"type\":\"remote\",\"url\":\"https://user:secret@example.com/mcp\"}",
            "{\"type\":\"remote\",\"url\":\"https://example.com/mcp?token=secret\"}",
            "{\"type\":\"remote\",\"url\":\"http://example.com/mcp\"}",
            "{\"type\":\"remote\",\"url\":\"https://example.com/mcp\",\"headers\":{\"Authorization\":\"secret\"}}",
            "{\"type\":\"local\",\"command\":\"sh -c fixture\"}",
            "{\"type\":\"local\",\"command\":[\"fixture\"],\"environment\":{\"API_KEY\":\"literal-secret\"}}"
        ]
        for text in invalid {
            do { _ = try MCPRegistry.Configuration.parse(text); preconditionFailure("Unsafe configuration accepted") }
            catch { /* expected */ }
        }
        let connection = UUID()
        let grant = MCPRegistryMutation(revision: 7, operation: "grant", name: "docs", directory: "/client/a",
            connectionID: connection, server: host, config: remote)
        precondition(grant.body["directory"] as? String == "/client/a")
        precondition(grant.body["revision"] as? Int == 7)
        precondition(grant.body["config"] == nil, "Grant must not replace configuration")
        let add = MCPRegistryMutation(revision: 8, operation: "add", name: "docs", directory: "/client/a",
            connectionID: connection, server: host, config: remote)
        precondition(add.body["directory"] == nil, "Global registration grants no project")
        precondition((add.body["config"] as? [String: Any])?["type"] as? String == "remote")
        let wire = Data("{\"registry\":{\"version\":1,\"revision\":9,\"servers\":{}},\"runtimeConfirmed\":false}".utf8)
        let response = try JSONDecoder().decode(MCPRegistryResponse.self, from: wire)
        precondition(response.registry.revision == 9 && !response.runtimeConfirmed)
        print("PASS: registry parsing, wire contract, frozen mutations, per-computer pending persistence and explicit acknowledgement")
    }
}
