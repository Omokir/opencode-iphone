import SwiftUI

struct NotebookPowerStatus: Decodable { let powerOff: String; let wakeConfigured: Bool }
struct NotebookPowerTicket: Decodable { let ticket: String; let expiresIn: Int }
struct NotebookPowerAdmission: Decodable { let admitted: Bool }

struct NotebookPowerView: View {
    @EnvironmentObject var api: API
    @EnvironmentObject var privacy: PrivacyLock
    @State private var status: NotebookPowerStatus?
    @State private var confirmation = ""
    @State private var ticket: String?
    @State private var busy = false
    @State private var message: String?
    @State private var preparedServer = ""
    var body: some View {
        Form {
            Section("Desligar notebook") {
                Text("Encerra computador que executa OpenCode. Conversas em execução, transferências e conexão serão interrompidas; salve trabalho antes. App não garante que outros programas tenham salvo seus dados.").font(.caption).foregroundStyle(.red)
                Text(status?.powerOff == "yes" ? "Linux permite solicitar desligamento sem diálogo administrativo." : "Desligamento remoto não confirmado/autorizado pelo Linux.").font(.caption)
                TextField("Digite DESLIGAR para habilitar", text: $confirmation).textInputAutocapitalization(.characters).autocorrectionDisabled()
                Button("Preparar desligamento", role: .destructive) { Task { await prepare() } }
                    .disabled(confirmation != "DESLIGAR" || busy || status?.powerOff != "yes" || !api.connected)
                Text("Haverá confirmação final. Nenhum privilégio, política Linux ou bloqueio de suspensão será alterado pelo app.").font(.caption).foregroundStyle(.secondary)
            }
            Section("Ligar notebook") {
                Label("Wake-on-LAN não configurado", systemImage: "power.circle")
                Text("Notebook desligado não executa Tailscale nem recebe chamadas do Pocket. Ligar de longe exige suporte de hardware/BIOS, alimentação, rede compatível e outro dispositivo ligado na mesma rede para enviar sinal de despertar. Esse caminho ainda não foi validado/configurado.").font(.caption)
                Button("Ligar remotamente") { }.disabled(true)
                Text("Manter acordado apenas evita suspensão; não liga computador que já desligou. Após desligar, pode ser necessário botão físico para voltar.").font(.caption).foregroundStyle(.secondary)
            }
            if let message { Text(message).font(.caption).textSelection(.enabled) }
            Button("Consultar capacidade do Linux") { Task { await check() } }.disabled(busy)
        }.navigationTitle("Energia do notebook")
            .task { await check() }
            .alert("Desligar notebook agora?", isPresented: Binding(get: { ticket != nil }, set: { if !$0 { ticket = nil } }), presenting: ticket) { saved in
                Button("Desligar agora", role: .destructive) { Task { await powerOff(saved) } }
                Button("Cancelar", role: .cancel) { ticket = nil }
            } message: { _ in Text("OpenCode e transferências vão parar. Ligar pelo app ainda não está disponível. Confirmação vale 45 segundos e só pode ser usada uma vez.") }
    }
    func check() async {
        do { status = try await api.request("/phone/power/status") }
        catch { message = ConnectionAdvice.describe(error) }
    }
    func prepare() async {
        guard !busy, confirmation == "DESLIGAR" else { return }
        guard await privacy.confirm("Preparar desligamento do notebook") else { return }
        busy = true; defer { busy = false }; confirmation = ""
        let server = api.server
        do { let result: NotebookPowerTicket = try await api.request("/phone/power/prepare", method: "POST"); if api.server == server && api.connected { preparedServer = server; ticket = result.ticket } }
        catch { message = "Não preparado: \(ConnectionAdvice.describe(error))" }
    }
    func powerOff(_ saved: String) async {
        guard !busy, api.connected, preparedServer == api.server else { return }; ticket = nil
        busy = true; defer { busy = false }
        do {
            let result: NotebookPowerAdmission = try await api.request("/phone/power/off", method: "POST", body: ["ticket": saved])
            message = result.admitted ? "Solicitação admitida pelo Linux. Conexão pode cair; desligamento físico não foi verificado pelo app." : "Linux não confirmou solicitação."
        } catch { message = "Resultado não confirmado; notebook pode já estar desligando. Confira estado antes de tentar novamente. Não houve repetição automática." }
    }
}
