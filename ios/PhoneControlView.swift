import SwiftUI

struct PhoneControlView: View {
    @EnvironmentObject var api: API
    @Environment(\.scenePhase) var phase
    @Environment(\.dismiss) var dismiss
    @State private var status: ControlStatus?
    @State private var path: [Session] = []
    @State private var busy = false
    @State private var stopping = false
    @State private var consent = false
    @State private var error: String?
    @State private var fetchError: String?
    @State private var notice: String?
    @State private var lastCheck: Date?
    @State private var probing = false
    @State private var probeResult: String?
    @State private var probeTask: Task<Void, Never>?
    @EnvironmentObject var privacy: PrivacyLock
    @AppStorage("settings.advanced") private var advanced = false

    var body: some View {
        NavigationStack(path: $path) {
            List {
                Section {
                    VStack(alignment: .leading, spacing: 14) {
                        Label("Seu iPhone, sob seu controle", systemImage: "iphone.gen3.radiowaves.left.and.right")
                            .font(.system(.title2, design: .rounded, weight: .bold)).fixedSize(horizontal: false, vertical: true)
                        Text("Você define tarefa e aprova ações. A IA usa agente conectado ao notebook.")
                            .foregroundStyle(.secondary)
                    }.padding(.vertical, 8)
                }
                Section("Conexão") {
                    LabeledContent("Notebook", value: api.reachable == false ? "Sem conexão" : lastCheck == nil ? "Consultando…" : "Conectado")
                    if let status {
                        LabeledContent(status.device.name, value: status.device.connected ? "Detectado" : "Não detectado")
                        LabeledContent("Agente", value: status.device.agentInstalled ? "Instalado" : "Não confirmado")
                        Label(status.enabled ? "Automação liberada" : "Automação pausada", systemImage: status.enabled ? "checkmark.shield" : "pause.circle")
                            .foregroundStyle(status.enabled ? Color.green : .secondary)
                        Text(status.ready ? "Canal de automação respondendo." : "Agente será iniciado quando tarefa precisar da tela.")
                            .font(.caption).foregroundStyle(.secondary)
                        if let expiry = status.expiresAt, status.enabled {
                            Text("Autorização até \(Date(timeIntervalSince1970: expiry).formatted(date: .omitted, time: .shortened)). Renove para continuar depois disso.")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    if let lastCheck { Text("Última consulta: \(lastCheck.formatted(date: .omitted, time: .standard))").font(.caption2).foregroundStyle(.secondary) }
                }
                if let status, status.sessionID != nil {
                    Section("Tarefa") {
                        Label(status.activity, systemImage: status.pending > 0 ? "hand.raised" : status.running ? "gearshape.2" : "text.bubble")
                        if status.pending > 0 { Text("\(status.pending) autorização(ões) aguardando na conversa.").font(.caption).foregroundStyle(.secondary) }
                        Button("Abrir conversa de controle") { Task { await openSession() } }.disabled(busy)
                    }
                }
                Section {
                    Button(status?.enabled == true ? "Renovar por 15 minutos e abrir tarefa" : "Liberar controle por 15 minutos") { consent = true }
                        .disabled(busy || status?.configured != true || status?.device.connected != true)
                    Button("Parar automação", role: .destructive) { Task { await stop() } }.disabled(stopping)
                } footer: {
                    Text("Parar bloqueia novas chamadas pelo MCP e solicita interrupção da conversa. Não desfaz ações já realizadas. Se perder conexão com notebook, parada não pode ser confirmada: bloqueie iPhone ou desconecte cabo.")
                }
                if advanced { Section("Sem cabo — diagnóstico experimental") {
                    Text("Teste somente de conexão ao agente neste iPhone. Não lê tela, não toca em apps e não libera automação.")
                        .font(.caption).foregroundStyle(.secondary)
                    Button(probing ? "Verificando agente local…" : "Testar agente neste iPhone") {
                        probing = true
                        probeResult = nil
                        probeTask = Task { @MainActor in
                            let result = await LocalAgentProbe.check()
                            guard !Task.isCancelled else { return }
                            probeResult = result
                            probing = false
                        }
                    }.disabled(probing)
                    if let probeResult { Text(probeResult).font(.caption).textSelection(.enabled) }
                    Text("Controle distante ainda não habilitado. Este teste verifica pré-requisito da futura ponte; nenhum endereço externo ou token é enviado ao agente.")
                        .font(.caption).foregroundStyle(.secondary)
                } }
                Section("Antes de começar") {
                    Label("Mantenha cabo conectado e iPhone desbloqueado. Bloqueio de tela não é detectado com certeza nesta versão.", systemImage: "cable.connector")
                    Label("Cada ação de toque, digitação ou abertura de app pede aprovação nesta conversa. Leia descrição antes de permitir.", systemImage: "hand.raised")
                    Text("Envio, exclusão, compra e execução de Atalhos também precisam de confirmação. A IA não deve contornar negativas. Outras conversas mantêm suas próprias permissões; isto não é isolamento contra programas do notebook.")
                        .font(.caption).foregroundStyle(.secondary)
                }
                if let notice { Section { Text(notice).foregroundStyle(.secondary) } }
                if let error { Section { Text(error).foregroundStyle(.red).textSelection(.enabled); Button("Fechar aviso") { self.error = nil } } }
                if let fetchError { Section { Text(fetchError).foregroundStyle(.red); Button("Tentar consultar novamente") { Task { await refresh() } } } }
            }
            .navigationTitle("Controlar iPhone").navigationBarTitleDisplayMode(.inline)
            .navigationDestination(for: Session.self) { ChatView(session: $0) }
            .toolbar {
                ToolbarItem(placement: .topBarLeading) { Button("Fechar") { dismiss() } }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Parar", systemImage: "stop.circle.fill", role: .destructive) { Task { await stop() } }.disabled(stopping)
                }
            }
            .overlay { if busy { ProgressView() } }
            .onDisappear { probeTask?.cancel(); probing = false }
            .onChange(of: phase) { _, value in
                if value != .active { probeTask?.cancel(); probing = false; probeResult = nil }
            }
            .confirmationDialog("Liberar leitura da tela por 15 minutos?", isPresented: $consent, titleVisibility: .visible) {
                Button("Liberar e abrir tarefa") { Task { await start() } }
                Button("Cancelar", role: .cancel) { }
            } message: {
                Text("A IA poderá ler tela e listar aplicativos. Cada ação que altera tela pede aprovação na conversa. Não mostre senhas ou códigos de autenticação durante controle.")
            }
            .task(id: phase) {
                guard phase == .active else { return }
                while !Task.isCancelled {
                    await refresh()
                    do { try await Task.sleep(for: .seconds(5)) } catch { break }
                }
            }
        }
    }

    func refresh() async {
        guard !busy else { return }
        do {
            status = try await api.request("/phone/control/status")
            lastCheck = Date()
            fetchError = nil
        } catch let failure as URLError where failure.code == .cancelled { }
        catch { self.fetchError = "Estado não atualizado: \(error.localizedDescription). Verifique VPN e notebook." }
    }
    func start() async {
        guard await privacy.confirm("Autorizar controle do iPhone") else { return }
        busy = true
        defer { busy = false }
        do {
            let session: Item<Session> = try await api.request("/phone/control/start", method: "POST", body: [:])
            notice = nil
            error = nil
            path.append(session.data)
        } catch { self.error = "Liberação não confirmada: \(error.localizedDescription). Consulte estado antes de tentar novamente." }
    }
    func openSession() async {
        guard let id = status?.sessionID else { return }
        busy = true
        defer { busy = false }
        do {
            let session: Item<Session> = try await api.request("/api/session/\(id)")
            path.append(session.data)
        } catch { self.error = error.localizedDescription }
    }
    func stop() async {
        guard !stopping else { return }
        stopping = true
        defer { stopping = false }
        busy = true
        do {
            let stopped: ControlStopped = try await api.request("/phone/control/stop", method: "POST", body: [:])
            guard !stopped.enabled else { throw PhoneError.message("Notebook não confirmou bloqueio.") }
            notice = stopped.warnings.isEmpty ? "Novas chamadas bloqueadas. Interrupção solicitada; ações anteriores não são desfeitas." : stopped.warnings.joined(separator: " ")
            error = nil
        } catch { self.error = "Parada não confirmada: \(error.localizedDescription). Bloqueie iPhone ou desconecte cabo." }
        busy = false
        await refresh()
    }
}
