import SwiftUI

struct KzLCallScreen: View {
    @EnvironmentObject var api: API
    @ObservedObject var call = KzLCallCoordinator.shared
    @ObservedObject var voice = KzLCallCoordinator.shared.voice
    @Environment(\.dismiss) private var dismiss
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var activity = false
    var body: some View {
        ZStack {
            LinearGradient(colors: [Color(red: 0.12, green: 0.03, blue: 0.05), Color(red: 0.04, green: 0.04, blue: 0.06)], startPoint: .topLeading, endPoint: .bottomTrailing).ignoresSafeArea()
            VStack(spacing: 24) {
                HStack { Button("Minimizar", systemImage: "arrow.down.right.and.arrow.up.left") { call.presented = false; dismiss() }; Spacer() }
                Spacer()
                KzLAvatar(active: voice.active)
                    .frame(width: 144, height: 144)
                Text("Agente KzL").font(.largeTitle.weight(.semibold))
                Text(voice.status).font(.title3).multilineTextAlignment(.center)
                Text("\(voice.elapsedSeconds / 60):\(String(format: "%02d", voice.elapsedSeconds % 60))").monospacedDigit()
                if let error = voice.error ?? call.error { Text(error).foregroundStyle(.orange).font(.caption) }
                if !voice.caption.isEmpty { ScrollView { Text(voice.caption).textSelection(.enabled) }.frame(maxHeight: 150) }
                Text(voice.notebook).font(.caption).foregroundStyle(.secondary)
                Button("Atividade do computador", systemImage: "desktopcomputer") { activity = true }
                Spacer()
                HStack(spacing: 30) {
                    VStack { AudioRoutePicker().frame(width: 60, height: 60); Text("Áudio").font(.caption) }
                    Button { call.end(); call.presented = false; dismiss() } label: {
                        Image(systemName: "phone.down.fill").font(.title).foregroundStyle(.white).frame(width: 76, height: 76).background(.red, in: Circle())
                    }.accessibilityLabel("Encerrar ligação")
                    Button { voice.setMuted(!voice.muted) } label: {
                        VStack { Image(systemName: voice.muted ? "mic.slash.fill" : "mic.fill").font(.title).frame(width: 60, height: 60); Text(voice.muted ? "Ativar" : "Silenciar").font(.caption) }
                    }
                }
                Text("Chamada de saída · áudio em segundo plano em validação").font(.caption2).foregroundStyle(.secondary)
            }.padding(24)
        }.preferredColorScheme(.dark).tint(.red)
            .sheet(isPresented: $activity) { NavigationStack { KzLTasksView().toolbar { Button("Fechar") { activity = false } } } }
    }
}

struct KzLAvatar: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    var active = false
    var body: some View {
        ZStack {
            Circle().fill(Color(red: 0.10, green: 0.10, blue: 0.13))
            if let image = UIImage(named: "KzL") {
                Image(uiImage: image).resizable().scaledToFit().clipShape(Circle())
            } else {
                // Original artwork is intentionally not reconstructed from a screenshot.
                Text("KzL").font(.system(size: 36, weight: .bold, design: .rounded)).foregroundStyle(.red)
            }
        }.overlay(Circle().stroke(.red.opacity(active ? 0.8 : 0.2), lineWidth: 2))
            .accessibilityLabel(active ? "KzL conectado" : "KzL")
    }
}
