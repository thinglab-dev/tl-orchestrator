## 1. Achado prévio de integridade (bloqueante para o *chain of custody*, não para a decisão de conteúdo)

Antes de avaliar o mérito, registro uma inconsistência formal: os digests SHA-256 computados agora pela leitura seletiva (`scripts/read_section.py`) **não batem** com os digests declarados no `resume.json` para nenhuma das quatro fontes resolvidas:

| Artefato | Digest no manifesto | Digest computado agora |
|---|---|---|
| PROJECT.md#frontmatter | `adcd36f9...4bd73` | `983eafd3...50dc162` |
| checker-6-0a-r1.md#Parecer | `670eebe5...5676402de` | `7020957d...36f8172b8` |
| dev-report-6-0a.md#Escopo entregue | `80af0230...913a55dc8c2cd5` | `272287fb...c9af93f48373` |
| spec-6-0a.md#§3 | `da77d7eb...446f1aee8c7a9db` | `549a4179...557ffe27bb3` |

Isso caracteriza `digest_changed` conforme `prompts/orchestrator-playbook.md`: o conteúdo lido no checkpoint-B não corresponde ao que o manifesto de retomada declara ter resolvido. Como o exercício é explicitamente sobre um recorte documental "não observável" na árvore histórica, presumo que seja artefato deliberado do fixture (T015-r01) e não sigilo real — mas formalmente isso significa que o `resume.json` fornecido **não pode ser tomado como prova de que o conteúdo abaixo é o mesmo que foi congelado**. Meu parecer abaixo usa o conteúdo lido *agora*, com digest próprio registrado nesta resposta, e não herda a cadeia de custódia do manifesto. Recomendo que o T015 regenere/revalide o `resume.json` contra o checkpoint-B antes de qualquer uso não-experimental.

Isso não bloqueia a decisão de condução (o conteúdo é internamente consistente e coerente entre spec/dev-report/checker), mas é um achado de governança a registrar.

## 2. Avaliação formal da Story 6.0a — Parecer r1 (`changes_requested`)

**R1 (medium, category=patch, target=maker)** — único `action_item` aberto.

- **Localização:** `cmd/lynvia/internal/process/config.go: validateListenAddr`.
- **Alegação do Checker:** a heurística `host == "" && port == "8080"` inventa semântica não pedida, recusando `:8080` explícito e quebrando o comportamento do perfil legado Bling.
- **Confronto com a spec (AC01, AC04):**
  - AC01 exige que "configuração atual Bling mantém comportamento" — comportamento retroativo é obrigação, não opção.
  - AC04 proíbe apenas inicialização **implícita** em endereço default; não proíbe uso **explícito** de `:8080` por quem já o configurava assim.
- **Confronto com o dev-report:** a própria seção "Escopo entregue" confirma o comportamento questionado — *"endereço ausente, malformado ou `:8080` é recusado"* — corroborando literalmente a evidência do Checker. Não há divergência de fato entre parecer e report; o Maker documentou a própria regra que o Checker aponta como defeito.
- **Conclusão:** R1 é um achado bem fundado, delimitado e não especulativo. Ele aponta um defeito real que impede o critério de aceite obrigatório AC01 (quebra de compatibilidade retroativa para instalações que já usam `:8080` explícito), não uma preferência estilística. Classifico como **bloqueante para aprovação**, corretamente marcado como `changes_requested`.

**Itens `deferred` (não bloqueantes, concordo com a triagem do Checker):**
1. Validação de material público/privado ausente no perfil `mkauth-control-plane` — adiamento correto, pois os handlers só serão ligados em 6.0b–d (AC02 explícito na spec).
2. Falha isolada em `internal/connectorgate` — externa ao escopo modificado por esta story; não há base na spec (§6, "uma story implementa somente seu módulo") para tratá-la aqui.

Nenhum item em `rejected`.

## 3. Encaminhamento proposto

