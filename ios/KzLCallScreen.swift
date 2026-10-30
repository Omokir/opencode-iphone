import SwiftUI

struct KzLCallScreen: View {
    @EnvironmentObject var api: API
    @ObservedObject var call = KzLCallCoordinator.shared
    @ObservedObject var voice = KzLCallCoordinator.shared.voice
    @Environment(\.dismiss) private var dismiss
    @State private var activity = false
    @State private var captions = false
    @State private var consent = false
    @State private var starting = false
    @AppStorage("voice.kzL.billingAcknowledged") private var billingAcknowledged = false
    var session: Session? = nil
    var body: some View {
        ZStack {
            PocketDesign.graphite.ignoresSafeArea()
            VStack(spacing: 20) {
                HStack {
                    Button { call.presented = false; dismiss() } label: { Image(systemName: "arrow.down.right.and.arrow.up.left").frame(width: 44, height: 44) }.accessibilityLabel("Minimizar ligação")
                    Spacer()
                    Button { captions.toggle() } label: { Image(systemName: captions ? "captions.bubble.fill" : "captions.bubble").frame(width: 44, height: 44) }.accessibilityLabel("Mostrar ou ocultar legendas")
                }.foregroundStyle(.secondary)
                Spacer()
                KzLAvatar(active: voice.active)
                    .frame(width: 136, height: 136)
                Text("KzL").font(.system(size: 32, weight: .semibold))
                Text((starting || call.isStarting || call.callID != nil) && !voice.open ? "Chamando…" : voice.presentationStatus).font(.title3).foregroundStyle(.secondary).multilineTextAlignment(.center)
                if voice.open { Text("\(voice.elapsedSeconds / 60):\(String(format: "%02d", voice.elapsedSeconds % 60))").font(.subheadline.monospacedDigit()).foregroundStyle(.secondary) }
                if let error = voice.error ?? call.error { Text(error).foregroundStyle(.orange).font(.caption) }
                if captions && !voice.caption.isEmpty { ScrollView { Text(voice.caption).font(.body).textSelection(.enabled) }.frame(maxHeight: 140) }
                if !voice.tasks.isEmpty {
                    Button { activity = true } label: {
                        HStack(spacing: 10) {
                            Image(systemName: "desktopcomputer")
                            VStack(alignment: .leading, spacing: 3) {
                                Text("Computador").font(.subheadline.weight(.medium))
                                Text(voice.notebook).font(.caption).foregroundStyle(.secondary).lineLimit(2)
                            }
                            Spacer(); Image(systemName: "chevron.right").font(.caption)
                        }.padding(14).background(.white.opacity(0.05), in: RoundedRectangle(cornerRadius: 16))
                    }.foregroundStyle(.primary).padding(.top, 12)
                }
                Spacer()
                if call.callID != nil || voice.open {
                    HStack(alignment: .top, spacing: 28) {
                        VStack(spacing: 10) {
                            AudioRoutePicker().frame(width: 64, height: 64).background(.white.opacity(0.08), in: Circle())
                            Text("Áudio").font(.caption).foregroundStyle(.secondary)
                        }
                        Button { call.end(); call.presented = false; dismiss() } label: {
                            VStack(spacing: 10) {
                                Image(systemName: "phone.down.fill").font(.system(size: 24)).foregroundStyle(.white).frame(width: 64, height: 64).background(PocketDesign.kzL, in: Circle())
                                Text("Encerrar").font(.caption).foregroundStyle(.secondary)
                            }
                        }.accessibilityLabel("Encerrar ligação")
                        Button { voice.setMuted(!voice.muted) } label: {
                            VStack(spacing: 10) {
                                Image(systemName: voice.muted ? "mic.slash.fill" : "mic.fill").font(.system(size: 23)).frame(width: 64, height: 64).background(.white.opacity(voice.muted ? 0.18 : 0.08), in: Circle())
                                Text(voice.muted ? "Ativar" : "Silenciar").font(.caption).foregroundStyle(.secondary)
                            }
                        }.foregroundStyle(.white)
                    }
                } else {
                    Button { requestCall() } label: { Label("Ligar para KzL", systemImage: "phone.fill").font(.headline).padding(.horizontal, 24).frame(minHeight: 54) }
                        .buttonStyle(.borderedProminent).tint(PocketDesign.kzL).disabled(starting || call.isStarting)
                }
            }.padding(.horizontal, 28).padding(.top, 8).padding(.bottom, 32)
        }.preferredColorScheme(.dark).tint(PocketDesign.kzL)
            .onAppear { consumeStartRequest() }
            .onChange(of: call.startRequested) { _, requested in if requested { consumeStartRequest() } }
            .confirmationDialog("Ligar com OpenAI Realtime?", isPresented: $consent, titleVisibility: .visible) {
                Button("Ligar") { billingAcknowledged = true; startCall() }
                Button("Cancelar", role: .cancel) { call.startRequested = false }
            } message: { Text("Voz e transcrição usam API paga. Microfone e contexto recente serão enviados à OpenAI. Próximos toques no telefone iniciam ligação diretamente; limite de tempo fica em Ajustes → Voz. Permissões do computador continuam valendo. Não diga senhas ou códigos.") }
            .sheet(isPresented: $activity) { NavigationStack { KzLTasksView().toolbar { Button("Fechar") { activity = false } } } }
    }
    private func consumeStartRequest() {
        guard call.startRequested else { return }
        call.startRequested = false
        requestCall()
    }
    private func requestCall() {
        guard !starting, !call.isStarting, call.callID == nil else { return }
        if billingAcknowledged { startCall() } else { consent = true }
    }
    private func startCall() {
        guard let target = call.session ?? session, !starting else { return }
        #if SNAPSHOT
        call.error = "Prévia visual: nenhuma chamada API iniciada."
        #else
        starting = true
        Task { await call.start(api: api, session: target); starting = false }
        #endif
    }
}

struct KzLAvatar: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    var active = false
    var body: some View {
        ZStack {
            Circle().fill(Color(red: 0.10, green: 0.10, blue: 0.13))
            if let image = UIImage(named: "KzL") {
                Image(uiImage: image).resizable().scaledToFit().clipShape(Circle())
            } else {
                // Safe fallback if an installation is missing the bundled original.
                Text("KzL").font(.system(size: 36, weight: .bold, design: .rounded)).foregroundStyle(PocketDesign.kzL).lineLimit(1).minimumScaleFactor(0.3).padding(8)
            }
        }.overlay(Circle().stroke(PocketDesign.kzL.opacity(active ? 0.8 : 0.2), lineWidth: 1.5))
            .accessibilityLabel(active ? "KzL conectado" : "KzL")
    }
}
