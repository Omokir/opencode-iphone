import AVFoundation
import Foundation

/// Native mono PCM16/24kHz transport. Input converter lives on input callback;
/// playback is admitted on main actor and bounded to 20 seconds queued audio.
final class VoiceAudio: @unchecked Sendable {
    private let engine = AVAudioEngine()
    private let player = AVAudioPlayerNode()
    private let lock = NSLock()
    private var muted = false
    private var epoch: UInt64 = 0
    private var tap = false
    private var outputGeneration = 0
    private var scheduled: Int64 = 0
    private var played: Int64 = 0
    private var playedLifetime: Int64 = 0
    private var spans: [(id: String, start: Int64, end: Int64)] = []
    private var microphoneCallbacks = 0
    private var conversionErrors = 0
    private let format = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: 24000, channels: 1, interleaved: false)!
    var hasPendingAudio: Bool { scheduled > played }
    var diagnostics: String {
        lock.lock(); let callbacks = microphoneCallbacks; let failures = conversionErrors; lock.unlock()
        let session = AVAudioSession.sharedInstance()
        let types = session.currentRoute.outputs.map { $0.portType.rawValue }.joined(separator: ",")
        return "Saída: \(types.isEmpty ? "nenhuma" : types) · volume do sistema: \(Int(session.outputVolume * 100))%\nEngine: \(engine.isRunning ? "ativo" : "parado") · player: \(player.isPlaying ? "ativo" : "parado")\nCallbacks de microfone: \(callbacks) · erros de conversão: \(failures)\nFrames agendados: \(scheduled) · reprodução confirmada pelo iOS: \(played)\nFrames reproduzidos acumulados: \(playedLifetime)\nMixer: \(Int(engine.mainMixerNode.outputVolume * 100))% · player: \(Int(player.volume * 100))%"
    }
    func setMuted(_ value: Bool) { lock.lock(); muted = value; epoch &+= 1; lock.unlock() }
    func current(_ value: UInt64) -> Bool { lock.lock(); defer { lock.unlock() }; return !muted && value == epoch }
    func start(input: @escaping @Sendable (Data, UInt64) -> Void) throws {
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.playAndRecord, mode: .voiceChat, options: [.defaultToSpeaker, .allowBluetooth])
        try session.setActive(true)
        let node = engine.inputNode
        try node.setVoiceProcessingEnabled(true)
        let source = node.outputFormat(forBus: 0)
        guard source.channelCount > 0, source.sampleRate > 0, let converter = AVAudioConverter(from: source, to: format) else { throw PhoneError.message("Microfone/formato de áudio indisponível.") }
        engine.attach(player); engine.connect(player, to: engine.mainMixerNode, format: format)
        node.installTap(onBus: 0, bufferSize: 1024, format: source) { [weak self] buffer, _ in
            guard let self else { return }
            self.lock.lock(); self.microphoneCallbacks += 1; let silent = self.muted; let epoch = self.epoch; self.lock.unlock()
            guard !silent else { return }
            let count = AVAudioFrameCount(ceil(Double(buffer.frameLength) * 24000 / source.sampleRate) + 64)
            guard let output = AVAudioPCMBuffer(pcmFormat: self.format, frameCapacity: count) else { return }
            var supplied = false
            var error: NSError?
            let status = converter.convert(to: output, error: &error) { _, state in
                if supplied { state.pointee = .noDataNow; return nil }
                supplied = true; state.pointee = .haveData; return buffer
            }
            guard status != .error, error == nil, let samples = output.floatChannelData?[0], output.frameLength > 0 else {
                if status == .error || error != nil { self.lock.lock(); self.conversionErrors += 1; self.lock.unlock() }
                return
            }
            let data = RealtimePCM.encode(UnsafeBufferPointer(start: samples, count: Int(output.frameLength)))
            input(data, epoch)
        }
        tap = true
        engine.prepare(); try engine.start(); player.play()
    }
    func enqueue(_ data: Data, item: String) throws {
        guard let decoded = RealtimePCM.decode(data) else { throw PhoneError.message("Bloco de voz inválido.") }
        guard !decoded.isEmpty else { return }
        let frames = Int64(data.count / 2)
        guard scheduled - played + frames <= 24000 * 20 else { throw PhoneError.message("Áudio acumulou além do limite. Chamada encerrada para evitar atraso/custo.") }
        if spans.last?.id != item {
            spans.removeAll { $0.end <= played }
            guard spans.count < 32 else { throw PhoneError.message("Fila de voz excedeu limite.") }
            spans.append((item, scheduled, scheduled))
        }
        guard let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(frames)), let values = buffer.floatChannelData?[0] else { return }
        buffer.frameLength = AVAudioFrameCount(frames)
        for (index, value) in decoded.enumerated() { values[index] = value }
        scheduled += frames; spans[spans.count - 1].end = scheduled
        let generation = outputGeneration
        player.scheduleBuffer(buffer, completionCallbackType: .dataPlayedBack) { [weak self] _ in
            DispatchQueue.main.async {
                guard let self, self.outputGeneration == generation else { return }
                let confirmed = min(frames, self.scheduled - self.played)
                self.played += confirmed; self.playedLifetime += confirmed
            }
        }
        if !player.isPlaying { player.play() }
    }
    func interrupt() -> [(String, Int)] {
        // Conservative lower bound: only fully played buffers count as heard.
        let cuts = spans.filter { $0.end > played }.map { ($0.id, Int(max(0, min(played, $0.end) - $0.start) * 1000 / 24000)) }
        outputGeneration &+= 1; player.stop(); scheduled = 0; played = 0; spans = []
        if engine.isRunning { player.play() }
        return cuts
    }
    func stop() {
        setMuted(true); outputGeneration &+= 1
        if tap { engine.inputNode.removeTap(onBus: 0); tap = false }
        player.stop(); engine.stop(); spans = []; scheduled = 0; played = 0
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }
}
