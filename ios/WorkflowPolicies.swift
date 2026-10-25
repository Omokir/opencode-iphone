import Foundation

enum VoiceBudget {
    static func minutes(_ value: Int) -> Int { value == 0 ? 5 : max(1, min(15, value)) }
    static func outputTokens(_ value: Int) -> Int { [512, 1024, 2048].contains(value) ? value : 512 }
}

struct VoiceUsageLedger {
    private var seen = Set<String>()
    private(set) var input: Int64 = 0
    private(set) var output: Int64 = 0
    private(set) var audioInput: Int64 = 0
    private(set) var audioOutput: Int64 = 0
    private(set) var missing = 0
    private(set) var responses = 0
    private var audioInputReports = 0
    private var audioOutputReports = 0
    mutating func observe(_ event: [String: Any]) {
        guard event["type"] as? String == "response.done", let response = event["response"] as? [String: Any],
              let id = response["id"] as? String, !id.isEmpty, id.count <= 128, seen.count < 1000, seen.insert(id).inserted else { return }
        responses += 1
        struct Usage: Decodable {
            let input_tokens: Int64?; let output_tokens: Int64?
            let input_token_details: Detail?; let output_token_details: Detail?
            struct Detail: Decodable { let audio_tokens: Int64? }
        }
        guard let raw = response["usage"], let data = try? JSONSerialization.data(withJSONObject: raw),
              let usage = try? JSONDecoder().decode(Usage.self, from: data),
              let incoming = usage.input_tokens, let outgoing = usage.output_tokens,
              (0...1_000_000_000).contains(incoming), (0...1_000_000_000).contains(outgoing) else { missing += 1; return }
        input += incoming; output += outgoing
        if let count = usage.input_token_details?.audio_tokens, (0...incoming).contains(count) { audioInput += count; audioInputReports += 1 }
        if let count = usage.output_token_details?.audio_tokens, (0...outgoing).contains(count) { audioOutput += count; audioOutputReports += 1 }
    }
    var summary: String {
        guard responses > missing else { return "Uso não reportado integralmente pela API (\(responses) respostas observadas). Isso não significa custo zero. Confira faturamento no provedor." }
        return "Uso reportado: \(input) tokens de entrada · \(output) de saída\nÁudio entrada: \(audioInputReports == 0 ? "não reportado" : "\(audioInput) tokens em \(audioInputReports) respostas")\nÁudio saída: \(audioOutputReports == 0 ? "não reportado" : "\(audioOutput) tokens em \(audioOutputReports) respostas")\n\(responses) respostas observadas · \(missing) sem uso completo. Não é fatura nem limite monetário; último turno pode não ter sido reportado."
    }
}

enum TaskReplyMatch {
    enum Result: Equatable { case waiting, ambiguous, completed(String, Bool) }
    static func find(requestID: String, messages: [Message]) -> Result {
        let ordered = messages.sorted { $0.time.created == $1.time.created ? $0.id < $1.id : $0.time.created < $1.time.created }
        guard let index = ordered.firstIndex(where: { $0.id == requestID && $0.type == "user" }) else { return .waiting }
        var candidates: [Message] = []
        var nextUser = false
        for message in ordered.dropFirst(index + 1) {
            if message.type == "user" { nextUser = true; break }
            if message.type == "assistant" { candidates.append(message) }
        }
        if let answer = candidates.last, answer.time.completed != nil { return .completed(answer.id, answer.error != nil) }
        return nextUser ? .ambiguous : .waiting
    }
}

enum VerifiedBuildPolicy {
    static func validSHA(_ value: String) -> Bool { value.count == 40 && value.allSatisfy { $0.isASCII && $0.isHexDigit } }
    static func ready(_ run: [String: Any], artifacts: [[String: Any]]) -> Bool {
        guard run["status"] as? String == "completed", run["conclusion"] as? String == "success",
              let sha = run["head_sha"] as? String, validSHA(sha) else { return false }
        return artifacts.contains { artifact in
            artifact["name"] as? String == "OpenCode-Pocket-iPhone" && artifact["expired"] as? Bool == false
                && (artifact["workflow_run"] as? [String: Any])?["head_sha"] as? String == sha
        }
    }
}
