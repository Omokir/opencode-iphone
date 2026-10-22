import SwiftUI

struct ConversationRow: View {
    let session: Session
    let pinned: Bool
    let unread: Bool
    let togglePin: () -> Void
    var body: some View {
        NavigationLink(value: session) {
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 5) {
                    Text(session.title ?? "Sem título").font(.headline).lineLimit(2)
                    Text(session.location.directory).font(.system(.caption, design: .monospaced)).foregroundStyle(.secondary).lineLimit(1)
                }.padding(.vertical, 5)
                Spacer(minLength: 0)
                if pinned { Image(systemName: "pin.fill").font(.caption).foregroundStyle(Style.blue).accessibilityHidden(true) }
                if unread { Circle().fill(Style.blue).frame(width: 9, height: 9).accessibilityHidden(true) }
            }
        }
        .accessibilityValue([pinned ? "Fixada" : nil, unread ? "Resposta não lida" : nil].compactMap { $0 }.joined(separator: ". "))
        .swipeActions(edge: .leading, allowsFullSwipe: true) {
            Button(pinned ? "Desafixar" : "Fixar", systemImage: pinned ? "pin.slash" : "pin", action: togglePin).tint(Style.blue)
        }
        .contextMenu {
            Button(pinned ? "Desafixar conversa" : "Fixar conversa", systemImage: pinned ? "pin.slash" : "pin", action: togglePin)
        }
    }
}
