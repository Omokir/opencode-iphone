import Foundation

struct VerifiedUpdate {
    let version: String
    let build: String
    let runID: Int
    let sha: String
    let expires: String
    var runURL: URL { URL(string: "https://github.com/Omokir/opencode-iphone/actions/runs/\(runID)")! }
    var notesURL: URL { URL(string: "https://github.com/Omokir/opencode-iphone/blob/\(sha)/README.md")! }
    func newer(than version: String, build: String) -> Bool {
        let order = self.version.compare(version, options: .numeric)
        return order == .orderedDescending || (order == .orderedSame && self.build.compare(build, options: .numeric) == .orderedDescending)
    }
    static func fetch() async throws -> VerifiedUpdate {
        let config = URLSessionConfiguration.ephemeral
        config.urlCache = nil; config.httpCookieStorage = nil; config.urlCredentialStorage = nil
        config.timeoutIntervalForRequest = 15; config.timeoutIntervalForResource = 30
        let network = URLSession(configuration: config); defer { network.invalidateAndCancel() }
        func read(_ url: String, limit: Int = 512 * 1024) async throws -> Data {
            var request = URLRequest(url: URL(string: url)!, cachePolicy: .reloadIgnoringLocalCacheData)
            if url.hasPrefix("https://api.github.com/") {
                request.setValue("application/vnd.github+json", forHTTPHeaderField: "Accept")
                request.setValue("2026-03-10", forHTTPHeaderField: "X-GitHub-Api-Version")
            }
            let (bytes, response) = try await network.bytes(for: request)
            guard (response as? HTTPURLResponse)?.statusCode == 200 else { throw PhoneError.message("GitHub não confirmou consulta pública. Confira conexão ou limite de consultas.") }
            var data = Data()
            for try await byte in bytes { guard data.count < limit else { throw PhoneError.message("Resposta de atualização excedeu limite.") }; data.append(byte) }
            return data
        }
        let prefix = "https://api.github.com/repos/Omokir/opencode-iphone/actions/"
        let runsData = try await read(prefix + "workflows/ios.yml/runs?status=success&branch=main&per_page=1")
        guard let runs = try JSONSerialization.jsonObject(with: runsData) as? [String: Any],
              let run = (runs["workflow_runs"] as? [[String: Any]])?.first,
              let id = run["id"] as? Int, id > 0, let sha = run["head_sha"] as? String, VerifiedBuildPolicy.validSHA(sha) else {
            throw PhoneError.message("Nenhum build concluído confirmado.")
        }
        let artifactsData = try await read(prefix + "runs/\(id)/artifacts?per_page=20")
        let object = try JSONSerialization.jsonObject(with: artifactsData) as? [String: Any]
        let artifacts = object?["artifacts"] as? [[String: Any]] ?? []
        guard VerifiedBuildPolicy.ready(run, artifacts: artifacts) else { throw PhoneError.message("Build existe, mas IPA não está disponível ou artefato expirou. Não é atualização pronta.") }
        let plist = try await read("https://raw.githubusercontent.com/Omokir/opencode-iphone/\(sha)/ios/Info.plist", limit: 65536)
        guard let info = try PropertyListSerialization.propertyList(from: plist, format: nil) as? [String: Any],
              let version = info["CFBundleShortVersionString"] as? String, version.count <= 24,
              version.allSatisfy({ $0.isASCII && ($0.isNumber || $0 == ".") }) else { throw PhoneError.message("Versão do artefato não confirmada no commit correspondente.") }
        guard let build = info["CFBundleVersion"] as? String, !build.isEmpty, build.count <= 12, build.allSatisfy({ $0.isASCII && $0.isNumber }) else { throw PhoneError.message("Número de build não confirmado.") }
        let expiry = artifacts.first(where: { $0["name"] as? String == "OpenCode-Pocket-iPhone" })?["expires_at"] as? String ?? "não informada"
        return VerifiedUpdate(version: version, build: build, runID: id, sha: sha, expires: String(expiry.prefix(40)))
    }
}
