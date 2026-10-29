import SwiftUI
import AVFoundation
import AVKit

struct VoiceSettingsView: View {
    @EnvironmentObject var privacy: PrivacyLock
    @State private var key = ""
    @State private var saved = VoiceKey.read() != nil
    @State private var notice: String?
    @State private var deleting = false
    @AppStorage("voice.model") private var model = "gpt-realtime-2.1"
    @AppStorage("voice.voice") private var voice = "marin"
    @AppStorage("voice.minutes") private var minutes = 5
    @AppStorage("voice.outputTokens") private var outputTokens = 512
    var body: some View {
        Form {
            Section("OpenAI Realtime") {
                Text("Realtime conversa diretamente por voz e usa OpenCode como ferramenta. Execução continua no login/modelo já configurado no notebook.").font(.caption)
                Text("Modelo: gpt-realtime-2.1 · WebRTC nativo")
                Picker("Voz", selection: $voice) { Text("Marin").tag("marin"); Text("Cedar").tag("cedar") }
                Text("Disponibilidade depende da conta API. Não há troca automática de modelo nem fallback pago.").font(.caption).foregroundStyle(.secondary)
            }
            Section("Credencial no notebook") {
                Label("Gerenciada pelo OpenCode do notebook", systemImage: "key.fill")
                Text("Celular envia oferta WebRTC pelo pareamento Tailscale e recebe resposta SDP. Chave permanente não sai do notebook. Login/modelo de programação permanecem separados.").font(.caption)
                Button("Apagar chave", role: .destructive) { deleting = true }.disabled(!saved)
                Text("Botão remove somente chave antiga deste iPhone, se existir. Ela não é usada pelo novo transporte. Use limite de gastos no projeto OpenAI do notebook.").font(.caption)
            }
            Section("Privacidade e cobrança") {
                Stepper("Limite por chamada: \(VoiceBudget.minutes(minutes)) min", value: Binding(get: { VoiceBudget.minutes(minutes) }, set: { minutes = VoiceBudget.minutes($0) }), in: 1...15)
                Picker("Limite de saída por resposta", selection: $outputTokens) {
                    Text("512 tokens · padrão").tag(512); Text("1.024 tokens").tag(1024); Text("2.048 tokens").tag(2048)
                }
                Text("Aumentar saída pode aumentar custo; não é correção comprovada de áudio. Uso de raciocínio também pode consumir orçamento antes de voz. Não há ajuste automático.").font(.caption).foregroundStyle(.secondary)
                Text("API Realtime tem cobrança separada da assinatura ChatGPT e do provedor usado pelo OpenCode. Áudio sai do iPhone durante chamada; consultas da ferramenta podem enviar texto recente desta conversa à OpenAI.").font(.caption)
                Text("Sem gravação local de áudio ou transcrição persistida. Chamada encerra ao sair do painel, entrar em segundo plano, bloquear aparelho ou perder conexão. Limite configurável entre 1 e 15 minutos; não é limite monetário garantido.").font(.caption)
            }
            if let notice { Text(notice).font(.caption).foregroundStyle(.secondary) }
        }.navigationTitle("Voz")
            .onDisappear { key = "" }
            .alert("Apagar chave de voz?", isPresented: $deleting) {
                Button("Apagar", role: .destructive) { Task { if await privacy.confirm("Apagar chave de voz") { VoiceKey.clear(); key = ""; saved = false; notice = "Chave removida deste iPhone." } } }
                Button("Cancelar", role: .cancel) { }
            } message: { Text("Isso não revoga chave na OpenAI. Revogue também no painel do provedor se necessário.") }
    }
}