**Rework delimitado ao achado R1.** Não há base para contestação (a evidência do próprio dev-report confirma o comportamento apontado) nem para impedimento (a correção é um patch cirúrgico, sem dependência externa nem necessidade de nova autorização/gate). O `required_action` do próprio Checker já delimita a ação: remover a regra arbitrária `host=="" && port=="8080"`, preservando a validação sintática (`net.SplitHostPort`) e a exigência de configuração preexistente. Os itens `deferred` não entram no escopo desta rodada de rework.

## 4. Briefing estruturado — Maker, Rework R1

```yaml
work_ref: bmad/story/6.0a
round: R1 (rework)
verdict_origin: changes_requested (checker-6-0a-r1.md)
scope: estritamente delimitado ao achado R1; nenhum outro item do parecer (deferred: mkauth
  material validation, connectorgate) entra nesta rodada.

target_file: cmd/lynvia/internal/process/config.go
target_function: validateListenAddr (chamada a partir de normalizeConfig)

problema:
  A validação atual recusa explicitamente host=="" && port=="8080" com a mensagem
  "endereço webhookd usa default de produção". Essa regra:
  - inventa semântica não presente em AC01/AC04;
  - quebra retroativamente instalações do perfil Bling que já configuravam ":8080" de
    forma explícita, violando AC01 ("Configuração atual Bling mantém comportamento").

correção requerida:
  - Remover a regra heurística host=="" && port=="8080" -> reject.
  - Preservar a proteção real contra endereço implícito através de:
      a) validação sintática do endereço via net.SplitHostPort (endereço ausente ou
         malformado continua recusado);
      b) exigência de que o endereço tenha sido explicitamente configurado (não há
         fallback silencioso para um default de produção quando o campo está vazio).
  - Não introduzir nenhuma outra heurística de valor "mágico" (porta específica,
    string default) como proxy de "endereço implícito".

fora de escopo nesta rodada (não tocar):
  - Validação de material público/privado do perfil mkauth-control-plane
    (normalizeConfig) — adiada para 6.0b–d por decisão do Checker, alinhada ao AC02.
  - internal/connectorgate — falha preexistente e externa ao escopo desta story.
  - Qualquer alteração de Compose/Set/validateSufficient além do necessário para
    corrigir validateListenAddr.

content_paths preservados (não expandir escopo de arquivos tocados pela story):
  - cmd/lynvia/internal/process/config.go
  (mesmo arquivo já modificado na rodada 1, conforme dev-report-6-0a.md §Escopo entregue;
   nenhum novo arquivo deve ser introduzido para resolver R1)

critérios de aceite reafetados por este rework:
  - AC01: configuração Bling explícita com ":8080" deve voltar a ser aceita sem
    alteração de comportamento retroativo.
  - AC04: endereço ausente/malformado/implícito continua bloqueado; não há regressão
    de proteção, apenas remoção da heurística indevida.

verificação esperada (S18/S19, conforme §5 da spec):
  - Cenário positivo: config Bling legado com listener em ":8080" explícito -> aceito,
    comportamento idêntico ao pré-existente.
  - Cenário negativo mantido: endereço ausente ou malformado -> continua recusado.
  - Sonda contrafactual: remover a validação sintática (net.SplitHostPort) deve tornar
    vermelho o teste; restaurar deve tornar verde novamente.
  - Não usar mock para comprovar o comportamento; fixtures sintéticas apenas.

autorização vigente: rework delimitado, dentro do escopo já autorizado para 6.0a;
  não requer novo gate G1–G6 (nenhuma DDL, nenhum efeito de laboratório ou PII envolvido).

nota de proveniência (ver seção 1 desta resposta): os digests deste checkpoint-B não
  batem com os declarados no resume.json; o Maker deve tratar o conteúdo aqui citado
  como lido diretamente do checkpoint-B nesta sessão, não como herdado do manifesto.
```

**Resumo:** parecer r1 é procedente; R1 é bloqueante e corretamente delimitado; encaminhamento é rework cirúrgico em `validateListenAddr`, sem expandir escopo de arquivos ou reabrir itens deferred. Achado paralelo de integridade (digests do `resume.json` divergentes do conteúdo real) foi registrado e não deve ser silenciado em usos não-experimentais do T015.
