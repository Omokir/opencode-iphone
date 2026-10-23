import SwiftUI
import UniformTypeIdentifiers
import QuickLook
import Combine

struct PendingUpload: Identifiable {
    let file: StagedUpload
    let root: String
    let path: String
    var id: UUID { file.id }
}
struct FileReplacement: Identifiable {
    let pending: PendingUpload
    let existing: RemoteFile
    var id: UUID { pending.id }
}

@MainActor final class FileBrowserStore: ObservableObject {
    @Published var roots: [BrowserRoots.Root] = []
    @Published var root = "home"
    @Published var path = ""
    @Published var listing: BrowserListing?
    @Published var busy = false
    @Published var transferring = false
    @Published var error: String?
    @Published var notice: String?
    @Published var preview: LocalPreview?
    @Published var replacement: FileReplacement?
    @Published var unconfirmed: PendingUpload?
    private var task: Task<Void, Never>?

    func initialize(_ api: API, initial: String?) async {
        busy = true
        do {
            let result: BrowserRoots = try await api.request("/phone/files/roots")
            roots = result.roots
            guard let first = roots.first else { throw TransferFailure.message("Nenhuma pasta liberada no notebook.") }
            root = first.id
            if let initial {
                do {
                    let context: BrowserLocation = try await api.request("/phone/files/context?directory=" + API.escape(initial))
                    root = context.root; path = context.path
                } catch { notice = "Projeto fora das pastas liberadas; mostrando pasta pessoal." }
            }
        } catch { self.error = error.localizedDescription }
        busy = false
        if !roots.isEmpty { await load(api) }
    }
    func load(_ api: API) async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        if listing?.root != root || listing?.path != path { listing = nil }
        do {
            let result: BrowserListing = try await api.request("/phone/files/list?root=" + API.escape(root) + "&path=" + API.escape(path))
            listing = result
            error = nil
        } catch { self.error = error.localizedDescription }
    }
    func navigate(_ relative: String, api: API) async {
        guard !transferring && !busy else { return }
        path = relative
        listing = nil
        await load(api)
    }
    func download(_ file: RemoteFile, api: API) {
        guard !transferring else { return }
        let selectedRoot = root
        transferring = true
        error = nil
        notice = "Baixando \(file.name)… Mantenha app aberto."
        task = Task {
            defer { transferring = false; task = nil }
            do {
                preview = try await api.downloadFile(root: selectedRoot, file: file)
                notice = "Download verificado. Use Salvar/Compartilhar para guardar no app Arquivos."
            } catch { self.error = "Download não concluído: \(error.localizedDescription)"; notice = nil }
        }
    }
    func prepare(_ url: URL, api: API) {
        guard !transferring && !busy else { return }
        let selectedRoot = root
        let directory = path
        transferring = true
        error = nil
        notice = "Preparando cópia protegida do arquivo…"
        task = Task {
            defer { transferring = false; task = nil }
            do {
                let file = try await Task.detached(priority: .userInitiated) { try PrivateTransferFiles.stage(url) }.value
                try Task.checkCancellation()
                let target = directory.isEmpty ? file.name : directory + "/" + file.name
                let pending = PendingUpload(file: file, root: selectedRoot, path: target)
                if let existing = listing?.entries.first(where: { $0.name == file.name }) {
                    guard existing.kind == "file" && existing.readable && existing.version != nil else { throw TransferFailure.message("Destino protegido ou não é arquivo regular.") }
                    replacement = FileReplacement(pending: pending, existing: existing)
                    notice = "Aguardando confirmação de substituição. Nada foi enviado ainda."
                } else { await send(pending, expected: nil, api: api) }
            } catch { self.error = error.localizedDescription; notice = nil }
        }
    }
    func replace(_ value: FileReplacement, api: API) {
        guard !transferring, let version = value.existing.version else { return }
        replacement = nil
        transferring = true
        task = Task {
            await send(value.pending, expected: version, api: api)
            transferring = false; task = nil
        }
    }
    private func send(_ pending: PendingUpload, expected: String?, api: API) async {
        notice = "Enviando \(pending.file.name)… Mantenha app aberto."
        error = nil
        do {
            let receipt = try await api.uploadFile(pending.file, root: pending.root, path: pending.path, expected: expected)
            guard receipt.path == pending.path && receipt.root == pending.root else { throw TransferFailure.message("Destino do recibo não confere.") }
            unconfirmed = nil
            notice = "Enviado e verificado: \(pending.file.name)."
            await load(api)
        } catch TransferFailure.conflict(let existing, let message) {
            replacement = FileReplacement(pending: pending, existing: existing)
            notice = message
        } catch {
            unconfirmed = pending
            self.error = "Envio não confirmado: \(error.localizedDescription) Confira recibo e pasta antes de novo envio."
            notice = nil
        }
    }
    func verifyReceipt(_ api: API) async {
        guard let pending = unconfirmed else { return }
        do {
            let receipt: UploadReceipt = try await api.request("/phone/files/receipt?id=" + pending.id.uuidString)
            guard receipt.sha256 == pending.file.sha256 && receipt.root == pending.root && receipt.path == pending.path else { throw TransferFailure.message("Recibo não corresponde ao envio.") }
            unconfirmed = nil
            error = nil
            notice = "Recibo confirma envio concluído. Atualize pasta para verificar estado atual do arquivo."
            await load(api)
        } catch { self.error = "Sem confirmação: \(error.localizedDescription). Não reenvie automaticamente; confira pasta." }
    }
    func cancel() {
        task?.cancel()
        notice = "Cancelamento solicitado. Se envio já chegou ao notebook, arquivo pode ter sido gravado; confira pasta/recibo."
    }
}

