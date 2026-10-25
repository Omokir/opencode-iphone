import Foundation

@main @MainActor struct WorkflowTests {
    static func main() throws {
        precondition(VoiceBudget.minutes(0) == 5 && VoiceBudget.minutes(999) == 15 && VoiceBudget.minutes(-1) == 1)
        precondition(VoiceBudget.outputTokens(99999) == 512 && VoiceBudget.outputTokens(1024) == 1024)
        var usage = VoiceUsageLedger()
        let event: [String: Any] = ["type": "response.done", "response": ["id": "resp_one", "usage": ["input_tokens": 20, "output_tokens": 10, "input_token_details": ["audio_tokens": 3]]]]
        usage.observe(event); usage.observe(event)
        precondition(usage.input == 20 && usage.output == 10 && usage.responses == 1)
        usage.observe(["type": "response.done", "response": ["id": "resp_two"]])
        precondition(usage.missing == 1 && usage.summary.contains("não reportado"))
        let decoder = JSONDecoder()
        func message(_ id: String, type: String, created: Int, completed: Bool = false) throws -> Message {
            let value: [String: Any] = ["id": id, "type": type, "time": completed ? ["created": created, "completed": created + 1] : ["created": created]]
            return try decoder.decode(Message.self, from: JSONSerialization.data(withJSONObject: value))
        }
        let request = try message("msg_req", type: "user", created: 1)
        let otherUser = try message("msg_other", type: "user", created: 2)
        let reply = try message("msg_answer", type: "assistant", created: 3, completed: true)
        precondition(TaskReplyMatch.find(requestID: request.id, messages: [request, reply]) == .completed(reply.id, false))
        precondition(TaskReplyMatch.find(requestID: request.id, messages: [request, otherUser, reply]) == .ambiguous)
        precondition(TaskReplyMatch.find(requestID: "missing", messages: [reply]) == .waiting)
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("workflow-tests-" + UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: folder) }
        let file = folder.appendingPathComponent("tasks.json")
        let history = TaskHistory(url: file)
        try history.begin(server: "host", sessionID: "ses_test", requestID: "msg_req", text: "Synthetic task")
        history.set("msg_req", server: "host", state: "admitted")
        let recovered = TaskHistory(url: file)
        precondition(recovered.records.first?.state == "uncertain")
        precondition(recovered.records.first?.serverKey != TaskHistory.serverKey("other"))
        recovered.set("msg_req", server: "host", state: "completed", resultID: "msg_answer")
        recovered.set("msg_req", server: "host", state: "uncertain")
        precondition(recovered.records.first?.state == "completed")
        let sha = String(repeating: "a", count: 40)
        let run: [String: Any] = ["status": "completed", "conclusion": "success", "head_sha": sha]
        let artifact: [String: Any] = ["name": "OpenCode-Pocket-iPhone", "expired": false, "workflow_run": ["head_sha": sha]]
        precondition(VerifiedBuildPolicy.ready(run, artifacts: [artifact]))
        precondition(!VerifiedBuildPolicy.ready(run, artifacts: [["name": "OpenCode-Pocket-iPhone", "expired": true]]))
        precondition(!VerifiedBuildPolicy.validSHA("../main"))
        print("PASS: bounded voice budgets, deduplicated reported usage, no cross-user reply matching, uncertain recovery, immutable confirmed results and build/artifact commit binding")
    }
}
