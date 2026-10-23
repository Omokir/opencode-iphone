import Foundation
import Security

enum VoiceKey {
    private static var query: [String: Any] {
        [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: "com.omokir.opencodepocket.voice", kSecAttrAccount as String: "openai-api-key"]
    }
    static func read() -> String? {
        var q = query; q[kSecReturnData as String] = true; q[kSecMatchLimit as String] = kSecMatchLimitOne
        var item: CFTypeRef?
        guard SecItemCopyMatching(q as CFDictionary, &item) == errSecSuccess, let data = item as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }
    static func save(_ text: String) throws {
        let key = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard key.hasPrefix("sk-"), (20...512).contains(key.count), !key.contains(where: { $0.isWhitespace }) else { throw PhoneError.message("Cole somente chave OpenAI válida, sem prefixo Bearer.") }
        let attributes: [String: Any] = [kSecValueData as String: Data(key.utf8), kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly]
        let status = SecItemUpdate(query as CFDictionary, attributes as CFDictionary)
        if status == errSecItemNotFound {
            var q = query; attributes.forEach { q[$0.key] = $0.value }
            guard SecItemAdd(q as CFDictionary, nil) == errSecSuccess else { throw PhoneError.message("Não foi possível guardar chave no Chaves do iPhone.") }
        } else if status != errSecSuccess { throw PhoneError.message("Não foi possível atualizar chave.") }
    }
    static func clear() { SecItemDelete(query as CFDictionary) }
}
