import SwiftUI
import ImageIO

struct ComputerActivity: Decodable {
    struct Step: Decodable, Identifiable {
        struct Picture: Decodable { let index: Int; let mime: String }
        let messageID: String
        let sessionID: String?
        let toolID: String
        let name: String
        let state: String
        let time: Double
        let images: [Picture]
        var id: String { (sessionID ?? "") + ":" + messageID + ":" + toolID }
    }
    let steps: [Step]
}

struct ComputerActivityView: View {
    @EnvironmentObject var api: API
    @Environment(\.scenePhase) var phase
    let task: KzLTask
    @State private var steps: [ComputerActivity.Step] = []
    @State private var image: UIImage?
    @State private var error: String?
    @State private var loading = false
    var body: some View {
        List {
            Section {
                Text(task.text)
                Text("Etapas registradas pelo OpenCode. Capturas são pontuais e podem estar antigas; não é transmissão ao vivo.").font(.caption).foregroundStyle(.secondary)
                if let error { Text(error).foregroundStyle(.orange) }
                if let image { Image(uiImage: image).resizable().scaledToFit().accessibilityLabel("Captura registrada da tarefa") }
            }
            Section("Usando computador") {
                if steps.isEmpty { Text("Nenhuma etapa de computer-use nesta página. Consulte conversa completa da tarefa.").foregroundStyle(.secondary) }
                ForEach(steps) { step in
                    VStack(alignment: .leading, spacing: 8) {
                        Text(step.name).font(.system(.subheadline, design: .monospaced))
                        Text(step.state).font(.caption)
                        Text(Date(timeIntervalSince1970: step.time > 100_000_000_000 ? step.time / 1000 : step.time), style: .time).font(.caption)
                        ForEach(step.images, id: \.index) { picture in
                            Button("Ver captura registrada") { Task { await preview(step, picture.index) } }.disabled(loading)
                        }
                    }
                }
            }
            NavigationLink("Abrir conversa / permissões") { KzLTaskDestination(id: task.child) }
        }.navigationTitle("Computador")
            .task(id: phase) {
                guard phase == .active else { return }
                while !Task.isCancelled {
                    let connection = api.connectionID
                    do {
                        let activity: ComputerActivity = try await api.request("/phone/kzl/task/\(task.id)/computer")
                        guard connection == api.connectionID, !Task.isCancelled else { return }
                        steps = activity.steps; error = nil
                    } catch { self.error = "Atividade não confirmada. Últimos dados podem estar antigos." }
                    do { try await Task.sleep(for: .seconds(3)) } catch { return }
                }
            }
    }
    private func preview(_ step: ComputerActivity.Step, _ index: Int) async {
        loading = true; defer { loading = false }
        let connection = api.connectionID
        do {
            let path = "/phone/kzl/task/\(task.id)/computer/image?message=" + API.escape(step.messageID) + "&tool=" + API.escape(step.toolID) + "&index=\(index)&session=" + API.escape(step.sessionID ?? task.child)
            let request = try api.makeRequest(path)
            let (data, response) = try await api.transport.data(for: request)
            guard connection == api.connectionID, !Task.isCancelled else { return }
            guard (response as? HTTPURLResponse)?.statusCode == 200, data.count <= 8 * 1024 * 1024,
                  let source = CGImageSourceCreateWithData(data as CFData, nil),
                  let thumbnail = CGImageSourceCreateThumbnailAtIndex(source, 0, [kCGImageSourceCreateThumbnailFromImageAlways: true, kCGImageSourceThumbnailMaxPixelSize: 1600, kCGImageSourceCreateThumbnailWithTransform: true] as CFDictionary) else {
                throw PhoneError.message("Captura indisponível ou incompatível.")
            }
            image = UIImage(cgImage: thumbnail)
        } catch { self.error = "Captura não disponível. Nenhum arquivo ou URL externo foi aberto." }
    }
}
