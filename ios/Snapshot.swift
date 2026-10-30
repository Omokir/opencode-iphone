#if SNAPSHOT
// Compiled only into simulator smoke builds. Never included in the device IPA.
import Foundation
import SwiftUI

@MainActor enum Snapshot {
    static var clean: Bool { ["--snapshot-conversation", "--snapshot-sidebar", "--snapshot-call", "--snapshot-call-active", "--snapshot-live"].contains { ProcessInfo.processInfo.arguments.contains($0) } }
    static var created: [String: [String: Any]] = [:]
    static var object: [String: Any] = {
        var value: [String: Any] = [
        "id": "ses_demo", "title": "Controle do meu iPhone", "agent": "build",
        "metadata": ["phoneControl": true],
        "time": ["created": 1, "updated": 300, "idle": 300], "outcome": "succeeded",
        "location": ["directory": "/workspace/meu-app"],
        "model": ["providerID": "openai", "id": "gpt-6.1-sol-ultrafast"]
        ]
        if clean {
            let screen = ProcessInfo.processInfo.arguments.first(where: { $0.hasPrefix("--snapshot-") }) ?? "design"
            value["id"] = "ses_design_" + screen.replacingOccurrences(of: "--snapshot-", with: "").replacingOccurrences(of: "-", with: "_")
            value["title"] = "Uma ideia, do começo ao fim"
            value["metadata"] = [:] as [String: Bool]
            value["model"] = ["providerID": "openai", "id": "gpt-6.1-terra-fast"]
        }
        return value
    }()
    static var kzlObject: [String: Any] {
        var value = object; value["id"] = "ses_kzl_demo"; value["title"] = "Agente KzL"; value["metadata"] = ["kzlAgent": true]
        return value
    }
    static var kzlSession: Session { try! JSONDecoder().decode(Session.self, from: JSONSerialization.data(withJSONObject: kzlObject)) }
    static var session: Session {
        try! JSONDecoder().decode(Session.self, from: JSONSerialization.data(withJSONObject: object))
    }
    static let catalog: [String: Any] = [
        "agents": [["id": "build", "name": "Build"], ["id": "plan", "name": "Plan"]],
        "models": [
            ["id": "gpt-6.1-terra-fast", "providerID": "openai", "name": "GPT-6.1 Terra Fast",
             "capabilities": ["input": ["text", "image", "pdf"]], "variants": [["id": "high"]], "status": "active"],
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
            if route == "/phone/kzl/ensure" { result = ["data": kzlObject] }
            else if route == "/api/session" {
                var fresh = object; fresh["id"] = "ses_new_demo"; fresh["title"] = "Nova conversa"; fresh["metadata"] = [:] as [String: Bool]
                created["ses_new_demo"] = fresh; result = ["data": fresh]
            }
            else if route == "/phone/session/read-state" { result = ["viewed": [:], "unavailable": []] }
            else if route == "/phone/control/start" { result = ["data": object] }
            else if route == "/phone/control/stop" { result = ["enabled": false, "warnings": []] }
            else if route.hasSuffix("/agent") { object["agent"] = body?["agent"] }
            else if route.hasSuffix("/model") { object["model"] = body?["model"] }
            else if method == "PATCH" { object["title"] = body?["title"] }
            else if route.hasSuffix("/prompt") { result = ["data": ["id": "input_demo"]] }
        } else if route == "/phone/catalog" { result = catalog }
        else if route == "/phone/files/roots" { result = ["roots": [["id": "home", "name": "Pasta pessoal (exemplo)"]], "maxBytes": 67108864] }
        else if route == "/phone/files/context" { result = ["root": "home", "path": "Documents"] }
        else if route == "/phone/files/list" {
            let query = URLComponents(string: "https://fixture.invalid" + path)?.queryItems
            let folder = query?.first { $0.name == "path" }?.value ?? ""
            let file: [String: Any] = ["name": "README.txt", "path": folder.isEmpty ? "README.txt" : folder + "/README.txt", "kind": "file", "size": 18, "modifiedAt": 1000, "version": "fixture-version", "readable": true]
            var entries = [file]
            if folder.isEmpty { entries.insert(["name": "Documents", "path": "Documents", "kind": "directory", "readable": true, "version": "directory-version"], at: 0) }
            result = ["root": "home", "path": folder, "parent": folder.isEmpty ? NSNull() as Any : "" as Any, "entries": entries, "truncated": false]
        }
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
        else if route == "/api/session/active" { result = ["data": [:]] }
        else if route == "/api/session" {
            let query = URLComponents(string: "https://fixture.invalid" + path)?.queryItems?.first { $0.name == "search" }?.value ?? ""
            if query.isEmpty {
                var second = object; second["id"] = "ses_demo_second"; second["title"] = "Revisar a API do projeto"
                var third = object; third["id"] = "ses_demo_third"; third["title"] = "Organizar arquivos do notebook"
                result = ["data": clean ? [object, second, third] : [object]]
            }
            else {
                var found = object
                found["id"] = "ses_search_only"
                found["title"] = "Conversa antiga pesquisável"
                result = ["data": query.lowercased().contains("antiga") ? [found] : []]
            }
        }
        else if route.hasSuffix("/message") {
            if route.contains("ses_new_demo") { result = ["data": []] }
            else if clean {
                result = ["data": [
                    ["id": "msg_1", "type": "user", "text": "Vamos criar uma página para meu projeto? Quero algo simples, sem cara de template.", "time": ["created": 1]],
                    ["id": "msg_2", "type": "assistant", "time": ["created": 2, "completed": 3], "content": [
                        ["type": "text", "text": "Sim. Começaria com uma ideia clara, bastante espaço e uma tipografia que tenha a cara do projeto.\n\n**Minha proposta**\n\n• Uma abertura direta, sem slogans genéricos.\n• Conteúdo organizado em poucas seções.\n• Uma ação principal, fácil de encontrar.\n\nPodemos explorar o visual antes de mexer nos arquivos."],
                        ["type": "tool", "id": "call_demo", "name": "read", "state": ["status": "completed", "detail": "Fixture: estrutura do projeto conferida."]]
                    ]],
                    ["id": "msg_3", "type": "assistant", "time": ["created": 4, "completed": 5], "content": [["type": "text", "text": "Pronto para revisar. Você pode continuar por texto ou abrir o Live desta conversa."]]]
                ]]
            } else {
            result = ["data": [
                ["id": "msg_1", "type": "user", "text": "Analise projeto e proponha plano antes de alterar arquivos.", "time": ["created": 1]],
                ["id": "msg_2", "type": "assistant", "time": ["created": 2, "completed": 3],
                 "content": [["type": "text", "text": "Vou abrir Ajustes e aguardar sua próxima instrução. Confirme abertura abaixo."],
                             ["type": "tool", "id": "call_demo", "name": "iphone_mobile_launch_app",
                              "state": ["status": "running", "input": ["device": "local-device", "packageName": "com.apple.Preferences"]]]]],
                ["id": "msg_3", "type": "assistant", "time": ["created": 4, "completed": 5], "content": [],
                 "error": ["type": "provider.auth", "message": "Exemplo: chave do provedor expirou. Selecione outro modelo nos ajustes."]]
            ]]
            }
        } else if route.hasSuffix("/form") { result = ["data": []] }
        else if route.hasSuffix("/permission") {
            if clean { result = ["data": []] } else {
            result = ["data": [["id": "per_demo", "action": "iphone_mobile_launch_app", "resources": ["*"],
                                 "message": "Abrir Ajustes no iPhone", "source": ["id": "call_demo", "messageID": "msg_2"]]]]
            }
        }
        else if route.hasSuffix("/inbox") { result = ["data": []] }
        else if route == "/phone/kzl/tasks" { result = ["tasks": []] }
        else if route == "/phone/kzl/memory" { result = ["turns": []] }
        else if route == "/api/session/ses_kzl_demo" { result = ["data": kzlObject] }
        else if let id = route.split(separator: "/").last, let value = created[String(id)] { result = ["data": value] }
        else { result = ["data": object] }
        return try JSONSerialization.data(withJSONObject: result)
    }
}

