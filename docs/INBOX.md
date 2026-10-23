# Pasta automática — 0.5.0

Na tela de conversas, abra **Pasta automática do iPhone**. A primeira abertura
cria **Iphone 11 Omoki** em Documentos do Pocket, visível em **Arquivos → No Meu
iPhone → OpenCode Pocket**. Use Salvar em Arquivos de outros apps para colocar
imagens, PDFs e arquivos nessa pasta. Não é pasta da biblioteca Fotos: não apaga
imagens da galeria. Criar pasta não ativa transferência; ligue opção no painel.

Com opção ativa, Pocket verifica aproximadamente a cada oito segundos enquanto
está aberto. Computador precisa estar conectado. Destino fixo:
`~/Downloads/Iphone 11 Omoki`. Gateway cria apenas essa pasta e seu diretório
Downloads, quando necessário, sem seguir links simbólicos. Permissão fica
vinculada ao endereço do servidor escolhido; trocar servidor não autoriza envio
automático ao novo destino.

## Movimentação, não backup

**Ativar significa autorizar remoção dos arquivos dessa pasta do iPhone depois
da transferência verificada.** Não há desfazer no app. Não apague app enquanto
houver arquivos pendentes: desinstalar pode apagar Documentos locais.

1. Lê checksum em blocos e transmite arquivo sem criar cópia integral extra no
   iPhone. Não há limite fixo de tamanho nessa pasta; limites do explorador manual
   não se aplicam. Computador precisa ter espaço para arquivo temporário e destino.
2. Persiste identificador do envio por servidor/nome/checksum.
3. Destino recebe prefixo UUID: nomes iguais não sobrescrevem arquivos existentes.
4. Antes de retomar, consulta conteúdo real do destino por identificador/caminho.
5. Envia com checksum e criação sem sobrescrita quando destino ainda não existe.
6. Faz **nova leitura dos bytes efetivamente gravados no computador** e compara
   SHA-256, tamanho, identificador e caminho, não apenas recibo antigo.
7. Coordena acesso ao arquivo local e recalcula checksum antes de remover.
   Se conteúdo mudou, preserva versão local. Falhas deixam original pendente.

Recibo não garante que arquivo continuará no computador para sempre: alterações
posteriores por outros programas continuam possíveis. Não há transação atômica
distribuída entre iOS e computador. Coordenação protege contra acessos cooperativos
de apps Arquivos; não é isolamento contra programas maliciosos. Crash pode deixar
cópias duplicadas, preferidas à perda de dados. Não há descarte automático por idade.

Somente arquivos regulares diretamente nessa pasta, sem links/subpastas/ocultos.
Proteções de credenciais do explorador continuam valendo. Arquivo grande, protegido
ou alterado pode pausar fila com erro visível; retire-o da pasta ou resolva problema.
Desativar pausa próximos passos; operação de remoção já iniciada pode terminar.
Em segundo plano ou aparelho bloqueado, iOS pode suspender acesso/transferência;
reabra Pocket para retomar. Não há observador contínuo em segundo plano.

Dashboard também mostra armazenamento do iPhone e do volume de destino no
computador: percentual ocupado, GB livres e capacidade. GB são decimais. iPhone
consulta somente volume local e não envia essa informação ao computador. Capacidade
do computador usa volume da pasta de destino ou ancestral existente antes da criação.

Token do Pocket pode enviar para essa pasta e verificar seu conteúdo; nenhuma rota
de exclusão no computador foi adicionada. Credenciais, recibos e conteúdo real não
fazem parte do repositório ou dos testes CI, que usam somente fixtures temporárias.
