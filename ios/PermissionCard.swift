import SwiftUI

struct PermissionCard: View {
    let permission: Permission
    let details: String?
    let strict: Bool
    let reply: (String) async -> Void
    @State private var confirm = false
    @State private var busy = false
    @State private var expanded = false
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("Permissão necessária", systemImage: "hand.raised").font(.subheadline.weight(.semibold))
            Text(permission.message ?? permission.action).font(.subheadline).lineLimit(expanded ? nil : 2).textSelection(.enabled)
            if expanded {
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
            }
            HStack {
                Button("Negar", role: .destructive) { answer("reject") }.disabled(busy)
                Spacer()
                if expanded {
                    Button("Permitir uma vez") { confirm = true }
                        .buttonStyle(.bordered).disabled(busy || (strict && details?.isEmpty != false))
                } else {
                    Button("Revisar") { expanded = true }.buttonStyle(.bordered).disabled(busy)
                }
            }
        }
        .padding(14).background(Color.orange.opacity(0.07), in: RoundedRectangle(cornerRadius: 16))
        .padding(.horizontal, 12).padding(.vertical, 4)
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