struct VoiceCallView: View {
    @EnvironmentObject var api: API
    @EnvironmentObject var privacy: PrivacyLock
    @Environment(\.scenePhase) var phase
    @Environment(\.dismiss) var dismiss
    let session: Session
    @StateObject private var voice = RealtimeVoiceStore()
    @StateObject private var monitor = ChatStore()
    @StateObject private var soundTest = VoiceSoundTest()
    @State private var consent = false
    @State private var interruptTask = false
    @State private var question: QuestionForm?
    var body: some View {
        NavigationStack {
            List {
                Section {
                    Label(voice.status, systemImage: voice.open ? "waveform.circle.fill" : "phone.circle")
                        .font(.title3.weight(.semibold)).foregroundStyle(voice.active ? Color.green : Style.blue)
                    Text("Voz: OpenAI Realtime · execução: OpenCode do notebook").font(.caption).foregroundStyle(.secondary)
                    if voice.open {
                        Text("\(voice.elapsedSeconds / 60):\(String(format: "%02d", voice.elapsedSeconds % 60)) / \(voice.maximumSeconds / 60):00").font(.system(.headline, design: .monospaced)).accessibilityLabel("Duração da chamada")
                        Text(voice.muted ? "Microfone mudo" : "Microfone via WebRTC · sem medidor PCM local").font(.caption)
                        Text(voice.route).font(.caption).foregroundStyle(.secondary)
                        HStack {
                            Button("Usar alto-falante") { voice.useSpeaker() }.disabled(!voice.active)
                            AudioRoutePicker().frame(width: 44, height: 44).accessibilityLabel("Selecionar saída de áudio no iOS")
                        }
                        Button(voice.muted ? "Ativar microfone" : "Mudo", systemImage: voice.muted ? "mic.slash.fill" : "mic.fill") { voice.setMuted(!voice.muted) }.disabled(!voice.active)
                        Button("Parar somente fala", systemImage: "speaker.slash") { voice.stopSpeaking() }.disabled(!voice.active)
                        Button("Encerrar chamada", role: .destructive) { voice.end() }
                    } else {
                        NavigationLink("Revisar tarefas sem reenviar") { TaskHistoryView() }
                        Button("Ligar", systemImage: "phone.fill") { consent = true }.disabled(soundTest.running)
                        Button(soundTest.running ? "Testando circuito local…" : "Testar som local (sem API)", systemImage: "speaker.wave.2") { Task { await soundTest.run() } }.disabled(soundTest.running)
                        Text("Teste local verifica saída do iOS, não comprova mídia WebRTC. Nada é enviado à rede. Aumente volume pelos botões do iPhone se necessário.").font(.caption).foregroundStyle(.secondary)
                        if !soundTest.result.isEmpty { Text(soundTest.result).font(.system(.caption, design: .monospaced)).textSelection(.enabled) }
                        NavigationLink("Configurar voz") { VoiceSettingsView() }
                    }
                    if let error = voice.error { Text(error).font(.caption).foregroundStyle(.red) }
                }
                if !voice.caption.isEmpty { Section("Legenda da voz · somente nesta chamada") { Text(voice.caption).textSelection(.enabled) } }
                if let call = voice.pending {
                    Section("Confirmar tarefa no notebook") {
                        Text(call.task ?? "").font(.body).textSelection(.enabled)
                        Text("Só este texto será enviado à conversa atual. Login/modelo e permissões do OpenCode não serão alterados.").font(.caption)
                        Button("Confirmar envio ao OpenCode") { Task { if await privacy.confirm("Enviar tarefa de voz ao notebook") { await voice.approve(call, api: api, session: session, monitor: monitor) } } }
                        Button("Negar proposta", role: .cancel) { voice.deny() }
                        Text("Nova fala antes de confirmar cancela esta proposta, evitando enviar instrução antiga.").font(.caption).foregroundStyle(.secondary)
                    }
                }
                Section("Notebook") {
                    Text(voice.notebook).font(.caption)
                    ForEach(monitor.permissions) { permission in
                        PermissionCard(permission: permission, details: monitor.permissionDetails[permission.id], strict: true) { decision in
                            await monitor.reply(api, session: session, permission: permission, decision: decision)
                        }
                    }
                    ForEach(monitor.questions) { form in Button(form.title) { voice.setMuted(true); question = form } }
                    Button("Interromper tarefa no notebook", role: .destructive) { interruptTask = true }.disabled(!api.connected)
                    Text("Falar por cima e Encerrar param voz, não tarefa já admitida. Consulte conversa antes de repetir envio incerto.").font(.caption).foregroundStyle(.secondary)
                }
                Section {
                    Text(voice.usageText).font(.caption).textSelection(.enabled)
                    DisclosureGroup("Diagnóstico sem chave ou conteúdo") {
                        Text(voice.diagnosticsText).font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                        ShareLink(item: voice.diagnosticsText) { Label("Compartilhar contadores", systemImage: "square.and.arrow.up") }
                    }
                }
            }.navigationTitle("Conversa por voz").navigationBarTitleDisplayMode(.inline)
                .toolbar { Button("Fechar") { voice.end(); dismiss() } }
                .onDisappear { voice.end(); soundTest.stop() }
                .onChange(of: phase) { _, value in if value == .background { voice.end(); soundTest.stop() } }
                .onChange(of: api.connected) { _, connected in if !connected { voice.end() } }
                .onChange(of: api.server) { _, _ in voice.end() }
                .onChange(of: api.connectionID) { _, _ in voice.end() }
                .onReceive(NotificationCenter.default.publisher(for: AVAudioSession.interruptionNotification)) { _ in if voice.open { voice.end(reason: "Áudio interrompido pelo iOS; toque Ligar para retomar manualmente.") } }
                .onReceive(NotificationCenter.default.publisher(for: AVAudioSession.routeChangeNotification)) { notification in
                    let raw = notification.userInfo?[AVAudioSessionRouteChangeReasonKey] as? UInt
                    if voice.active, raw == AVAudioSession.RouteChangeReason.oldDeviceUnavailable.rawValue || raw == AVAudioSession.RouteChangeReason.newDeviceAvailable.rawValue {
                        voice.end(reason: "Saída/microfone mudou. Inicie nova chamada para configurar áudio com segurança.")
                    }
                }
                .sheet(item: $question) { form in QuestionFormView(question: form, session: session) { Task { await monitor.refresh(api, session: session) } } }
                .confirmationDialog("Iniciar chamada com API paga?", isPresented: $consent, titleVisibility: .visible) {
                    Button("Ligar via OpenCode do notebook") { Task { if await privacy.confirm("Iniciar conversa de voz com OpenAI Realtime"), !soundTest.running { await voice.start(api, session: session, monitor: monitor) } } }
                    Button("Cancelar", role: .cancel) { }
                } message: { Text("Microfone será transmitido à OpenAI. Texto recente desta conversa pode ser compartilhado com Realtime por ferramenta. Cobrança separada; limite de \(VoiceBudget.minutes(UserDefaults.standard.integer(forKey: "voice.minutes"))) minutos, sem garantia de valor máximo. Não diga senhas/códigos. Nenhuma tarefa será enviada sem confirmação visual.") }
                .alert("Interromper tarefa no notebook?", isPresented: $interruptTask) {
                    Button("Interromper", role: .destructive) { Task { if await privacy.confirm("Interromper tarefa no notebook") { await monitor.interrupt(api, session: session) } } }
                    Button("Cancelar", role: .cancel) { }
                } message: { Text("Solicita interrupção à conversa atual; não desfaz ações já realizadas.") }
        }
    }
}

struct AudioRoutePicker: UIViewRepresentable {
    func makeUIView(context: Context) -> AVRoutePickerView { let view = AVRoutePickerView(); view.prioritizesVideoDevices = false; return view }
    func updateUIView(_ uiView: AVRoutePickerView, context: Context) { }
}
