import SwiftUI

struct QuestionFormView: View {
    @EnvironmentObject var api: API
    @Environment(\.dismiss) var dismiss
    let question: QuestionForm
    let session: Session
    let answered: () -> Void
    @State private var answers: [String: JSONValue] = [:]
    @State private var custom: [String: String] = [:]
    @State private var busy = false
    @State private var error: String?
    var visible: [QuestionForm.Field] { question.fields.filter { question.visible($0, answers: answers) } }
    var supported: Bool { visible.allSatisfy { ["string", "boolean", "multiselect", "number", "integer"].contains($0.type) } }
    var body: some View {
        NavigationStack {
            Form {
                Section { Text(question.title).font(.headline).fixedSize(horizontal: false, vertical: true) }
                ForEach(visible) { field in
                    Section {
                        if let description = field.description { Text(description).font(.caption).foregroundStyle(.secondary) }
                        if field.type == "boolean" {
                            Toggle("Sim", isOn: Binding(get: { answers[field.key] == .bool(true) }, set: { answers[field.key] = .bool($0) }))
                        } else if field.type == "string" || field.type == "multiselect" {
                            ForEach(field.options ?? []) { option in
                                Button {
                                    if field.type == "multiselect" {
                                        var values = strings(field.key)
                                        if values.contains(option.value) { values.removeAll { $0 == option.value } } else { values.append(option.value) }
                                        answers[field.key] = .array(values.map { .string($0) })
                                    } else { answers[field.key] = .string(option.value) }
                                } label: {
                                    HStack(alignment: .top) {
                                        Image(systemName: selected(field, option.value) ? "checkmark.circle.fill" : "circle")
                                        VStack(alignment: .leading, spacing: 3) {
                                            Text(option.label).foregroundStyle(.primary)
                                            if let description = option.description { Text(description).font(.caption).foregroundStyle(.secondary) }
                                        }
                                    }.padding(.vertical, 3)
                                }
                            }
                            if field.options?.isEmpty != false || field.custom == true {
                                TextField(field.placeholder ?? (field.type == "multiselect" ? "Outras respostas, uma por linha" : "Sua resposta"), text: textBinding(field), axis: .vertical).lineLimit(2...6)
                            }
                        } else if field.type == "number" || field.type == "integer" {
                            TextField("Número", text: textBinding(field)).keyboardType(.numbersAndPunctuation)
                        } else {
                            Text("Este tipo de pergunta precisa ser respondido na interface do notebook.").foregroundStyle(.secondary)
                        }
                    } header: { Text((field.title ?? field.key) + (field.required == true ? " *" : "")) }
                }
                if let error { Section { Text(error).foregroundStyle(.red).textSelection(.enabled) } }
            }
            .disabled(busy)
            .navigationTitle("Responder à IA").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Fechar") { dismiss() }.disabled(busy) }
                ToolbarItem(placement: .confirmationAction) { Button("Enviar resposta") { Task { await submit() } }.disabled(busy || !supported) }
            }
            .overlay { if busy { ProgressView() } }
            .onAppear {
                for field in question.fields {
                    if let value = field.defaultValue { answers[field.key] = value }
                    else if field.type == "boolean" { answers[field.key] = .bool(false) }
                }
            }
        }
    }
    func strings(_ key: String) -> [String] {
        guard case .array(let values) = answers[key] else { return [] }
        return values.compactMap { if case .string(let text) = $0 { return text }; return nil }
    }
    func selected(_ field: QuestionForm.Field, _ value: String) -> Bool {
        field.type == "multiselect" ? strings(field.key).contains(value) : answers[field.key] == .string(value)
    }
    func textBinding(_ field: QuestionForm.Field) -> Binding<String> {
        Binding(get: {
            if field.type == "multiselect" { return custom[field.key] ?? "" }
            if case .string(let text) = answers[field.key] {
                return (field.options ?? []).contains { $0.value == text } ? "" : text
            }
            if case .number(let value) = answers[field.key] { return String(value) }
            return ""
        }, set: { text in
            if field.type == "multiselect" {
                custom[field.key] = text
                let listed = Set((field.options ?? []).map(\.value))
                var values = strings(field.key).filter { listed.contains($0) }
                for line in text.split(separator: "\n").map({ $0.trimmingCharacters(in: .whitespaces) }) where !line.isEmpty && !values.contains(line) { values.append(line) }
                answers[field.key] = .array(values.map { .string($0) })
            } else { answers[field.key] = .string(text) }
        })
    }
    func submit() async {
        busy = true
        defer { busy = false }
        do {
            var payload: [String: Any] = [:]
            for field in visible {
                var value = answers[field.key]
                if case .string(let text) = value, text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { value = nil }
                if case .array(let values) = value, values.isEmpty { value = nil }
                if field.required == true && value == nil { throw PhoneError.message("Responda: \(field.title ?? field.key).") }
                guard let value else { continue }
                if field.type == "number" || field.type == "integer" {
                    let number: Double?
                    if case .number(let n) = value { number = n }
                    else if case .string(let text) = value { number = Double(text.replacingOccurrences(of: ",", with: ".")) }
                    else { number = nil }
                    guard let number, number.isFinite, field.type != "integer" || number.rounded() == number else { throw PhoneError.message("Informe número válido em \(field.title ?? field.key).") }
                    payload[field.key] = number
                } else { payload[field.key] = value.object }
            }
            let _: EmptyResponse = try await api.request("/api/session/\(session.id)/form/\(question.id)/reply", method: "POST", body: ["answer": payload])
            answered()
            dismiss()
        } catch { self.error = error.localizedDescription }
    }
}
