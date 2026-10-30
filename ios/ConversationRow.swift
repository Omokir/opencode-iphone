import SwiftUI

struct ConversationRow: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.scenePhase) private var phase
    let session: Session
    let pinned: Bool
    let unread: Bool
    let running: Bool
    let togglePin: () -> Void
    var body: some View {
        NavigationLink(value: session) {
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 5) {
                    Text(session.isKzL ? "Agente KzL" : session.title ?? "Sem título").font(.body.weight(.medium)).lineLimit(1)
                    Text(URL(fileURLWithPath: session.location.directory).lastPathComponent).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                }.padding(.vertical, 5)
                Spacer(minLength: 0)
                if pinned { Image(systemName: "pin.fill").font(.caption).foregroundStyle(Style.blue).accessibilityHidden(true) }
                if running {
                    Image(systemName: "circle.fill").font(.system(size: 10)).foregroundStyle(.green)
                        .symbolEffect(.pulse, isActive: !reduceMotion && phase == .active)
                        .frame(width: 12, height: 12).accessibilityHidden(true)
                } else if unread { Circle().fill(Style.blue).frame(width: 9, height: 9).accessibilityHidden(true) }
            }
        }
        .listRowSeparator(.hidden)
        .accessibilityValue([pinned ? "Fixada" : nil, running ? "Em execução no notebook" : unread ? "Resposta não lida" : nil].compactMap { $0 }.joined(separator: ". "))
        .swipeActions(edge: .leading, allowsFullSwipe: true) {
            Button(pinned ? "Desafixar" : "Fixar", systemImage: pinned ? "pin.slash" : "pin", action: togglePin).tint(Style.blue)
        }
        .contextMenu {
            Button(pinned ? "Desafixar conversa" : "Fixar conversa", systemImage: pinned ? "pin.slash" : "pin", action: togglePin)
        }
    }
}
