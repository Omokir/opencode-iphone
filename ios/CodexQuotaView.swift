import SwiftUI

struct CodexQuotaView: View {
    let quota: CodexQuota?
    let failed: Bool
    let loading: Bool
    let refresh: () -> Void
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Label("Codex semanal", systemImage: "chart.pie").font(.subheadline.weight(.semibold))
                Spacer()
                Button { refresh() } label: {
                    if loading { ProgressView().controlSize(.mini) } else { Image(systemName: "arrow.clockwise") }
                }.disabled(loading).accessibilityLabel("Atualizar cota Codex")
            }
            if failed {
                Text("Cota sem atualização. Verifique conexão com notebook.").font(.caption).foregroundStyle(.secondary)
            } else if let quota {
                if let week = quota.weekly {
                    HStack {
                        Text("\(week.remainingPercent.formatted(.number.precision(.fractionLength(0...1))))% disponível")
                            .font(.headline).foregroundStyle(week.usedPercent >= 80 ? Color.orange : Style.blue)
                        Spacer()
                        Text("\(week.usedPercent.formatted(.number.precision(.fractionLength(0...1))))% usado").font(.caption).foregroundStyle(.secondary)
                    }
                    ProgressView(value: week.usedPercent / 100).tint(week.usedPercent >= 80 ? .orange : Style.blue)
                    if let reset = week.resetsAt {
                        Text("Renova em \(Date(timeIntervalSince1970: reset).formatted(date: .abbreviated, time: .shortened)).")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                } else {
                    Text(quota.reason ?? "Janela semanal não informada pela conta.").font(.caption).foregroundStyle(.secondary)
                }
                if let label = quota.accountLabel { Text("Conta Codex: \(label)").font(.caption2).foregroundStyle(.secondary) }
                Text("Consulta: \(Date(timeIntervalSince1970: quota.checkedAt).formatted(date: .omitted, time: .shortened)). Não é saldo de API nem confirmação da conta usada pelo modelo do chat.")
                    .font(.caption2).foregroundStyle(.secondary)
            } else {
                Text(loading ? "Consultando conta do Codex no notebook…" : "Cota ainda não consultada.").font(.caption).foregroundStyle(.secondary)
            }
        }.padding(.vertical, 4)
    }
}
