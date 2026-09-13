## Avaliação formal — T009, parecer do Checker r07

### 1. Vínculo formal (alvo, spec, autorização)

Conferi diretamente as fontes, não apenas o `resume.json`:

- `task-T009-spec.md` → `spec_revision: 4197dea48f75cd14` (linha 3), igual ao valor em `resume.json.spec_revision` e ao prefixo do digest de `## Spec` (`4197dea48f75cd14e7a3…`).
- `T009-r07.md`, rejeitado #1: HEAD `0de10d60149cf7c038a0954c6aec302c9fcd111e`, SHA-256 dos 85 arquivos de `content_paths` = `938ddfb319408b79…`. Isso bate exatamente com `content_id: 0de10d60149cf7c038a0954c6aec302c9fcd111e:938ddfb319408b79` do `adapted_fixture`.

Alvo, spec e content_id estão coerentes entre si — não há desvio de escopo nem substituição de fixture.

### 2. Independência do Checker vs. autoria efetiva — ponto crítico verificado

Este é o item que exige conferência direta, não confiança cega no `resume.json`.

- `resume.json.effective_authors` declara `["anthropic", "google", "openai"]` — **três** famílias.
- O próprio parecer do Checker (`T009-r07.md`, "Resultado da revisão") declara independência apenas frente a **duas**: `independence: distinta de toda autoria efetiva (Google, Anthropic)`.
- Fui à fonte primária do conteúdo revisado, `T009-analysis.md`:
  - Cabeçalho, linha 5: `maker: agy gemini-3.8-flash-high` → família **Google**.
  - `rework_round: 5 (+ correção própria do Orquestrador após c01)`; a linha correspondente em `T009-r07.md` (`Agent runs`) identifica essa correção própria como `claude / claude-fable-5-1 / Anthropic`.
  - Não encontrei, em `T009-analysis.md` nem em `T009-mechanical-check.py`, qualquer rodada de rework/correção autorada por família OpenAI. As únicas ocorrências de `codex`/OpenAI no `Agent runs` de r07 são os papéis de **processo** desta rodada de revisão — classifier (`codex/gpt-5.6-luna`) e checker (`codex/gpt-6-astra`) —, não autoria do conteúdo entregue.

**Conclusão:** a autoria efetiva real do conteúdo sob revisão é Google + Anthropic, exatamente como o próprio Checker declarou e verificou. O Checker usado é `codex/gpt-6-astra` (OpenAI) — família distinta de ambas, satisfazendo a restrição `required` fixada para este piloto (`PROJECT.md`, seção "Piloto de avaliação do Astra como Checker").

O campo `effective_authors` do `resume.json` está **superestimado** (inclui "openai" sem lastro documental) — é uma inconsistência de dado de contexto, não um defeito de governança factual. **Não bloqueia o fechamento**, mas deve ser corrigido na ferramenta que gera esse resumo, para não induzir um Orquestrador futuro a um bloqueio ou a uma aprovação por engano nesse campo. Registro isso como achado a corrigir, não como impedimento.

### 3. Limitação residual vs. defeito bloqueante

A classe "procedência por conteúdo" (pins/autoria aceitos sem comparar valor declarado com a fonte; `story_id`/fase/revisões/política/famílias aceitos em qualquer localização existente; papéis exigidos da política em vez da solicitação) está:

- Documentada explicitamente em `T009-analysis.md:276`, com histórico de 4 rodadas e conclusão formal da fase consultiva `T009-c01`.
- Elevada a requisito normativo em T010 (tabela tipo-de-informação → fonte autorizada → conteúdo que sustenta valor → como conferir) — fora do escopo desta Task por decisão explícita da spec.
- Prevista e aceita nos próprios AC02/AC05 da spec congelada (`task-T009-spec.md`), que exigem apenas a **declaração** da limitação, não sua eliminação nesta Task.

Isso é exatamente o caso de "limitação residual explicitamente aceita na spec", não um defeito bloqueante de AC02/AC05. O Checker tratou-a corretamente como tal (rejeitou a hipótese de regressão/persistência indevida da promessa de rastreabilidade total, mantendo a limitação declarada).

### 4. Inconsistência secundária a registrar (não bloqueante)

`T009-r07.md` linha 11 ("Commands and exits") afirma "validador exit 0", mas o corpo do rejeitado AC06 relata exit 1 no `validate_repository.py` (falha de `TemporaryDirectory` no sandbox do Checker), compensado por verificação direta de cada sub-função (`load_manifest`, `validate_json`, `validate_frontmatter`, `validate_links`, `validate_readme_manifest`) e por `--self-test` com exit 0. A evidência detalhada é a que sustenta a aprovação; a linha-resumo está redigida de forma imprecisa. Recomendo correção editorial da linha-resumo, sem reabrir AC06 — a exigência de reprodutibilidade do piloto (self-test) foi cumprida.

### 5. Verificação de que "approved" não é passe livre

Confirmei que o Checker não apenas emitiu veredito, mas fundamentou cada uma das 7 rejeições com citação por critério (arquivo:linha, comandos executados, hashes conferidos, sondas próprias como remoção de envelopes e alteração de effort), incluindo reexecução do `--self-test` (38 casos, paridade com `pilot_summary.json`) e comparação byte a byte da exportação distribuída. Não há ação pendente (`action_items: []`), nem `deferred`.

---

## Minuta de fechamento proposta

**Task:** T009 — Validação Semântica da Classificação pelo Orquestrador
**Rodada:** r07 (Checker `codex/gpt-6-astra/high`, independência `required`, satisfeita frente à autoria efetiva real Google+Anthropic)
**Decisão:** **Fechar** com registro de limitação.

Registro de fechamento:
1. AC01–AC06 satisfeitos no nível fixado pela spec `4197dea48f75cd14`, sobre `content_id 0de10d60149cf7c038a0954c6aec302c9fcd111e:938ddfb319408b79`, sem regressão frente às contraprovas de r01–r06.
2. Independência do Checker conferida por fonte primária (não pelo campo agregado do `resume.json`, que superestima a autoria efetiva): efetivos = Google (maker Agy/Gemini) e Anthropic (correção própria do Orquestrador); Checker OpenAI é distinto de ambos — `required` cumprido.
3. Limitação residual "procedência por conteúdo" mantida como aceita e encaminhada normativamente a T010; não é motivo de rework nesta Task.
4. Duas correções de higiene documental a abrir como itens leves (não bloqueantes para este fechamento):
   - Corrigir `effective_authors` em ferramentas/`resume.json` para refletir apenas Google/Anthropic quando este for o caso real, evitando incluir papéis de processo (classifier/checker) como autoria.
   - Corrigir a linha-resumo "Commands and exits" de `T009-r07.md` para refletir o exit 1 real do `validate_repository.py` no sandbox do Checker e a verificação substitutiva por sub-função, hoje só explicada no corpo do rejeitado AC06.

Nenhum arquivo foi alterado nesta sessão (modo somente leitura); nenhum agente foi despachado. Esta é a proposta de condução para decisão do Orquestrador responsável pelo fechamento efetivo.
