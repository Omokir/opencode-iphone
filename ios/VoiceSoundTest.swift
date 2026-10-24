import Foundation
import AVFoundation
import Combine

@MainActor final class VoiceSoundTest: ObservableObject {
    @Published private(set) var running = false
    @Published private(set) var result = ""
    private var audio: VoiceAudio?
    private var generation = UUID()
    func run() async {
        guard !running else { return }
        running = true; result = "Preparando teste local…"
        let token = UUID(); generation = token
        do {
            let allowed = await withCheckedContinuation { continuation in AVAudioSession.sharedInstance().requestRecordPermission { continuation.resume(returning: $0) } }
            guard generation == token, !Task.isCancelled else { return }
            guard allowed else { throw PhoneError.message("Autorize microfone nos Ajustes do iOS para testar circuito de chamada.") }
            let io = VoiceAudio(); audio = io
            // Same capture/playback chain as call; microphone bytes are discarded.
            try io.start { _, _ in }
            let samples = (0..<9600).map { index -> Float in
                let envelope = min(1, Double(min(index, 9599-index)) / 480)
                return Float(sin(Double(index) * 2 * .pi * 440 / 24000) * 0.15 * envelope)
            }
            let data = samples.withUnsafeBufferPointer { RealtimePCM.encode($0) }
            try io.enqueue(data, item: "local-tone")
            try await Task.sleep(for: .milliseconds(1200))
            guard generation == token else { return }
            result = "Você ouviu um tom? Nenhuma API foi chamada; microfone descartado localmente.\n" + io.diagnostics
        } catch { if generation == token { result = "Teste local não concluído. Confira permissão/rota de áudio. Nenhuma API foi chamada." } }
        if generation == token { audio?.stop(); audio = nil; running = false }
    }
    func stop() { generation = UUID(); audio?.stop(); audio = nil; running = false }
}
