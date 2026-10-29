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
                Text("Áudio não é gravado pelo Pocket. Transcrição de entrada usa API e pode ter custo adicional; textos e tarefas ficam no histórico privado do Agente KzL no notebook. Contexto entre chamadas é limitado. Chamada encerra em segundo plano ou ao sair do painel; tarefas continuam. Limite de tempo não é limite monetário garantido.").font(.caption)
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
    @State private var cancellingID: String?
    @State private var taskToReview: KzLTask?
    @State private var question: QuestionForm?
    var body: some View {
        NavigationStack {
            List {
                Section {
                    VStack(spacing: 18) {
                        Image(systemName: voice.muted ? "mic.slash" : voice.open ? "waveform" : "waveform.circle")
                            .font(.system(size: 52, weight: .light)).foregroundStyle(voice.active ? Color.primary : Color.secondary)
                            .frame(width: 112, height: 112)
                            .background(Color(uiColor: .tertiarySystemFill), in: Circle())
                            .accessibilityHidden(true)
                        Text(voice.status).font(.title3.weight(.medium)).multilineTextAlignment(.center)
                    }.frame(maxWidth: .infinity).padding(.vertical, 24)
                    Text("Agente KzL · voz Realtime · execução persistente no notebook").font(.caption).foregroundStyle(.secondary)
                    if voice.open {
                        Text("\(voice.elapsedSeconds / 60):\(String(format: "%02d", voice.elapsedSeconds % 60)) / \(voice.maximumSeconds / 60):00").font(.system(.headline, design: .monospaced)).accessibilityLabel("Duração da chamada")
                        Text(voice.muted ? "Microfone mudo" : "Microfone via WebRTC · sem medidor PCM local").font(.caption)
                        Text(voice.route).font(.caption).foregroundStyle(.secondary)
                        HStack {
                            Button("Usar alto-falante") { voice.useSpeaker() }.disabled(!voice.active)
                            AudioRoutePicker().frame(width: 44, height: 44).accessibilityLabel("Selecionar saída de áudio no iOS")
                        }
                        HStack(spacing: 20) {
                            Button { voice.setMuted(!voice.muted) } label: {
                                Label(voice.muted ? "Ativar" : "Mudo", systemImage: voice.muted ? "mic.slash.fill" : "mic.fill")
                                    .frame(minHeight: 48)
                            }.disabled(!voice.active).buttonStyle(.bordered)
                            Spacer()
                            Button(role: .destructive) { voice.end() } label: {
                                Label("Encerrar", systemImage: "phone.down.fill").frame(minHeight: 48)
                            }.buttonStyle(.borderedProminent)
                        }
                        Button("Parar somente fala", systemImage: "speaker.slash") { voice.stopSpeaking() }.disabled(!voice.active)
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
                if !voice.caption.isEmpty { Section("Legenda · texto salvo no notebook quando confirmado") { Text(voice.caption).textSelection(.enabled) } }
                Section("Notebook") {
                    Text(voice.notebook).font(.caption)
                    if let issue = voice.taskSyncIssue { Text(issue).font(.caption).foregroundStyle(.orange) }
                    if let issue = voice.memoryNotice { Text(issue).font(.caption).foregroundStyle(.orange) }
                    ForEach(voice.tasks.prefix(12)) { task in
                        VStack(alignment: .leading, spacing: 6) {
                            Text(task.text).font(.subheadline).lineLimit(2)
                            Text(task.label).font(.caption.weight(.semibold)).foregroundStyle(task.state == "waiting" ? Color.orange : Style.blue)
                            if !task.result.isEmpty { Text(task.result).font(.caption).lineLimit(3) }
                            Button(task.state == "waiting" ? "Revisar permissão ou pergunta" : "Abrir tarefa") { voice.setMuted(true); taskToReview = task }
                            if task.canCancel { Button("Interromper esta tarefa", role: .destructive) { cancellingID = task.id; interruptTask = true } }
                        }
                    }
                    Text("Pedidos claros são delegados sem confirmação extra do Pocket. Permissões do OpenCode permanecem. Falar por cima e Encerrar param voz, não trabalho já enviado.").font(.caption).foregroundStyle(.secondary)
                }
                Section {
                    Text(voice.usageText).font(.caption).textSelection(.enabled)
                    DisclosureGroup("Diagnóstico sem chave ou conteúdo") {
                        Text(voice.diagnosticsText).font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                        ShareLink(item: voice.diagnosticsText) { Label("Compartilhar contadores", systemImage: "square.and.arrow.up") }
                    }
                }
             }.listStyle(.insetGrouped).navigationTitle("Conversa por voz").navigationBarTitleDisplayMode(.inline)
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
                .sheet(item: $taskToReview) { task in NavigationStack { KzLTaskDestination(id: task.child).toolbar { Button("Voltar à ligação") { taskToReview = nil } } } }
                .confirmationDialog("Iniciar chamada com API paga?", isPresented: $consent, titleVisibility: .visible) {
                    Button("Ligar via OpenCode do notebook") { Task { if !soundTest.running { await voice.start(api, session: session, monitor: monitor) } } }
                    Button("Cancelar", role: .cancel) { }
                } message: { Text("Microfone e contexto limitado do Agente KzL serão enviados à OpenAI. Transcrição e voz têm cobrança API. Textos serão salvos no notebook, sem gravar áudio. Pedidos claros poderão iniciar tarefas sem confirmação adicional; permissões do OpenCode permanecem. Não diga senhas/códigos. Limite de \(VoiceBudget.minutes(UserDefaults.standard.integer(forKey: "voice.minutes"))) minutos, não monetário.") }
                .alert("Interromper tarefa no notebook?", isPresented: $interruptTask) {
                    Button("Interromper", role: .destructive) { Task {
                        guard let id = cancellingID else { return }
                        do { let _: KzLTask = try await api.request("/phone/kzl/task/\(id)/cancel", method: "POST", body: [:]) }
                        catch { voice.error = "Interrupção não confirmada; confira tarefa antes de repetir." }
                    } }
                    Button("Cancelar", role: .cancel) { }
                } message: { Text("Solicita interrupção somente da tarefa selecionada; não desfaz ações já realizadas.") }
        }
    }
}

struct AudioRoutePicker: UIViewRepresentable {
    func makeUIView(context: Context) -> AVRoutePickerView { let view = AVRoutePickerView(); view.prioritizesVideoDevices = false; return view }
    func updateUIView(_ uiView: AVRoutePickerView, context: Context) { }
}
