import SwiftUI

struct ChatOptionsView: View {
    @EnvironmentObject var api: API
    @Environment(\.dismiss) var dismiss
    @Binding var session: Session
    @State private var catalog: Catalog?
    @State private var title = ""
    @State private var agent = "build"
    @State private var modelKey = ""
    @State private var variant = ""
    @State private var choosingModel = false
    @State private var busy = false
    @State private var loaded = false
    @State private var error: String?

    var selected: CatalogModel? { catalog?.models.first { $0.key == modelKey } }
    var body: some View {
        NavigationStack {
            Form {
                Section("Nome da conversa") {
                    TextField("Nome do chat", text: $title, axis: .vertical).lineLimit(1...3)
                }
                Section {
                    Picker("Modo", selection: $agent) {
                        ForEach(catalog?.agents ?? []) { choice in Text(choice.name).tag(choice.id) }
                    }
                    Text(agent == "plan" ? "Plan: analisa e prepara plano com restrições do agente configuradas no notebook." : "Build: pode executar tarefas e alterar arquivos conforme permissões do notebook.")
                        .font(.caption).foregroundStyle(.secondary)
                } header: { Text("Agente") }
                Section {
                    Button { choosingModel = true } label: {
                        HStack {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(selected?.name ?? session.model?.id ?? "Selecionar modelo").foregroundStyle(.primary)
                                Text(selected?.providerID ?? session.model?.providerID ?? "").font(.caption).foregroundStyle(.secondary)
                            }
                            Spacer()
                            Image(systemName: "chevron.right").foregroundStyle(.secondary)
                        }
                    }
                    if let selected, !selected.variants.isEmpty {
                        Picker("Variante", selection: $variant) {
                            Text("Padrão").tag("")
                            ForEach(selected.variants) { value in Text(value.id).tag(value.id) }
                        }
                    }
                    Text("Modelos usam contas do notebook e podem gerar custos. Estar listado não garante que chave ou saldo estejam válidos.")
                        .font(.caption).foregroundStyle(.secondary)
                } header: { Text("Modelo desta conversa") }
                Section("Workspace") {
                    Label("No notebook", systemImage: "laptopcomputer")
                    Text(session.location.directory).font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                }
                if let error { Section { Text(error).foregroundStyle(.red).textSelection(.enabled) } }
            }
            .disabled(busy)
            .navigationTitle("Ajustes do chat").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancelar") { dismiss() }.disabled(busy) }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Salvar") { Task { await save() } }.disabled(busy || !loaded || title.count > 200)
                }
            }
            .overlay { if busy { ProgressView() } }
            .sheet(isPresented: $choosingModel) {
                ModelPickerView(models: catalog?.models ?? [], selection: modelKey) { model in
                    if modelKey != model.key { variant = "" }
                    modelKey = model.key
                    choosingModel = false
                }
            }
            .task {
                title = session.title ?? ""
                agent = session.agent ?? "build"
                modelKey = session.model?.key ?? ""
                variant = session.model?.variant == "default" ? "" : session.model?.variant ?? ""
                do {
                    catalog = try await api.request("/phone/catalog?directory=" + API.escape(session.location.directory))
                    loaded = true
                } catch { self.error = error.localizedDescription }
            }
        }
    }

    func save() async {
        busy = true
        defer { busy = false }
        do {
            let trimmed = title.trimmingCharacters(in: .whitespacesAndNewlines)
            if trimmed != (session.title ?? "") {
                guard !trimmed.isEmpty else { throw PhoneError.message("Informe nome para conversa.") }
                let _: EmptyResponse = try await api.request("/api/session/\(session.id)", method: "PATCH", body: ["title": trimmed])
            }
            let agentChanged = agent != (session.agent ?? "build")
            if agentChanged {
                let _: EmptyResponse = try await api.request("/api/session/\(session.id)/agent", method: "POST", body: ["agent": agent])
            }
            let previousVariant = session.model?.variant == "default" ? "" : session.model?.variant ?? ""
            if let selected, agentChanged || selected.key != session.model?.key || variant != previousVariant {
                let model = Session.Model(providerID: selected.providerID, id: selected.id, variant: variant.isEmpty ? nil : variant)
                let _: EmptyResponse = try await api.request("/api/session/\(session.id)/model", method: "POST", body: ["model": model.payload])
            }
            let refreshed: Item<Session> = try await api.request("/api/session/\(session.id)")
            session = refreshed.data
            dismiss()
        } catch {
            self.error = "Não foi possível salvar tudo: \(error.localizedDescription) Confira valores antes de tentar novamente."
            if let refreshed: Item<Session> = try? await api.request("/api/session/\(session.id)") { session = refreshed.data }
        }
    }
}

struct ModelPickerView: View {
    @Environment(\.dismiss) var dismiss
    let models: [CatalogModel]
    let selection: String
    let choose: (CatalogModel) -> Void
    @State private var search = ""
    var matching: [CatalogModel] {
        models.filter { search.isEmpty || ($0.name + " " + $0.providerID + " " + $0.id).localizedCaseInsensitiveContains(search) }
    }
    var body: some View {
        NavigationStack {
            List {
                ForEach(Array(Set(matching.map(\.providerID))).sorted(), id: \.self) { provider in
                    Section(provider) {
                        ForEach(matching.filter { $0.providerID == provider }.sorted { $0.name < $1.name }, id: \.key) { model in
                            Button { choose(model) } label: {
                                HStack {
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text(model.name).foregroundStyle(.primary)
                                        Text(model.capabilities.input.joined(separator: " · ")).font(.caption).foregroundStyle(.secondary)
                                    }
                                    Spacer()
                                    if model.key == selection { Image(systemName: "checkmark") }
                                }
                            }
                        }
                    }
                }
            }
            .searchable(text: $search, prompt: "Modelo ou provedor")
            .navigationTitle("Selecionar modelo").navigationBarTitleDisplayMode(.inline)
            .toolbar { Button("Voltar") { dismiss() } }
        }
    }
}