struct FileBrowserView: View {
    @EnvironmentObject var api: API
    @EnvironmentObject var privacy: PrivacyLock
    @Environment(\.dismiss) var dismiss
    @StateObject private var store = FileBrowserStore()
    @State private var importing = false
    let initialDirectory: String?
    init(initialDirectory: String? = nil) { self.initialDirectory = initialDirectory }
    var body: some View {
        NavigationStack {
            List {
                Section {
                    if store.roots.count > 1 {
                        Picker("Pasta liberada", selection: $store.root) { ForEach(store.roots) { Text($0.name).tag($0.id) } }
                            .disabled(store.busy || store.transferring)
                    }
                    Text(store.roots.first(where: { $0.id == store.root })?.name ?? "Notebook").font(.headline)
                    Text(store.path.isEmpty ? "/" : "/" + store.path).font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                    if let parent = store.listing?.parent {
                        Button("Pasta acima", systemImage: "arrow.up.doc") { Task { await store.navigate(parent, api: api) } }.disabled(store.busy || store.transferring)
                    }
                }
                if store.transferring {
                    Section { HStack { ProgressView(); Text(store.notice ?? "Transferindo…").font(.caption) }; Button("Cancelar transferência", role: .destructive) { store.cancel() } }
                } else if let notice = store.notice { Section { Text(notice).font(.caption).foregroundStyle(.secondary) } }
                if let error = store.error {
                    Section {
                        Text(error).foregroundStyle(.red).textSelection(.enabled)
                        Button("Atualizar pasta") { Task { await store.load(api) } }.disabled(store.transferring)
                    }
                }
                if store.unconfirmed != nil {
                    Section {
                        Text("Último envio ainda não confirmado. Atualizar pasta não equivale a confirmar recibo.").font(.caption).foregroundStyle(.orange)
                        Button("Conferir recibo do último envio") { Task { await store.verifyReceipt(api) } }
                    }
                }
                Section("Arquivos e pastas") {
                    ForEach(store.listing?.entries ?? []) { file in
                        Button {
                            if file.kind == "directory" { Task { await store.navigate(file.path, api: api) } }
                            else { store.download(file, api: api) }
                        } label: {
                            HStack(alignment: .top, spacing: 12) {
                                Image(systemName: !file.readable ? "lock" : file.kind == "directory" ? "folder" : "doc").frame(width: 24)
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(file.name).foregroundStyle(.primary).lineLimit(2)
                                    if !file.readable { Text("Protegido, link ou tipo não suportado").font(.caption).foregroundStyle(.secondary) }
                                    else if let size = file.size { Text(ByteCountFormatter.string(fromByteCount: size, countStyle: .file)).font(.caption).foregroundStyle(.secondary) }
                                }
                                Spacer()
                                Image(systemName: file.kind == "directory" ? "chevron.right" : "arrow.down.circle")
                            }.padding(.vertical, 3)
                        }.disabled(!file.readable || store.busy || store.transferring)
                    }
                    if store.listing?.entries.isEmpty == true { Text("Pasta vazia ou itens ocultos/protegidos.").foregroundStyle(.secondary) }
                    if store.listing?.truncated == true { Text("Pasta grande: até 2.000 itens nesta consulta.").font(.caption).foregroundStyle(.secondary) }
                }
                Section {
                    Text("Até 64 MB por transferência. Downloads ficam em cache protegido; salve em Arquivos para guardar. Envios não são executados pelo explorador. Pastas ocultas, links e credenciais comuns são bloqueados. Sem apagar arquivos nesta versão.")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Arquivos do notebook").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) { Button("Fechar") { dismiss() }.disabled(store.transferring) }
                ToolbarItem(placement: .topBarTrailing) { Button("Enviar arquivo", systemImage: "square.and.arrow.up") { importing = true }.disabled(store.busy || store.transferring || store.listing == nil) }
            }
            .overlay { if store.busy { ProgressView() } }
            .interactiveDismissDisabled(store.transferring)
            .refreshable { await store.load(api) }
            .task { await store.initialize(api, initial: initialDirectory) }
            .onChange(of: store.root) { _, _ in if !store.busy { Task { await store.navigate("", api: api) } } }
            .fileImporter(isPresented: $importing, allowedContentTypes: [.item]) { result in
                switch result {
                case .success(let url): store.prepare(url, api: api)
                case .failure(let error): if (error as NSError).code != NSUserCancelledError { store.error = error.localizedDescription }
                }
            }
            .sheet(item: $store.preview) { FilePreviewView(file: $0) }
            .alert("Substituir arquivo existente?", isPresented: Binding(get: { store.replacement != nil }, set: { if !$0 { store.replacement = nil } }), presenting: store.replacement) { replacement in
                Button("Substituir", role: .destructive) { Task { if await privacy.confirm("Substituir arquivo no computador") { store.replace(replacement, api: api) } } }
                Button("Cancelar", role: .cancel) { store.replacement = nil; store.notice = "Substituição cancelada; destino não foi alterado." }
            } message: { replacement in Text("\(replacement.existing.name) já existe nesta pasta. Conteúdo atual será substituído; app não oferece desfazer. Se versão mudar, será necessário confirmar novamente.") }
        }
    }
}

struct FilePreviewView: View {
    @Environment(\.dismiss) var dismiss
    let file: LocalPreview
    var body: some View {
        NavigationStack {
            QuickFilePreview(url: file.url)
                .navigationTitle(file.name).navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .topBarLeading) { Button("Fechar") { dismiss() } }
                    ToolbarItem(placement: .topBarTrailing) { ShareLink(item: file.url) { Label("Salvar/Compartilhar", systemImage: "square.and.arrow.up") } }
                }
        }
    }
}
struct QuickFilePreview: UIViewControllerRepresentable {
    let url: URL
    func makeCoordinator() -> Coordinator { Coordinator(url: url) }
    func makeUIViewController(context: Context) -> QLPreviewController {
        let controller = QLPreviewController(); controller.dataSource = context.coordinator; return controller
    }
    func updateUIViewController(_ controller: QLPreviewController, context: Context) { }
    final class Coordinator: NSObject, QLPreviewControllerDataSource {
        let url: URL
        init(url: URL) { self.url = url }
        func numberOfPreviewItems(in controller: QLPreviewController) -> Int { 1 }
        func previewController(_ controller: QLPreviewController, previewItemAt index: Int) -> QLPreviewItem { url as NSURL }
    }
}
