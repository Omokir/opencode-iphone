import Foundation

@main struct CachePolicyTests {
    static func main() {
        precondition(HistoryCache.allowed("/api/session?limit=30&order=desc"))
        precondition(HistoryCache.allowed("/api/session/ses_test/message?limit=50&order=desc"))
        for path in ["/api/config", "/api/session/active", "/phone/devices", "/api/session/ses_test/permission", "/api/session/ses_test/form", "/api/session?search=private", "/api/session/ses_test/message?cursor=old", "/api/session/ses_test/message?type=assistant"] {
            precondition(!HistoryCache.allowed(path))
        }
        precondition(HistoryCache.key("host-a|ses_test") != HistoryCache.key("host-b|ses_test"))
        precondition(ConnectionAdvice.describe(URLError(.cannotFindHost)).contains("DNS"))
        precondition(ConnectionAdvice.describe(URLError(.timedOut)).contains("prazo"))
        print("PASS: cache scope excludes permissions/secrets, server isolation, DNS/timeout advice")
    }
}
