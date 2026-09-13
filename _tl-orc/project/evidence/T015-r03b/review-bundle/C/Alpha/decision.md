## Avaliação formal — DW-6.0A-01 (r1)

### 1. O que o parecer r1 registra
`checker-dw-6-0a-01-r1.md` traz veredito `approved` (zero achados aceitos, três hipóteses de fragilidade rejeitadas com evidência) para a troca de um único literal em `release_test.go:242`. O "Envelope original" e a "Classificação (resultado bruto)" mostram que o candidato efetivamente despachado como Checker foi **Agy `gemini-3.8-flash-medium` / effort medium**.

### 2. Confronto com a governança em `PROJECT.md`

Dois controles independentes são violados pelo mesmo despacho:

- **Catálogo permitido** (`## Catálogo permitido`): a família Gemini está autorizada para Checker apenas como `gemini-3.1-pro-high`; `gemini-3.8-flash-medium` é reservado a **Classificador/Searcher**, não a Checker. O modelo usado no r1 não consta do catálogo para esse papel.
- **Pin fixado pelo usuário em 2026-09-07** (`### Escolhas fixadas pelo usuário...`), que **"prevalece sobre o perfil"**: para Checker report-only o modelo deve vir da família **Claude**, escolhido pelo Classificador dentro de `sonnet`/`claude-opus-5`, com a única restrição de família distinta dos Makers efetivos (Agy Gemini e Codex GPT). Esse pin não foi honrado — a própria classificação bruta relegou Claude/`sonnet` a "último recurso" e promoveu Gemini ao topo, invertendo a ordem imposta pelo pin.

Agravante: a justificativa de independência usada na classificação ("família distinta da autoria Claude/Anthropic") parte de premissa factualmente incorreta — a correção de 2026-09-08 foi feita pelo próprio Orquestrador, família OpenAI GPT (conforme a nota de resolução em `deferred-work.md` e a tabela de Preferências operacionais), não por Claude/Anthropic. Isso não inverte a conclusão (Gemini seguiria "família distinta" de OpenAI também), mas evidencia que o racional de despacho estava desalinhado dos fatos do caso, reduzindo a confiabilidade do processo de seleção que produziu esse candidato.

### 3. Determinação
O veredito `approved` do r1 **não constitui aprovação regular**: foi emitido por um candidato não autorizado para o papel de Checker, tanto pelo catálogo permitido quanto pelo pin de usuário que prevalece sobre o perfil. Trata-se de **aprovação por candidato não autorizado**, não de um parecer de mérito questionável — a análise técnica em si (rejeição das três hipóteses de fragilidade) pode ser tecnicamente razoável, mas não tem valor de quitação de governança porque a fonte da aprovação é inelegível para o papel.

Nota lateral (fora do escopo de correção agora, mas relevante para reconciliação): `deferred-work.md` contém **dois registros conflitantes** para DW-6.0A-01 — um marcado como "RESOLVIDO" citando este mesmo parecer r1 inválido, e outro, logo abaixo, ainda descrevendo o item como pendência ativa bloqueando `make check`. Essa duplicidade deveria ser sanada na mesma regularização.

### 4. Proposta de regularização (não executada — somente leitura)

1. **Reclassificar** DW-6.0A-01 do estado "resolvido" para "pendente de revisão válida", preservando o parecer r1 integralmente como registro do desvio (não apagar; anotar como `invalid_dispatch` / candidato fora do catálogo e do pin).
2. **Nova classificação** (papel `checker`, fase `review`) em sessão limpa, obrigando o Classificador a respeitar o pin de 2026-09-07: candidato primário Claude (`sonnet` ou `claude-opus-5`, effort médio/alto), independente dos Makers efetivos (Agy Gemini e Codex GPT).
3. **Nova revisão** do mesmo diff de uma linha (`release_test.go:242`) por esse candidato registrado, em sessão nova, sem reaproveitar o r1 como base de decisão — apenas como contexto histórico do desvio.
4. **Reconciliar** as duas entradas conflitantes de DW-6.0A-01 em `deferred-work.md` em uma única entrada com status coerente, uma vez obtida a revisão válida.
5. Registrar o episódio (candidato inelegível aprovando revisão de Checker) como pendência de auditoria do processo de despacho, já que o mesmo padrão de erro no Classificador pode se repetir em outras unidades.

### Briefing para a próxima sessão (Checker, papel `checker`, fase `review`)
- **Contexto:** diff de 1 linha em `modules/lynvia/internal/connectorgate/release_test.go:242`, trocando o literal exato de usage por um prefixo estável (`"uso: lynvia-mkauth-connector [--version"`, sem o `]`), corrigindo desalinhamento do oráculo de teste após o CLI do módulo `lynvia-mkauth-connector` ganhar subcomandos novos.
- **Evidências disponíveis:** teste isolado vermelho→verde, sonda contrafactual restaurando regressão, `make check` completo do módulo `lynvia` verde (0 SKIP).
- **Candidato obrigatório:** família Claude (`sonnet` ou `claude-opus-5`), effort medium/high, sessão nova, independente dos Makers efetivos (Agy Gemini, Codex GPT), conforme pin de 2026-09-07 em `PROJECT.md`.
- **O que revisar:** confirmar que o novo prefixo ainda discrimina regressões reais de usage sem se acoplar à lista completa de subcomandos; verificar ausência de outros oráculos frágeis não cobertos pela mudança pontual.
- **Registro do desvio:** anexar o parecer r1 (`checker-dw-6-0a-01-r1.md`) como anexo histórico, explicitamente marcado como despacho inválido (modelo fora do catálogo/pin para o papel Checker), não como insumo de mérito para a nova decisão.

Nenhum arquivo foi alterado e nenhum agente foi despachado — esta resposta é apenas a proposta de condução e o briefing solicitados, em modo somente leitura.
