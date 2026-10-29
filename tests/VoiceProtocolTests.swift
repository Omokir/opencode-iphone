import Foundation

@main struct VoiceProtocolTests {
    static func main() throws {
        func event(_ status: String, name: String = "opencode_submit", arguments: String = #"{"task":"Review project"}"#) -> [String: Any] {
            ["type": "response.done", "response": ["status": status, "output": [["type": "function_call", "call_id": "call_1", "name": name, "arguments": arguments]]]]
        }
        precondition(RealtimeProtocol.completedTools(event("completed")).first?.task == "Review project")
        for state in ["cancelled", "incomplete", "failed", "in_progress"] { precondition(RealtimeProtocol.completedTools(event(state)).isEmpty) }
        precondition(RealtimeProtocol.completedTools(["type": "response.function_call_arguments.done", "arguments": #"{"task":"Never execute incomplete event"}"#]).isEmpty)
        precondition(RealtimeProtocol.completedTools(event("completed", name: "shell_exec")).isEmpty)
        for args in [#"{"task":"go","sessionID":"other"}"#, #"{"task":""}"#, "not json", #"{"url":"https://evil.invalid"}"#] {
            precondition(RealtimeProtocol.completedTools(event("completed", arguments: args)).isEmpty)
        }
        precondition(RealtimeProtocol.completedTools(event("completed", name: "opencode_status", arguments: "{}")).count == 1)
        precondition(RealtimeProtocol.completedTools(event("completed", name: "opencode_status", arguments: #"{"path":"/api/config"}"#)).isEmpty)
        let session = RealtimeProtocol.configuration(model: "gpt-realtime", voice: "marin")
        precondition(session["type"] as? String == "realtime")
        precondition((session["tools"] as? [[String: Any]])?.count == 5)
        precondition(RealtimeProtocol.completedTools(event("completed", name: "opencode_capabilities", arguments: "{}")).count == 1)
        precondition(RealtimeProtocol.completedTools(event("completed", name: "opencode_cancel", arguments: #"{"jobID":"job_abc"}"#)).first?.jobID == "job_abc")
        precondition(RealtimeProtocol.completedTools(event("completed", name: "opencode_update", arguments: #"{"jobID":"job_abc","task":"Read only"}"#)).first?.task == "Read only")
        precondition(RealtimeProtocol.completedTools(event("completed", name: "opencode_cancel", arguments: #"{"jobID":"job_../../secret"}"#)).isEmpty)
        precondition(RealtimeProtocol.completedTools(event("completed", name: "opencode_update", arguments: #"{"jobID":"job_abc","task":"Read only","permissions":"allow"}"#)).isEmpty)
        let completedItem: [String: Any] = ["type": "response.output_item.done", "item": ["type": "function_call", "status": "completed", "call_id": "call_early", "name": "opencode_submit", "arguments": #"{"task":"Inspect fixture"}"#]]
        precondition(RealtimeProtocol.completedTools(completedItem).first?.task == "Inspect fixture")
        precondition(!(session["instructions"] as! String).contains("sempre aguarde confirmação visual"))
        let samples: [Float] = [-2, -1, 0, 1, 2, .nan, .infinity]
        let data = samples.withUnsafeBufferPointer { RealtimePCM.encode($0) }
        let decoded = RealtimePCM.decode(data)!
        precondition(decoded.count == samples.count && decoded[0] == -1 && decoded[2] == 0 && decoded[3] > 0.99 && decoded[5] == 0 && decoded[6] == 0)
        precondition(RealtimePCM.decode(Data([1])) == nil)
        precondition(RealtimePCM.decode(Data(repeating: 0, count: 256 * 1024 + 2)) == nil)
        let report = VoiceResponseReport(event: ["response": ["status": "incomplete", "status_details": ["reason": "max_output_tokens", "error": ["message": "must-not-leak", "code": "private-key-placeholder"]]]])
        precondition(report.state == "incomplete" && report.reason == "max_output_tokens" && report.code == "other")
        let unsafe = VoiceResponseReport(event: ["response": ["status": "must-not-leak", "status_details": ["reason": "must-not-leak"]]])
        precondition(unsafe.state == "unknown" && unsafe.reason == "none")
        precondition(VoiceResponseReport.safeCode("insufficient_quota") == "insufficient_quota")
        print("PASS: voice response diagnostics preserve known failure reasons without raw error/message/key disclosure")
        print("PASS: Realtime ignores cancelled/incomplete tool calls, rejects arbitrary tools/paths, preserves PCM16 bounds/endian and clips unsafe samples")
    }
}
