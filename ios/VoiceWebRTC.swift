import Foundation
import AVFoundation
import WebRTC

/// Media stays in WebRTC; only bounded JSON events cross the data channel.
final class VoiceWebRTC: NSObject, RTCPeerConnectionDelegate, RTCDataChannelDelegate, @unchecked Sendable {
    private static let factory: RTCPeerConnectionFactory = {
        RTCInitializeSSL()
        return RTCPeerConnectionFactory()
    }()
    private var peer: RTCPeerConnection!
    private var channel: RTCDataChannel!
    private var microphone: RTCAudioTrack!
    var onEvent: ((Data) -> Void)?
    var onFailure: (() -> Void)?
    var onReady: (() -> Void)?
    private var closed = false

    override init() {
        super.init()
        let config = RTCConfiguration()
        config.sdpSemantics = .unifiedPlan
        peer = Self.factory.peerConnection(with: config, constraints: RTCMediaConstraints(mandatoryConstraints: nil, optionalConstraints: nil), delegate: self)
        microphone = Self.factory.audioTrack(with: Self.factory.audioSource(with: RTCMediaConstraints(mandatoryConstraints: nil, optionalConstraints: nil)), trackId: "microphone")
        microphone.isEnabled = false
        peer?.add(microphone, streamIds: ["voice"])
        channel = peer?.dataChannel(forLabel: "oai-events", configuration: RTCDataChannelConfiguration())
        channel?.delegate = self
    }
    func offer() async throws -> String {
        guard let peer, channel != nil else { throw PhoneError.message("WebRTC não pôde criar conexão.") }
        do {
            let audio = RTCAudioSession.sharedInstance()
            audio.lockForConfiguration()
            defer { audio.unlockForConfiguration() }
            try audio.setCategory(.playAndRecord, with: [.allowBluetooth, .defaultToSpeaker])
            try audio.setMode(.voiceChat)
            try audio.setActive(true)
        }
        let offer: RTCSessionDescription = try await withCheckedThrowingContinuation { continuation in
            peer.offer(for: RTCMediaConstraints(mandatoryConstraints: ["OfferToReceiveAudio": "true"], optionalConstraints: nil)) { sdp, error in
                if let error { continuation.resume(throwing: error) }
                else if let sdp { continuation.resume(returning: sdp) }
                else { continuation.resume(throwing: PhoneError.message("Oferta WebRTC ausente.")) }
            }
        }
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            peer.setLocalDescription(offer) { error in
                if let error { continuation.resume(throwing: error) } else { continuation.resume() }
            }
        }
        // No trickle signaling endpoint: collect candidates before sending the offer.
        for _ in 0..<100 {
            try Task.checkCancellation()
            guard !closed else { throw CancellationError() }
            if peer.iceGatheringState == .complete { return peer.localDescription?.sdp ?? offer.sdp }
            try await Task.sleep(for: .milliseconds(100))
        }
        throw PhoneError.message("Coleta de rede WebRTC expirou; nenhuma sessão paga criada.")
    }
    func answer(_ sdp: String) async throws {
        guard !closed, let peer, sdp.utf8.count < 256 * 1024 else { throw CancellationError() }
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            peer.setRemoteDescription(RTCSessionDescription(type: .answer, sdp: sdp)) { error in
                if let error { continuation.resume(throwing: error) } else { continuation.resume() }
            }
        }
    }
    func send(_ data: Data) throws {
        guard !closed, channel?.readyState == .open, data.count <= 256 * 1024,
              channel.bufferedAmount < 512 * 1024,
              channel.sendData(RTCDataBuffer(data: data, isBinary: false)) else { throw PhoneError.message("Canal WebRTC indisponível.") }
    }
    func mute(_ value: Bool) { microphone?.isEnabled = !value }
    func speaker() throws {
        let audio = RTCAudioSession.sharedInstance(); audio.lockForConfiguration()
        defer { audio.unlockForConfiguration() }
        try audio.overrideOutputAudioPort(.speaker)
    }
    func close() {
        closed = true; microphone?.isEnabled = false
        onEvent = nil; onFailure = nil; onReady = nil
        channel?.delegate = nil; channel?.close(); peer?.delegate = nil; peer?.close()
        let audio = RTCAudioSession.sharedInstance(); audio.lockForConfiguration()
        try? audio.setActive(false); audio.unlockForConfiguration()
    }
    func dataChannelDidChangeState(_ dataChannel: RTCDataChannel) {
        if dataChannel.readyState == .open { onReady?() }
        if dataChannel.readyState == .closed && !closed { onFailure?() }
    }
    func dataChannel(_ dataChannel: RTCDataChannel, didReceiveMessageWith buffer: RTCDataBuffer) {
        guard !closed, buffer.data.count <= 512 * 1024 else { return }
        onEvent?(buffer.data)
    }
    func peerConnection(_ peerConnection: RTCPeerConnection, didChange stateChanged: RTCSignalingState) {}
    func peerConnection(_ peerConnection: RTCPeerConnection, didAdd stream: RTCMediaStream) {}
    func peerConnection(_ peerConnection: RTCPeerConnection, didRemove stream: RTCMediaStream) {}
    func peerConnectionShouldNegotiate(_ peerConnection: RTCPeerConnection) {}
    func peerConnection(_ peerConnection: RTCPeerConnection, didChange newState: RTCIceConnectionState) {
        if !closed && [.failed, .disconnected, .closed].contains(newState) { onFailure?() }
    }
    func peerConnection(_ peerConnection: RTCPeerConnection, didChange newState: RTCIceGatheringState) {}
    func peerConnection(_ peerConnection: RTCPeerConnection, didGenerate candidate: RTCIceCandidate) {}
    func peerConnection(_ peerConnection: RTCPeerConnection, didRemove candidates: [RTCIceCandidate]) {}
    func peerConnection(_ peerConnection: RTCPeerConnection, didOpen dataChannel: RTCDataChannel) {}
}

struct VoiceBrokerModels: Decodable {
    let data: Catalog
    struct Catalog: Decodable { let models: [Model] }
    struct Model: Decodable { let model: String; let transports: [String]; let available: Bool }
}
struct VoiceBrokerSession: Decodable {
    let data: SessionData
    struct SessionData: Decodable { let transport: Transport }
    struct Transport: Decodable { let type: String; let sdp: String }
}
