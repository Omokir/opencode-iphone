#if SNAPSHOT
// Compiled only into simulator smoke builds. Never included in the device IPA.
import Foundation
import SwiftUI

@MainActor enum Snapshot {
    static var object: [String: Any] = [
        "id": "ses_demo", "title": "Controle do meu iPhone", "agent": "build",
        "metadata": ["phoneControl": true],
        "time": ["created": 1, "updated": 300, "idle": 300], "outcome": "succeeded",
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
    static let question = try! JSONDecoder().decode(QuestionForm.self, from: Data(#"{"id":"form_demo","title":"Como você quer continuar?","fields":[{"key":"direction","type":"string","title":"Próxima etapa","required":true,"custom":true,"options":[{"value":"plan","label":"Só planejar","description":"Revisar proposta antes de alterar arquivos."},{"value":"build","label":"Implementar","description":"Seguir com alterações aprovadas."}]}]}"#.utf8))
    static func response(_ path: String, method: String, body: [String: Any]?) throws -> Data {
        let route = String(path.split(separator: "?")[0])
        var result: [String: Any] = [:]
        if method != "GET" {
            if route == "/phone/control/start" { result = ["data": object] }
            else if route == "/phone/control/stop" { result = ["enabled": false, "warnings": []] }
            else if route.hasSuffix("/agent") { object["agent"] = body?["agent"] }
            else if route.hasSuffix("/model") { object["model"] = body?["model"] }
            else if method == "PATCH" { object["title"] = body?["title"] }
            else if route.hasSuffix("/prompt") { result = ["data": ["id": "input_demo"]] }
        } else if route == "/phone/catalog" { result = catalog }
        else if route == "/phone/control/status" {
            result = ["configured": true, "enabled": true, "expiresAt": Date().timeIntervalSince1970 + 600,
                      "sessionID": "ses_demo", "device": ["connected": true, "agentInstalled": true, "name": "Meu iPhone"],
                      "running": true, "pending": 1, "activity": "Aguardando sua confirmação", "ready": true]
        }
        else if route == "/phone/codex/usage" {
            result = ["available": true, "source": "Codex CLI no notebook", "checkedAt": Date().timeIntervalSince1970,
                      "accountLabel": "u***@example.invalid", "plan": "plus", "weekly": ["usedPercent": 36, "windowMinutes": 10080, "resetsAt": Date().timeIntervalSince1970 + 172800]]
        }
        else if route == "/phone/status" { result = ["awake": true, "battery": ["available": true, "percentage": 46, "charging": true, "onAC": true, "state": "Charging"]] }
        else if route == "/api/session" { result = ["data": [object]] }
        else if route.hasSuffix("/message") {
            result = ["data": [
                ["id": "msg_1", "type": "user", "text": "Analise projeto e proponha plano antes de alterar arquivos.", "time": ["created": 1]],
                ["id": "msg_2", "type": "assistant", "time": ["created": 2, "completed": 3],
                 "content": [["type": "text", "text": "Vou abrir Ajustes e aguardar sua próxima instrução. Confirme abertura abaixo."],
                             ["type": "tool", "id": "call_demo", "name": "iphone_mobile_launch_app",
                              "state": ["status": "running", "input": ["device": "local-device", "packageName": "com.apple.Preferences"]]]]],
                ["id": "msg_3", "type": "assistant", "time": ["created": 4, "completed": 5], "content": [],
                 "error": ["type": "provider.auth", "message": "Exemplo: chave do provedor expirou. Selecione outro modelo nos ajustes."]]
            ]]
        } else if route.hasSuffix("/form") { result = ["data": []] }
        else if route.hasSuffix("/permission") {
            result = ["data": [["id": "per_demo", "action": "iphone_mobile_launch_app", "resources": ["*"],
                                "message": "Abrir Ajustes no iPhone", "source": ["id": "call_demo", "messageID": "msg_2"]]]]
        }
        else { result = ["data": object] }
        return try JSONSerialization.data(withJSONObject: result)
    }
}

struct SnapshotRoot: View {
    @State private var session = Snapshot.session
    var body: some View {
        let arguments = ProcessInfo.processInfo.arguments
        if arguments.contains("--snapshot-chat") { NavigationStack { ChatView(session: session) } }
        else if arguments.contains("--snapshot-sessions") { SnapshotConversationsView() }
        else if arguments.contains("--snapshot-control") { PhoneControlView() }
        else if arguments.contains("--snapshot-question") { QuestionFormView(question: Snapshot.question, session: session) { } }
        else if arguments.contains("--snapshot-options") { ChatOptionsView(session: $session) }
        else if arguments.contains("--snapshot-models") {
            let models = try! JSONDecoder().decode(Catalog.self, from: JSONSerialization.data(withJSONObject: Snapshot.catalog)).models
            ModelPickerView(models: models, selection: session.model?.key ?? "") { _ in }
        }
        else { ConnectView() }
    }
}

struct SnapshotConversationsView: View {
    @EnvironmentObject var api: API
    @EnvironmentObject var unread: UnreadStore
    @EnvironmentObject var pins: PinStore
    @State private var prepared = false
    var body: some View {
        if prepared { SessionsView() }
        else {
            ProgressView().task {
                var old = Snapshot.object
                old["time"] = ["created": 1, "updated": 100, "idle": 100]
                let baseline = try! JSONDecoder().decode(Session.self, from: JSONSerialization.data(withJSONObject: old))
                unread.initialize(server: api.server, sessions: [baseline])
                pins.toggle(Snapshot.session.id, server: api.server)
                prepared = true
            }
        }
    }
}
#endif
