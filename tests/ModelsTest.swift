import Foundation

@main
struct ModelsTest {
    static func main() throws {
        let decoder = JSONDecoder()
        let sessionJSON = #"{"data":[{"id":"ses_123","title":"Example","location":{"directory":"/workspace"},"model":{"providerID":"example","id":"model"}}],"cursor":{"next":"older","previous":null}}"#
        let sessions = try decoder.decode(Page<Session>.self, from: Data(sessionJSON.utf8))
        precondition(sessions.data.first?.model?.id == "model")
        precondition(sessions.cursor?.next == "older")
        let messagesJSON = #"{"data":[{"id":"msg_1","type":"user","text":"Hello","time":{"created":1}},{"id":"msg_2","type":"assistant","content":[{"type":"text","text":"Hi"},{"type":"tool","name":"read","state":{"status":"completed","content":[{"type":"text","text":"OK"}]}}],"time":{"created":2,"completed":3}}],"cursor":{"next":null}}"#
        let messages = try decoder.decode(Page<Message>.self, from: Data(messagesJSON.utf8))
        precondition(messages.data.count == 2)
        precondition(messages.data[1].content?[1].state?.status == "completed")
        let permissionsJSON = #"{"data":[{"id":"per_1","action":"shell","resources":["pwd"]}]}"#
        let permissions = try decoder.decode(Page<Permission>.self, from: Data(permissionsJSON.utf8))
        precondition(permissions.data[0].action == "shell")
        for _ in 0..<100 { precondition(RequestID.message().hasPrefix("msg_")) }
        let failureJSON = #"{"id":"msg_failure","type":"assistant","content":[],"time":{"created":2,"completed":3},"error":{"type":"provider.auth","message":"Expired key"}}"#
        let failure = try decoder.decode(Message.self, from: Data(failureJSON.utf8))
        precondition(failure.error?.message == "Expired key")
        let text = PendingFile(name: "code.swift", mime: "text/plain", data: Data("print(1)".utf8))
        try PendingFile.validate([text])
        precondition(text.payload["uri"] as? String == "data:text/plain;base64,cHJpbnQoMSk=")
        precondition(text.category == "text")
        do {
            try PendingFile.validate(Array(repeating: text, count: 6))
            preconditionFailure("Attachment count limit missing")
        } catch { }
        do {
            try PendingFile.validate([PendingFile(name: "large", mime: "text/plain", data: Data(count: PendingFile.maxFileBytes + 1))])
            preconditionFailure("Attachment byte limit missing")
        } catch { }
        let ref = try decoder.decode(Session.Model.self, from: Data(#"{"id":"m","providerID":"p","variant":"high"}"#.utf8))
        precondition(ref.payload["variant"] as? String == "high")
        let catalog = try decoder.decode(Catalog.self, from: Data(#"{"models":[{"id":"m","providerID":"p","name":"Model","capabilities":{"input":["text","image"]},"variants":[{"id":"high"}],"status":"active"}],"agents":[{"id":"plan","name":"Plan"}]}"#.utf8))
        precondition(catalog.models[0].key == "p/m")
        precondition(catalog.agents[0].id == "plan")
        print("PASS: native model decoding, pagination, tool status, permissions, message IDs")
        print("PASS: model variants, catalog, attachment URIs/limits, provider errors")
    }
}
