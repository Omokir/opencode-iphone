import SwiftUI
import LocalAuthentication
import Combine

@MainActor final class PrivacyLock: ObservableObject {
    @Published private(set) var enabled = UserDefaults.standard.bool(forKey: "privacy.lock")
    @Published private(set) var unlocked = false
    @Published private(set) var authenticating = false
    @Published var error: String?
    private var context: LAContext?
    private var generation = UUID()
    var allowsAccess: Bool { !enabled || unlocked }

    func lock() { generation = UUID(); context?.invalidate(); context = nil; unlocked = false }
    func confirm(_ reason: String, force: Bool = false) async -> Bool {
        guard enabled || force else { return true }
        guard !authenticating else { return false }
        authenticating = true
        defer { authenticating = false; context = nil }
        let ticket = generation
        let ctx = LAContext(); context = ctx
        do {
            let accepted = try await ctx.evaluatePolicy(.deviceOwnerAuthentication, localizedReason: reason)
            guard generation == ticket else { return false }
            error = nil; return accepted
        } catch { self.error = "Autenticação não concluída. Tente novamente para acessar Pocket."; return false }
    }
    func unlock() async {
        guard enabled, !unlocked else { return }
        unlocked = await confirm("Desbloquear conversas e arquivos do OpenCode Pocket")
    }
    func setEnabled(_ value: Bool) async {
        guard await confirm(value ? "Ativar bloqueio do Pocket" : "Desativar bloqueio do Pocket", force: true) else { return }
        enabled = value; unlocked = value
        UserDefaults.standard.set(value, forKey: "privacy.lock")
    }
}

struct PocketLockView: View {
    @EnvironmentObject var privacy: PrivacyLock
    var body: some View {
        VStack(spacing: 20) {
            Image(systemName: "lock.shield").font(.system(size: 50)).foregroundStyle(Style.blue)
            Text("Pocket bloqueado").font(.title2.bold())
            Text("Use Face ID ou código do aparelho.").foregroundStyle(.secondary)
            Button("Desbloquear") { Task { await privacy.unlock() } }.buttonStyle(.borderedProminent).disabled(privacy.authenticating)
            if let error = privacy.error { Text(error).font(.caption).foregroundStyle(.red) }
        }.padding()
    }
}
