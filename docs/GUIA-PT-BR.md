# OpenCode Pocket — instalação e uso

Cliente nativo para acessar **OpenCode V2 já rodando no computador**. Não executa
OpenCode no iPhone. Requer iOS 17+, computador Linux ligado, Python 3, OpenCode V2
com serviço gerenciado e Tailscale nos dois aparelhos. Projeto independente.

## 1. Preparar computador

Instale OpenCode V2 conforme documentação oficial: https://opencode.ai/v2/docs/.
Configure e autentique seu provedor no computador. Confirme que serviço está
ativo com `opencode service status`. Este gateway depende dessa interface V2 e
do arquivo local `~/.config/opencode/service.json`; versões incompatíveis podem
exigir adaptação. Não publique esse arquivo nem sua saída completa.

```bash
git clone https://github.com/Omokir/opencode-iphone.git
cd opencode-iphone
python3 -m unittest discover -s bridge -q
python3 bridge/server.py
```

Servidor escuta somente `127.0.0.1:49375`. Primeiro teste pode ficar no terminal;
para uso contínuo, crie `~/.config/systemd/user/opencode-iphone-bridge.service`:

```ini
[Unit]
Description=OpenCode Pocket private gateway
After=network.target

[Service]
ExecStart=/usr/bin/python3 %h/opencode-iphone/bridge/server.py
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
```

**Ajuste caminho em ExecStart para pasta real do clone.** Serviço precisa encontrar
`opencode` e, opcionalmente, `codex` no PATH. Se CLI foi instalada numa pasta local,
configure PATH no serviço usando caminhos absolutos do seu computador.
Pare servidor do terminal antes de iniciar serviço na mesma porta.

```bash
systemctl --user daemon-reload
systemctl --user enable --now opencode-iphone-bridge.service
```

## 2. Rede privada

Conecte computador e iPhone ao mesmo ambiente Tailscale. Ative HTTPS/MagicDNS
conforme instruções Tailscale e confira configuração existente antes de alterar:

```bash
tailscale serve status
tailscale serve --bg --https=8443 http://127.0.0.1:49375
```

Use URL HTTPS do computador exibida pelo Tailscale, com porta `8443`.
Não use `localhost` no iPhone. Não ative **Funnel**, não exponha gateway na internet
e não resete rotas Serve existentes. Aprovações administrativas, quando necessárias,
devem ser feitas por você. ACLs do Tailscale devem limitar acesso aos seus aparelhos.

## 3. Compilar e instalar app

No macOS com Xcode e Command Line Tools:

```bash
bash scripts/build-ios.sh
python3 scripts/validate-ipa.py build/OpenCode-Pocket-unsigned.ipa
```

Alternativa: faça fork, habilite GitHub Actions e execute workflow **Build iPhone**.
Baixe artefato **OpenCode-Pocket-iPhone** e extraia IPA. CI usa dados sintéticos,
não precisa de credenciais Apple nem tokens dos seus provedores.

IPA é **não assinado**. Assine e instale com ferramenta de sideload compatível,
como iLoader, seguindo instruções oficiais dessa ferramenta. Apple ID pertence
somente ao assinador; nunca coloque senha/certificados no repositório ou CI.
Assinatura gratuita costuma expirar em 7 dias e está sujeita aos limites Apple.
Confiança no desenvolvedor e modo Desenvolvedor podem ser necessários no iPhone.
Validador verifica estrutura do IPA, não assinatura nem instalação física.

Para atualizar, mantenha identificador `com.omokir.opencodepocket` e mesma identidade
de assinatura; instale por cima. Não apague app se quiser preservar dados locais.

## 4. Parear

No computador, dentro do clone:

```bash
python3 bridge/pair.py
```

No Pocket, informe URL HTTPS privada e código temporário mostrado no terminal.
Não compartilhe código nem token. Estado privado fica fora do clone, em
`~/.local/state/opencode-iphone/`. Para revogar todos os clientes, remova ou
substitua `token.secret` nesse diretório. Desconectar no app limpa apenas token
daquele aparelho; não revoga outros clientes.

## 5. Usar

- **Lupa:** procura nomes no servidor, inclusive além da primeira página. Fixadas
  correspondentes aparecem primeiro. Limpar texto restaura lista normal.
- **Nova conversa:** informe caminho absoluto existente no computador, por exemplo
  `/home/seu-usuario/projetos/meu-projeto` — não é pasta do iPhone.
- **Plan/Build e modelos:** escolha no chat; provedor precisa estar autenticado.
  Uso de modelos pode gerar custos. Permissões continuam exigindo revisão.
- **Anexos:** até cinco, 4 MB cada e 8 MB total no chat. Enviados ao computador e
  provedor somente quando você toca Enviar. Confira suporte do modelo.
- **Pasta:** baixar/enviar arquivos até 64 MiB; substituir exige confirmação.
  Por padrão, somente pasta pessoal, sem ocultos, links e credenciais comuns.
  Proteção não é antivírus nem sandbox contra programas do computador.
- **Rascunhos/fixadas/não lidas:** estado local por aparelho/servidor. Nada é
  reenviado automaticamente. Confira conversa antes de repetir envio incerto.
- **Histórico:** abertura traz 15 mensagens; carregue anteriores quando necessário.
  Eventos ao vivo funcionam em primeiro plano; não há push garantido.

## 6. Recursos opcionais e limites

Bateria depende de Linux power_supply; desktop sem bateria pode informar indisponível.
Cota Codex depende de CLI compatível e conta autenticada, não representa saldo API.
Modo manter acordado depende da integração local; não acorda computador já suspenso.

**Controle de iPhone é avançado e não vem funcional apenas clonando este projeto.**
Exige helper externo compatível, assinatura de componentes de automação, USB,
aparelho desbloqueado e integração de consentimento do notebook. Fork/helper local
usado no desenvolvimento não está distribuído neste repositório. Não prometa
controle com instalação padrão. Veja [limites do controle](PHONE-CONTROL.md).

## Problemas comuns

- **Hostname não encontrado:** DNS/VPN; reconecte Tailscale, confira MagicDNS e URL.
  Versão atual não corrige automaticamente todas as falhas DNS do iOS.
- **Sem conexão:** computador ligado, serviço ativo, Tailscale e porta 8443.
  PC funcionar localmente não confirma conexão do iPhone.
- **Código expirou:** gere outro localmente. Não publique logs com códigos/tokens.
- **App parou de abrir:** confira validade da assinatura e renove sem apagar dados.
- **Envio incerto:** confira chat, pasta ou recibo; não repita cegamente.

Segurança: parear concede acesso relevante aos arquivos e ferramentas do usuário
do computador. Use apenas aparelhos confiáveis. Não publique chats, logs, arquivos
de configuração privados, IPA pessoalmente assinado nem perfis Apple.
