import Foundation

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
                      cells(lines[i+1]).count == cells(lines[i]).count,
                      cells(lines[i+1]).allSatisfy({ $0.replacingOccurrences(of: ":", with: "").count >= 3 && $0.allSatisfy { $0 == "-" || $0 == ":" || $0 == " " } }) {
                flush(); var rows = [cells(lines[i])]; i += 2
                while i < lines.count && lines[i].contains("|") { rows.append(cells(lines[i])); i += 1 }
                result.append(.table(rows))
            } else { prose.append(lines[i]); i += 1 }
        }
        flush(); return result
    }
}
