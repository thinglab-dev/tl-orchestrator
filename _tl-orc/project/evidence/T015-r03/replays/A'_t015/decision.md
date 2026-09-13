## Avaliação formal — T009 r07 (checkpoint congelado, somente leitura)

### 1. Integridade do checkpoint
Reconferi via `read_section.py` os quatro digests do `resume.json` — todos batem byte-a-byte:

| Seletor | Digest esperado | Digest obtido |
|---|---|---|
| `task-T009-spec.md#Spec` | `4197dea48f75cd14...` | ✅ igual |
| `T009-r07.md#Review record` | `5834d19c77565cea...` | ✅ igual |
| `T009-r07.md#Verdict (JSON)` | `306dd8bf5acaf850...` | ✅ igual |
| `PROJECT.md#frontmatter` | `a9a09ac034db46e2...` | ✅ igual |

Além disso: o `content_id` citado pelo Checker (SHA-256 `938ddfb3...`, "85 arquivos") confere com a contagem real de `content_paths/` (85 arquivos); o HEAD citado (`0de10d60149cf7c038a0954c6aec302c9fcd111e`) existe no histórico e corresponde exatamente à mensagem de commit "diagnóstico ajustado (effort medium é condição observada)..." — texto que casa quase literalmente com o Review record do r07. O nome de branch citado ("analysis/t009-semantic-validation") não é o branch real desse commit (era `chore/t009-refine`, PR #25) — é uma imprecisão de rótulo na citação do Checker, mas não afeta o `content_id`/hash, que é a âncora de procedência real. Achado cosmético, não bloqueante.

### 2. Independência do Checker vs. autoria efetiva
Ponto central pedido na tarefa. `resume.json.effective_authors = [anthropic, google, openai]`, e o Checker usado é `codex/gpt-6-astra` (família OpenAI) sob restrição `required` (não `preferred` — sem fallback same-family permitido, conforme `PROJECT.md#Cadeias`).

À primeira vista isso pareceria um conflito (Checker da mesma família de um dos "effective_authors"). Mas a definição operativa de "autoria efetiva" em `PROJECT.md#Cadeias` é escopada: *"identifique todas as famílias que produziram o conteúdo revisado, incluindo reworks... e correções próprias do Orquestrador"* — ou seja, quem **escreveu** o artefato revisado, não quem meramente classificou/revisou-o.

Reconstruí a trilha de `Agent runs` de r01 a r07:
- **Maker real** de `T009-analysis.md`: `agy/gemini-3.8-flash-high` → família **Google**.
- **Correções próprias do Orquestrador** em r06 e r07 (rework nas linhas de limitação): `claude/claude-fable-5-1` → família **Anthropic**.
- `codex/gpt-5.6-luna` (Classificador) e `codex/gpt-6-astra` (Checker) são papéis **report-only/roteamento** — nunca escreveram no artefato revisado (todas as rodadas registram "nenhum arquivo escrito" pelo Checker).

Logo, a "autoria efetiva" no sentido que governa a independência do Checker é **Google + Anthropic**, exatamente como o próprio r07 declara (`independence: distinta de toda autoria efetiva (Google, Anthropic)`), e isso é consistente com r01–r06 (r01 já registrava "Maker Google; protótipo de referência Anthropic"). O Checker OpenAI é genuinamente distinto dessas duas famílias — **não há incompatibilidade de independência**.

O campo `effective_authors` do `resume.json` é mais amplo (inclui OpenAI por conta dos papéis de Classificador/Checker terem participado do fluxo), mas esse não é o escopo que `PROJECT.md` usa para o gate `required`. **Risco não bloqueante a registrar**: a nomenclatura `effective_authors` no manifesto de retomada pode induzir a erro um leitor/automação futuro que confunda "todas as famílias envolvidas" com "famílias que produziram o conteúdo" — vale nota para T010/consolidação de contrato, não impedimento desta rodada.

### 3. Limitação residual vs. defeito bloqueante
O verdict é explícito: a classe "procedência por conteúdo" (valores de pins/autoria citados vs. efetivamente comparados ao conteúdo da fonte) permanece como limitação **conhecida e delimitada**, não como AC não atendido. Os 7 itens `rejected` cobrem AC01–AC06 individualmente com evidência por arquivo:linha, sem hipótese aceita e sem regressão frente a r01–r06.

Verifiquei que o destino declarado (T010) é real e não é um encaminhamento de fachada: `T010-regras-de-conducao-*.md#Spec/AC02` normatiza exatamente "origem por tipo e conteúdo" com a cláusula *"fonte existente mas incompatível com o tipo ou com o valor é rejeitada"* — isto é a mesma classe de gap. T010 foi marcado `done` em `20260907T235648Z`, **44 minutos depois** do Checker do T009-r07 (`230749Z–231240Z`), portanto o encaminhamento era prospectivo e coerente no momento do veredito, e já foi honrado. Isso não é "approved" como passe livre: é uma limitação explicitamente aceita na spec (`Verification profile`), com destino existente e hoje cumprido.

### 4. Encaminhamento proposto
**Fechamento com registro da limitação**, dentro da autorização vigente (spec `4197dea48f75cd14`, verdict `approved` do Checker independente e íntegro). Não há impedimento fundamentado a levantar: alvo, spec_revision, content_id, independência e provas conferem.

**Minuta de fechamento (T009):**

> T009 fechada nesta rodada (r07) com base no veredito `approved` do Checker report-only (`codex/gpt-6-astra/high`, independência `required` verificada contra a autoria efetiva real — Maker Google + correções Anthropic do Orquestrador —, sem regressão nas contraprovas de r01–r06). AC01–AC06 satisfeitos no nível fixado pela spec (`4197dea48f75cd14`), piloto reproduzível (`--self-test`, 38 casos, 33 sem despacho). Limitação residual registrada: verificação mecânica confere localização e existência de citações de procedência, mas não compara valores de pins/autoria contra o conteúdo da fonte citada ("procedência por conteúdo") — classe consolidada normativamente em T010 (AC02, spec s3–s5, `done` em 20260907T235648Z). Nenhum rework adicional exigido nesta rodada.

Nenhum arquivo foi alterado nem agente foi despachado — análise limitada à leitura e verificação de digests conforme o aviso restritivo.