struct SnapshotRoot: View {
    @State private var session = Snapshot.session
    var body: some View {
        let arguments = ProcessInfo.processInfo.arguments
        if arguments.contains("--snapshot-conversation") { NavigationStack { ChatView(session: session, onNewConversation: {}) } }
        else if arguments.contains("--snapshot-sidebar") { SnapshotConversationsView() }
        else if arguments.contains("--snapshot-call") { KzLCallScreen(session: Snapshot.kzlSession) }
        else if arguments.contains("--snapshot-call-active") {
            KzLCallScreen(session: Snapshot.kzlSession).onAppear { KzLCallCoordinator.shared.voice.previewCallState() }
        }
        else if arguments.contains("--snapshot-live") { VoiceCallView(session: session) }
        else if arguments.contains("--snapshot-chat") { NavigationStack { ChatView(session: session) } }
        else if arguments.contains("--snapshot-sessions") { SnapshotConversationsView() }
        else if arguments.contains("--snapshot-search") { SessionsView() }
        else if arguments.contains("--snapshot-control") { PhoneControlView() }
        else if arguments.contains("--snapshot-question") { QuestionFormView(question: Snapshot.question, session: session) { } }
        else if arguments.contains("--snapshot-files") { FileBrowserView() }
        else if arguments.contains("--snapshot-inbox") { InboxSyncView() }
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
        if prepared { SessionsView(showSidebar: true) }
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
