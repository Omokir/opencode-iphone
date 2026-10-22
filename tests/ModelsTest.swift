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
        print("PASS: native model decoding, pagination, tool status, permissions, message IDs")
    }
}
