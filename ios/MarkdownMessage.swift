import SwiftUI

struct MarkdownMessage: View {
    let text: String
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            ForEach(Array(MessageBlock.parse(text).enumerated()), id: \.offset) { _, block in
                switch block {
                case .prose(let value): Text(.init(value)).textSelection(.enabled)
                case .code(let language, let value):
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            Text(language.isEmpty ? "Código" : language).font(.caption).foregroundStyle(.secondary)
                            Spacer()
                            Button("Copiar", systemImage: "doc.on.doc") { UIPasteboard.general.string = value }.font(.caption)
                        }
                        ScrollView(.horizontal) { Text(value).font(.system(.footnote, design: .monospaced)).textSelection(.enabled).fixedSize(horizontal: true, vertical: false) }
                    }.padding(12).background(Style.paper, in: RoundedRectangle(cornerRadius: 10))
                case .table(let rows):
                    ScrollView(.horizontal) {
                        Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 10) {
                            ForEach(Array(rows.enumerated()), id: \.offset) { index, cells in
                                GridRow { ForEach(Array(cells.enumerated()), id: \.offset) { _, cell in
                                    Text(.init(cell)).font(index == 0 ? .subheadline.weight(.semibold) : .subheadline).textSelection(.enabled).frame(maxWidth: 260, alignment: .leading)
                                } }
                                if index == 0 { Divider().gridCellColumns(rows.first?.count ?? 1) }
                            }
                        }.padding(10)
                    }.background(Style.paper, in: RoundedRectangle(cornerRadius: 10))
                }
            }
        }
    }
}
