import Foundation
import Combine
import CallKit
import AVFoundation
import WebRTC

/// Outgoing call owner, independent of sheets and privacy overlays.
/// No incoming push or automatic paid reconnect.
@MainActor final class KzLCallCoordinator: NSObject, ObservableObject, @preconcurrency CXProviderDelegate {
    static let shared = KzLCallCoordinator()
    let voice = RealtimeVoiceStore()
    private let monitor = ChatStore()
    @Published private(set) var session: Session?
    @Published private(set) var callID: UUID?
    @Published var presented = false
    @Published var error: String?
    @Published var startRequested = false
    @Published private(set) var isStarting = false
    private var requestGeneration = UUID()
    private let provider: CXProvider
    private let controller = CXCallController()
    private var api: API?
    private var observation: AnyCancellable?
    private var startTask: Task<Void, Never>?
    private var activationTimeout: Task<Void, Never>?
    private var reportedConnected = false
    override private init() {
        let config = CXProviderConfiguration(localizedName: "Agente KzL")
        config.supportsVideo = false; config.maximumCallsPerCallGroup = 1; config.maximumCallGroups = 1
        config.supportedHandleTypes = [.generic]; config.includesCallsInRecents = false
        provider = CXProvider(configuration: config)
        super.init()
        provider.setDelegate(self, queue: .main)
        observation = voice.objectWillChange.sink { [weak self] in
            Task { @MainActor in
                guard let self else { return }
                self.objectWillChange.send()
                if self.voice.active, let id = self.callID, !self.reportedConnected {
                    self.reportedConnected = true; self.provider.reportOutgoingCall(with: id, connectedAt: Date())
                }
                if !self.voice.open && (self.reportedConnected || self.voice.error != nil) { self.finishSystemCall() }
            }
        }
    }
    func prepare(api: API, session: Session) {
        guard session.isKzL else { return }
        if callID == nil && !isStarting {
            self.api = api; self.session = session; error = nil; voice.error = nil
            startRequested = true
        }
        presented = true
    }
    func start(api: API, session: Session) async {
        startRequested = false
        guard callID == nil, !isStarting, session.isKzL else { presented = true; return }
        isStarting = true
        let generation = requestGeneration; let connection = api.connectionID
        defer { if requestGeneration == generation { isStarting = false } }
        error = nil
        voice.error = nil
        let allowed = await withCheckedContinuation { continuation in
            AVAudioSession.sharedInstance().requestRecordPermission { continuation.resume(returning: $0) }
        }
        guard requestGeneration == generation, api.connectionID == connection else { return }
        guard allowed, api.connected else { error = "Microfone ou conexão indisponível."; return }
        let id = UUID(); self.api = api; self.session = session; callID = id; reportedConnected = false
        let action = CXStartCallAction(call: id, handle: CXHandle(type: .generic, value: "Agente KzL"))
        do {
            try await controller.request(CXTransaction(action: action))
            guard requestGeneration == generation, api.connectionID == connection, callID == id else {
                provider.reportCall(with: id, endedAt: Date(), reason: .remoteEnded); return
            }
            presented = true
            activationTimeout = Task {
                do { try await Task.sleep(for: .seconds(20)) } catch { return }
                guard callID == id, startTask == nil else { return }
                error = "iOS não ativou áudio da ligação. Toque Ligar para nova tentativa manual."
                end()
            }
        }
        catch {
            guard requestGeneration == generation else { return }
            self.error = "iOS não autorizou iniciar ligação. Nenhuma sessão de voz criada."; finishSystemCall()
        }
    }
    func end() { requestGeneration = UUID(); isStarting = false; startRequested = false; startTask?.cancel(); startTask = nil; voice.end(); finishSystemCall() }
    private func finishSystemCall() {
        guard let id = callID else { return }
        callID = nil; reportedConnected = false; api = nil; startTask = nil
        activationTimeout?.cancel(); activationTimeout = nil
        provider.reportCall(with: id, endedAt: Date(), reason: .remoteEnded)
        RTCAudioSession.sharedInstance().isAudioEnabled = false
        RTCAudioSession.sharedInstance().useManualAudio = false
    }
    func providerDidReset(_ provider: CXProvider) { end() }
    func provider(_ provider: CXProvider, perform action: CXStartCallAction) {
        guard action.callUUID == callID else { action.fail(); return }
        do {
            try AVAudioSession.sharedInstance().setCategory(.playAndRecord, mode: .voiceChat, options: [.allowBluetooth, .defaultToSpeaker])
        } catch { action.fail(); end(); return }
        RTCAudioSession.sharedInstance().useManualAudio = true
        RTCAudioSession.sharedInstance().isAudioEnabled = false
        provider.reportOutgoingCall(with: action.callUUID, startedConnectingAt: Date()); action.fulfill()
    }
    func provider(_ provider: CXProvider, didActivate audioSession: AVAudioSession) {
        activationTimeout?.cancel(); activationTimeout = nil
        RTCAudioSession.sharedInstance().audioSessionDidActivate(audioSession)
        RTCAudioSession.sharedInstance().isAudioEnabled = true
        guard let api, let session, let id = callID, !voice.open, startTask == nil else { return }
        startTask = Task {
            await voice.start(api, session: session, monitor: monitor, systemCall: true)
            if callID == id && !voice.open { finishSystemCall() }
        }
    }
    func provider(_ provider: CXProvider, didDeactivate audioSession: AVAudioSession) {
        RTCAudioSession.sharedInstance().audioSessionDidDeactivate(audioSession)
        RTCAudioSession.sharedInstance().isAudioEnabled = false
    }
    func provider(_ provider: CXProvider, perform action: CXEndCallAction) { end(); action.fulfill() }
    func provider(_ provider: CXProvider, perform action: CXSetMutedCallAction) {
        guard action.callUUID == callID else { action.fail(); return }
        voice.setMuted(action.isMuted); action.fulfill()
    }
    func provider(_ provider: CXProvider, timedOutPerforming action: CXAction) { end(); action.fail() }
}
