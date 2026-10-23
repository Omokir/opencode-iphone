import SwiftUI

enum MessageBlock: Equatable {
    case prose(String), code(String, String), table([[String]])
    static func parse(_ text: String) -> [MessageBlock] {
        let lines = text.components(separatedBy: "\n")
        var result: [MessageBlock] = [], prose: [String] = []
        func cells(_ row: String) -> [String] {
            var parts = row.split(separator: "|", omittingEmptySubsequences: false).map { $0.trimmingCharacters(in: .whitespaces) }
            if parts.first == "" { parts.removeFirst() }; if parts.last == "" { parts.removeLast() }
            return parts
        }
        func flush() { if !prose.isEmpty { result.append(.prose(prose.joined(separator: "\n"))); prose = [] } }
        var i = 0
        while i < lines.count {
            if lines[i].hasPrefix("```") {
                flush(); let language = String(lines[i].dropFirst(3)); i += 1
                var code: [String] = []
                while i < lines.count && !lines[i].hasPrefix("```") { code.append(lines[i]); i += 1 }
                result.append(.code(language, code.joined(separator: "\n")))
                if i < lines.count { i += 1 }
            } else if i + 1 < lines.count, lines[i].contains("|"), lines[i+1].contains("|"),
                      cells(lines[i+1]).allSatisfy({ $0.replacingOccurrences(of: ":", with: "").count >= 3 && $0.allSatisfy { $0 == "-" || $0 == ":" || $0 == " " } }) {
                flush(); var rows = [cells(lines[i])]; i += 2
                while i < lines.count && lines[i].contains("|") { rows.append(cells(lines[i])); i += 1 }
                result.append(.table(rows))
            } else { prose.append(lines[i]); i += 1 }
        }
        flush(); return result
    }
}

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
