import Foundation

struct VoiceResponseReport: Equatable {
    let state: String
    let reason: String
    let code: String
    init(event: [String: Any]) {
        let response = event["response"] as? [String: Any] ?? [:]
        let detail = response["status_details"] as? [String: Any] ?? [:]
        let error = detail["error"] as? [String: Any] ?? [:]
        let rawState = response["status"] as? String ?? ""
        state = ["completed", "incomplete", "failed", "cancelled"].contains(rawState) ? rawState : "unknown"
        let rawReason = detail["reason"] as? String ?? ""
        reason = ["max_output_tokens", "content_filter", "turn_detected", "client_cancelled"].contains(rawReason) ? rawReason : "none"
        code = Self.safeCode(error["code"] as? String)
    }
    static func safeCode(_ raw: String?) -> String {
        guard let raw else { return "none" }
        return ["invalid_api_key", "insufficient_quota", "rate_limit_exceeded", "invalid_request_error", "conversation_already_has_active_response", "response_cancel_not_active", "model_not_found", "unsupported_parameter"].contains(raw) ? raw : "other"
    }
}

struct VoiceDiagnostics {
    var sentPackets = 0
    var receivedAudio = 0
    var scheduledAudio = 0
    var ignoredAudio = 0
    var malformedAudio = 0
    var speechStarts = 0
    var transcripts = 0
    var response = "none"
    var reason = "none"
    var code = "none"
    var text: String {
        "Microfone: \(sentPackets) blocos enviados\nAPI: \(receivedAudio) blocos de áudio recebidos\nPlayer: \(scheduledAudio) blocos agendados\nDescartados após interrupção: \(ignoredAudio)\nÁudio com formato/campos inválidos: \(malformedAudio)\nInícios de fala detectados: \(speechStarts)\nBlocos de legenda: \(transcripts)\nResposta: \(response) · motivo: \(reason) · código: \(code)"
    }
}
