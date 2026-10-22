#if SNAPSHOT
// Compiled only into simulator smoke builds. Never included in the device IPA.
import Foundation
import SwiftUI

@MainActor enum Snapshot {
    static var object: [String: Any] = [
        "id": "ses_demo", "title": "Planejar aplicativo", "agent": "plan",
        "location": ["directory": "/workspace/meu-app"],
        "model": ["providerID": "openai", "id": "gpt-6.1-sol-ultrafast"]
    ]
    static var session: Session {
        try! JSONDecoder().decode(Session.self, from: JSONSerialization.data(withJSONObject: object))
    }
    static let catalog: [String: Any] = [
        "agents": [["id": "build", "name": "Build"], ["id": "plan", "name": "Plan"]],
        "models": [
            ["id": "gpt-6.1-sol-ultrafast", "providerID": "openai", "name": "GPT-6.1 Sol Ultrafast",
             "capabilities": ["input": ["text", "image", "pdf"]], "variants": [["id": "high"]], "status": "active"],
            ["id": "claude-sonnet", "providerID": "anthropic", "name": "Claude Sonnet",
             "capabilities": ["input": ["text", "image", "pdf"]], "variants": [], "status": "active"]
        ]
    ]
    static func response(_ path: String, method: String, body: [String: Any]?) throws -> Data {
        let route = String(path.split(separator: "?")[0])
        var result: [String: Any] = [:]
        if method != "GET" {
            if route.hasSuffix("/agent") { object["agent"] = body?["agent"] }
            else if route.hasSuffix("/model") { object["model"] = body?["model"] }
            else if method == "PATCH" { object["title"] = body?["title"] }
            else if route.hasSuffix("/prompt") { result = ["data": ["id": "input_demo"]] }
        } else if route == "/phone/catalog" { result = catalog }
        else if route == "/phone/status" { result = ["awake": true] }
        else if route == "/api/session" { result = ["data": [object]] }
        else if route.hasSuffix("/message") {
            result = ["data": [
                ["id": "msg_1", "type": "user", "text": "Analise projeto e proponha plano antes de alterar arquivos.", "time": ["created": 1]],
                ["id": "msg_2", "type": "assistant", "time": ["created": 2, "completed": 3],
                 "content": [["type": "text", "text": "Vou começar pela estrutura do projeto.\n\n**Plano**\n1. Verificar telas existentes\n2. Definir alterações\n3. Implementar após sua aprovação"]]],
                ["id": "msg_3", "type": "assistant", "time": ["created": 4, "completed": 5], "content": [],
                 "error": ["type": "provider.auth", "message": "Exemplo: chave do provedor expirou. Selecione outro modelo nos ajustes."]]
            ]]
        } else if route.hasSuffix("/permission") { result = ["data": []] }
        else { result = ["data": object] }
        return try JSONSerialization.data(withJSONObject: result)
    }
}

struct SnapshotRoot: View {
    @State private var session = Snapshot.session
    var body: some View {
        let arguments = ProcessInfo.processInfo.arguments
        if arguments.contains("--snapshot-chat") { NavigationStack { ChatView(session: session) } }
        else if arguments.contains("--snapshot-options") { ChatOptionsView(session: $session) }
        else if arguments.contains("--snapshot-models") {
            let models = try! JSONDecoder().decode(Catalog.self, from: JSONSerialization.data(withJSONObject: Snapshot.catalog)).models
            ModelPickerView(models: models, selection: session.model?.key ?? "") { _ in }
        }
        else { ConnectView() }
    }
}
#endif
