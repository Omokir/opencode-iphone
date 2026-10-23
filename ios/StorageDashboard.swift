import SwiftUI

struct StorageDashboard: View {
    let host: StorageCapacity?
    let stale: Bool
    @State private var phone: StorageCapacity?
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            capacity("Armazenamento do iPhone", icon: "iphone", value: phone)
            capacity("Armazenamento do computador", icon: "internaldrive", value: host)
            Text(stale ? "Computador sem atualização; valores anteriores podem estar desatualizados." : "Computador: disco da pasta de destino. GB decimais; espaço do iPhone fica somente neste aparelho.")
                .font(.caption2).foregroundStyle(.secondary)
        }
        .padding(.vertical, 6)
        .task {
            while !Task.isCancelled {
                let url = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
                if let value = try? url.resourceValues(forKeys: [.volumeTotalCapacityKey, .volumeAvailableCapacityKey]),
                   let total = value.volumeTotalCapacity, let free = value.volumeAvailableCapacity, total > 0 {
                    phone = StorageCapacity(totalBytes: Int64(total), freeBytes: Int64(free))
                } else { phone = nil }
                do { try await Task.sleep(for: .seconds(8)) } catch { break }
            }
        }
    }
    @ViewBuilder private func capacity(_ title: String, icon: String, value: StorageCapacity?) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Label(title, systemImage: icon).font(.subheadline.weight(.semibold))
            if let value {
                HStack {
                    Text(String(format: "%.0f%% ocupado", value.usedPercent))
                    Spacer()
                    Text(String(format: "%.1f GB livres", value.freeGB))
                }.font(.subheadline.monospacedDigit())
                ProgressView(value: value.usedPercent, total: 100).tint(value.usedPercent >= 90 ? .orange : Style.blue)
                Text(String(format: "Capacidade: %.1f GB", value.totalGB)).font(.caption).foregroundStyle(.secondary)
            } else { Text("Espaço indisponível").font(.caption).foregroundStyle(.secondary) }
        }
    }
}
