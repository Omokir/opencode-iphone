import Foundation
import Security
import SwiftUI

struct ComputerProfile: Codable, Identifiable {
    let id: String
    var name: String
    let server: String
    let token: String
}

/// The whole registry lives in Keychain; tokens never enter UserDefaults.
enum ComputerVault {
    private static let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
        kSecAttrService as String: "com.omokir.opencodephone.computers", kSecAttrAccount as String: "profiles"]
    static func read() throws -> [ComputerProfile] {
        var q = query; q[kSecReturnData as String] = true; q[kSecMatchLimit as String] = kSecMatchLimitOne
        var item: CFTypeRef?
        let status = SecItemCopyMatching(q as CFDictionary, &item)
        if status == errSecItemNotFound { return [] }
        guard status == errSecSuccess, let data = item as? Data else { throw PhoneError.message("Cofre de computadores indisponível.") }
        return try JSONDecoder().decode([ComputerProfile].self, from: data)
    }
    static func save(_ profiles: [ComputerProfile]) throws {
        let data = try JSONEncoder().encode(profiles)
        let status = SecItemUpdate(query as CFDictionary, [kSecValueData as String: data] as CFDictionary)
        if status == errSecItemNotFound {
            var q = query; q[kSecValueData as String] = data
            q[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            guard SecItemAdd(q as CFDictionary, nil) == errSecSuccess else { throw PhoneError.message("Não foi possível salvar computadores no Chaves.") }
        } else if status != errSecSuccess { throw PhoneError.message("Não foi possível atualizar computadores no Chaves.") }
    }
}

struct ComputersView: View {
    @EnvironmentObject var api: API
    @Environment(\.dismiss) var dismiss
    @State private var name = ""
    @State private var address = ""
    @State private var code = ""
    @State private var busy = false
    @State private var error: String?
    var body: some View {
        NavigationStack {
            Form {
                Section("Computador ativo") {
                    Text(api.server).font(.caption).textSelection(.enabled)
                    Text("Pedidos, arquivos e KzL pertencem ao computador selecionado. Trocar interrompe acompanhamento local; tarefas já enviadas continuam na máquina anterior.").font(.caption)
                }
                Section("Meus computadores") {
                    ForEach(api.computers) { computer in
                        Button {
                            do { try api.selectComputer(computer.id); dismiss() }
                            catch { self.error = error.localizedDescription }
                        } label: {
                            HStack {
                                VStack(alignment: .leading) { Text(computer.name); Text(computer.server).font(.caption).foregroundStyle(.secondary) }
                                Spacer()
                                if computer.server == api.server { Image(systemName: "checkmark") }
                            }
                        }.disabled(busy)
                    }
                }
                Section("Adicionar computador") {
                    TextField("Nome do computador Linux", text: $name)
                    TextField("https://computador.…ts.net:8443", text: $address).textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.URL)
                    TextField("Código de pareamento", text: $code).keyboardType(.numberPad)
                    Button(busy ? "Pareando…" : "Parear e selecionar") {
                        busy = true
                        Task {
                            defer { busy = false }
                            do { try await api.addComputer(name: name, address: address, code: code); code = ""; dismiss() }
                            catch { self.error = error.localizedDescription }
                        }
                    }.disabled(busy || name.trimmingCharacters(in: .whitespaces).isEmpty || code.count != 6)
                }
                if let error { Text(error).foregroundStyle(.red) }
                Section { Text("Nesta etapa: iPhone e Linux. Cada computador precisa do conector Pocket ativo e Tailscale. Adicionar dispositivo não instala OpenCode nem habilita controle visual. Mac, Windows e Android ficam para etapas futuras.").font(.caption).foregroundStyle(.secondary) }
            }.navigationTitle("Computadores").toolbar { Button("Fechar") { dismiss() } }
        }
    }
}
