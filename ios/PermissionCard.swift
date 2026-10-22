import SwiftUI

struct PermissionCard: View {
    let permission: Permission
    let details: String?
    let strict: Bool
    let reply: (String) async -> Void
    @State private var confirm = false
    @State private var busy = false
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("A IA aguarda sua autorização", systemImage: "hand.raised.fill").font(.headline)
            Text(permission.message ?? permission.action).font(.subheadline).textSelection(.enabled)
            Text(permission.resources.joined(separator: "\n")).font(.system(.caption2, design: .monospaced)).lineLimit(4)
            if let details, !details.isEmpty {
                DisclosureGroup("Ver ação solicitada") {
                    ScrollView { Text(details).font(.system(.caption, design: .monospaced)).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading) }
                        .frame(maxHeight: 180)
                }
            } else if strict {
                Text("Detalhes ainda não disponíveis. Aguarde atualização ou confira no notebook; permitir fica bloqueado.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            HStack {
                Button("Negar", role: .destructive) { answer("reject") }.disabled(busy)
                Spacer()
                Button("Revisar e permitir") { confirm = true }
                    .buttonStyle(.borderedProminent).disabled(busy || (strict && details?.isEmpty != false))
            }
        }
        .padding().background(Color.orange.opacity(0.12))
        .confirmationDialog("Autorizar somente esta ação?", isPresented: $confirm, titleVisibility: .visible) {
            Button("Permitir uma vez") { answer("once") }
            Button("Cancelar", role: .cancel) { }
        } message: {
            Text("Confira comando e destino em “Ver ação solicitada”. Toques podem enviar, apagar ou comprar conforme tela atual. Negue se efeito não estiver claro. Esta autorização não vale para próximas ações.")
        }
    }
    func answer(_ decision: String) {
        busy = true
        Task { await reply(decision); busy = false }
    }
}
