import SwiftUI

struct HostBatteryView: View {
    let status: HostStatus?
    let stale: Bool
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if stale {
                Label("Bateria do notebook sem atualização", systemImage: "wifi.exclamationmark").foregroundStyle(.secondary)
                Text("Verifique Tailscale e conexão do notebook.").font(.caption).foregroundStyle(.secondary)
            } else if let status, let battery = status.battery {
                HStack {
                    Label("Notebook", systemImage: "laptopcomputer").font(.subheadline.weight(.semibold))
                    Spacer()
                    if let percentage = battery.percentage {
                        Label("\(percentage)%", systemImage: battery.charging == true ? "battery.100percent.bolt" : percentage <= 20 ? "battery.25percent" : "battery.75percent")
                            .foregroundStyle(percentage <= 20 && battery.onAC != true ? Color.orange : battery.charging == true ? Color.green : .primary)
                            .font(.system(.subheadline, design: .monospaced, weight: .semibold))
                    } else { Text(battery.available ? "Percentual indisponível" : "Sem bateria detectada").font(.caption).foregroundStyle(.secondary) }
                }
                HStack {
                    Text(battery.charging == true ? "Carregando" : battery.onAC == true ? "Na tomada" : battery.state == "Discharging" ? "Usando bateria" : "Alimentação não confirmada")
                    Spacer()
                    Text(status.awake ? "Modo acordado ligado" : "Modo acordado desligado")
                }.font(.caption).foregroundStyle(.secondary)
                if let percentage = battery.percentage, percentage <= 20, battery.onAC != true {
                    Text("Bateria baixa. Conecte notebook à tomada para não perder acesso remoto.").font(.caption).foregroundStyle(.orange)
                }
            } else {
                Label("Consultando bateria do notebook…", systemImage: "battery.100percent").font(.caption).foregroundStyle(.secondary)
            }
        }.padding(.vertical, 4).accessibilityElement(children: .combine)
    }
}
