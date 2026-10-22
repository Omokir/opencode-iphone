# Instalar OpenCode Pocket no seu iPhone

## 1. Instalar aplicativo nativo

1. Conecte iPhone por cabo, desbloqueie e aceite **Confiar neste computador**.
2. Abra iLoader pelo instalador que você já usou com Mina de Bolso.
3. Use **Import IPA** e escolha `OpenCode-Pocket-unsigned.ipa`.
4. Informe sua conta Apple diretamente no iLoader. Não envie senha pelo chat.
5. Se solicitado, habilite **Ajustes → Privacidade e Segurança → Modo de Desenvolvedor**.
6. Autorize desenvolvedor em **Ajustes → Geral → VPN e Gerenciamento de Dispositivo**, se necessário.

IPA compilado sem assinatura não instala sozinho por Safari ou Arquivos.
Conta Apple gratuita normalmente exige renovar assinatura a cada sete dias.

## 2. Conectar ao notebook

1. Ative **Tailscale** no iPhone usando mesma rede privada do notebook.
2. No notebook, clique com botão direito em **iPhone OFF/ON** na barra superior.
   Alternativa: procure **Conectar iPhone ao OpenCode** no menu de aplicativos.
3. Copie endereço HTTPS exibido e código de seis dígitos para OpenCode Pocket.
4. Toque **Conectar**. Código vale cinco minutos e só pode ser usado uma vez.

Aplicativo conecta ao mesmo serviço OpenCode do notebook. Conversas existentes
aparecem; novas conversas usam pasta escolhida no notebook. Respostas atualizam
enquanto app está aberto. Sem notificações push nesta versão.

## 3. Usar com tampa fechada

- Clique com botão esquerdo em **iPhone OFF** para ativar modo; fica **iPhone ON**.
- Também pode ativar em **Ajustes → Manter notebook acordado** no aplicativo.
- Ative antes de fechar tampa. App não acorda notebook já suspenso.
- Mantenha notebook ventilado, preferencialmente ligado à tomada.
- Desligar modo restaura configurações de energia anteriores; se notebook
  suspender, acesso ficará indisponível até acordá-lo.

Não há porta pública: acesso usa HTTPS privado do Tailscale. Não é necessário
abrir portas no roteador. Notebook continua precisando de rede e energia.

## Atualização 0.2.0

No chat, use botões **Plan / Build** para trocar modo. Menu **… → Nome, modo e
modelo** permite renomear conversa, selecionar agente, modelo/provedor e variante.
Escolher modelo pode gerar custos na conta configurada no notebook.

Botão **+** permite escolher **Fotos** ou **Arquivos**. Suporta imagens, PDFs e
texto/código UTF-8; até 5 anexos, 4 MB por arquivo e 8 MB no total. Fotos são
convertidas para JPEG de até 2048 px. Arquivos só saem do iPhone ao tocar Enviar;
seguem pelo notebook para provedor do modelo. ZIP e outros binários não estão
incluídos. Se modelo não aceitar anexo, selecione outro compatível.

Instale atualização por cima do app, usando mesma conta Apple, sem apagar versão
anterior. Mesmo identificador do app e Chaves preservam pareamento; se iOS ou
assinatura invalidarem acesso salvo, gere novo código no notebook.

Workspace nesta versão continua sendo **No notebook**. Execução local OpenCode
no iPhone, notificações push, formulários interativos e detalhes completos da
saída de ferramentas ainda não estão incluídos.

Compilação, assinatura, instalação e teste no aparelho são etapas diferentes.
Um teste no simulador não comprova funcionamento no seu iPhone.

## Atualização 0.3.3

- **Tela inicial:** bateria do notebook e bolinha de resposta não lida.
- **Codex semanal:** percentual disponível/usado e próxima renovação, quando
  informados pela conta conectada ao Codex CLI no notebook. Não é saldo de API
  nem comprovação de que modelo do chat usa mesma conta.
- **Fotos:** seletor do sistema abre fora do menu de anexos.
- **Controlar meu iPhone:** painel com conexão, autorização de 15 minutos e
  conversa dedicada. Cada ação mutável pede revisão e confirmação individual.
- **Parar:** permanece visível no painel e na conversa de controle. Bloqueia
  novas chamadas normais do MCP e solicita interrupção, sem desfazer ações.
- **Envios:** falha não confirmada mantém texto/anexos, com aviso persistente.
- **Perguntas da IA:** toque no cartão “A IA fez uma pergunta” para selecionar
  opções ou digitar resposta no formulário nativo. Campos externos especiais
  continuam exigindo interface do notebook.

Bolinha atualiza com app ativo ou ao reabrir. Não há push; leitura é armazenada
só neste iPhone e não altera indicadores do notebook. Histórico antigo não vira
todo não lido no primeiro uso após atualização.

Controle foi testado por USB, desbloqueado. Após reinício ou expiração da
assinatura, suporte de desenvolvimento/agente pode precisar de preparação no
notebook. Se perder VPN ou rede, não presuma que botão Parar chegou ao notebook:
bloqueie iPhone ou desconecte cabo. Outras conversas mantêm permissões próprias.

## Atualização 0.3.4

Para favoritar/fixar: segure conversa e escolha **Fixar conversa**, ou deslize
linha para a direita e toque **Fixar**. Ela vai para seção **Fixadas** antes das
demais conversas. Faça o inverso para desafixar. Preferência fica salva neste
iPhone, separada por servidor; não renomeia nem arquiva chat no notebook.

Painel de controle usa agora a proteção de consentimento no MCP do notebook.
Começa pausado. Conecte iPhone por USB, desbloqueie e toque **Liberar por 15
minutos** no painel. **Parar** fecha acesso normal do MCP e pede interrupção;
não promete desfazer ações já executadas nem controlar outros programas do host.

## Atualização 0.4.0

- Botões rápidos **Plan/Build** confirmam modo no servidor; comparação de sessão
  foi corrigida para não ignorar metadados alterados com mesmo ID. Troca não
  promete transformar retroativamente uma resposta que já está em execução.
- **Pasta** na tela inicial abre arquivos do notebook; no chat, **… → Arquivos
  do projeto** tenta abrir a pasta daquele projeto, quando permitida.
- Navegue e toque em arquivo para baixar/visualizar. Use **Salvar/Compartilhar**
  para guardar no Arquivos do iPhone. Upload vai para pasta atualmente aberta.
- Até 64 MB por transferência; substituição exige confirmação e versão não pode
  ter mudado. Não há apagar/executar/descompactar. Ocultos, chaves comuns e links
  permanecem bloqueados; outras raízes precisam ser liberadas no notebook.
- Rascunhos locais guardam texto e anexos existentes; nada é reenviado sozinho.
  Aviso de envio não confirmado exige conferir conversa antes de tentar de novo.
- Toque no anexo para prévia. Respostas atualizam por eventos enquanto app está
  ativo; consulta periódica continua se conexão ao vivo cair. Ao ler histórico,
  use **Últimas mensagens** para voltar ao fim sem ser puxado automaticamente.

Mantenha app aberto em transferências. Cancelar não desfaz arquivo que já chegou
ao notebook. Se resposta do upload se perder, confira recibo/pasta antes de novo
envio. Isso continua sendo workspace remoto, não OpenCode executado no iPhone.
