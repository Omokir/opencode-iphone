import Foundation

/// Read-only feasibility probe. No screen, session creation or arbitrary URL.
enum LocalAgentProbe {
    private final class NoRedirect: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
        func urlSession(_ session: URLSession, task: URLSessionTask,
                        willPerformHTTPRedirection response: HTTPURLResponse,
                        newRequest request: URLRequest,
                        completionHandler: @escaping @Sendable (URLRequest?) -> Void) {
            completionHandler(nil)
        }
    }

    static func check() async -> String {
        let config = URLSessionConfiguration.ephemeral
        config.urlCache = nil
        config.urlCredentialStorage = nil
        config.httpCookieStorage = nil
        config.httpShouldSetCookies = false
        config.connectionProxyDictionary = [:]
        config.timeoutIntervalForRequest = 3
        config.timeoutIntervalForResource = 5
        config.waitsForConnectivity = false
        let transport = URLSession(configuration: config, delegate: NoRedirect(), delegateQueue: nil)
        defer { transport.invalidateAndCancel() }
        do {
            var request = URLRequest(url: URL(string: "http://localhost:8100/status")!, cachePolicy: .reloadIgnoringLocalCacheData)
            request.setValue("application/json", forHTTPHeaderField: "Accept")
            let (bytes, response) = try await transport.bytes(for: request)
            guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
                return "Serviço local não confirmou estado do agente. Ponte não habilitada."
            }
            var data = Data()
            for try await byte in bytes {
                try Task.checkCancellation()
                guard data.count < 16384 else { return "Resposta local excedeu limite; teste interrompido." }
                data.append(byte)
            }
            return AgentProbeResponse.isReady(data)
                ? "Agente respondeu neste iPhone. Isso ainda não comprova controle remoto nem funcionamento em segundo plano."
                : "Serviço respondeu, mas não confirmou agente pronto. Ponte não habilitada."
        } catch is CancellationError {
            return "Teste cancelado."
        } catch let error as URLError {
            switch error.code {
            case .appTransportSecurityRequiresSecureConnection:
                return "iOS bloqueou conexão local de diagnóstico. Ponte não habilitada."
            case .timedOut:
                return "Agente local não respondeu no prazo. Não remova cabo para iniciar nova sessão."
            case .cancelled:
                return "Teste cancelado."
            default:
                return "Agente não acessível dentro do iPhone. Estar online no Tailscale não basta para controlar tela."
            }
        } catch {
            return "Não foi possível validar agente local. Nenhum comando de controle enviado."
        }
    }
}
