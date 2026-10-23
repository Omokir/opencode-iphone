import SwiftUI
import Combine

@MainActor final class DocumentReceiver: ObservableObject {
    struct Incoming: Identifiable { let id = UUID(); let url: URL }
    static let shared = DocumentReceiver()
    @Published var incoming: Incoming?
    private var scoped = false
    func offer(_ url: URL) {
        guard url.isFileURL else { return }
        close()
        scoped = url.startAccessingSecurityScopedResource()
        incoming = Incoming(url: url)
    }
    func close() {
        if scoped, let incoming { incoming.url.stopAccessingSecurityScopedResource() }
        scoped = false; incoming = nil
    }
}

struct DocumentImportView: View {
    let item: DocumentReceiver.Incoming
    @EnvironmentObject var inbox: InboxSync
    @EnvironmentObject var api: API
    @State private var busy = false
    @State private var result: String?
    var body: some View {
        NavigationStack {
            Form {
                Section("Arquivo recebido") {
                    Text(item.url.lastPathComponent).font(.headline)
                    Text("Copiar para Iphone 11 Omoki, sem apagar arquivo de origem. Até 64 MiB por importação. Se pasta automática estiver ativa, cópia seguirá sua configuração de transferência e remoção.").font(.caption)
                    if inbox.enabledServer == api.server { Label("Pasta automática ativa neste notebook", systemImage: "arrow.up.doc").foregroundStyle(.orange) }
                    Button("Copiar para pasta do Pocket") { Task { await receive() } }.disabled(busy || result != nil)
                    if busy { ProgressView() }
                    if let result { Text(result).textSelection(.enabled) }
                }
            }.navigationTitle("Abrir no Pocket").navigationBarTitleDisplayMode(.inline)
                .toolbar { Button("Fechar") { DocumentReceiver.shared.close() }.disabled(busy) }
                .interactiveDismissDisabled(busy)
        }
    }
    func receive() async {
        busy = true; defer { busy = false }
        do {
            let staged = try await Task.detached(priority: .utility) { try PrivateTransferFiles.stage(item.url) }.value
            defer { try? FileManager.default.removeItem(at: staged.url) }
            var name = staged.name
            while name.utf8.count > 180 { name.removeLast() }
            let destination = try InboxSync.folder().appendingPathComponent(UUID().uuidString.lowercased() + "-" + name)
            try FileManager.default.setAttributes([.protectionKey: FileProtectionType.complete], ofItemAtPath: staged.url.path)
            // Publish complete private copy atomically within the app container,
            // never expose a partially copied file to the automatic inbox scan.
            try FileManager.default.moveItem(at: staged.url, to: destination)
            result = "Cópia recebida na pasta do Pocket. Origem preservada."
        } catch { result = "Não foi possível importar: \(error.localizedDescription). Origem preservada." }
    }
}
