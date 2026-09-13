Tenho evidência suficiente para o parecer. Não vou editar arquivos nem despachar agentes — isto é somente leitura, conforme instruído.

---

## Avaliação formal — DW-6.0A-01

**Achado (evidência coletada, com procedência):**

1. `deferred-work.md` (seção `## Deferred from: code review of 6-0a-configuracao-e-lifecycle-do-control-plane (2026-09-08)`) registra DW-6.0A-01 como **"RESOLVIDO em 2026-09-08"**, citando revisão externa **"Checker Agy `gemini-3.8-flash-medium`, `approved`, zero achados"**.
2. `checker-dw-6-0a-01-r1.md` (`## Parecer (objeto extraído)`) confirma `verdict: approved`, `action_items: []`, `deferred: []` — o candidato aprovou sem ressalvas, apenas registrando três hipóteses de fragilidade como `rejected`.
3. `PROJECT.md` (`## Catálogo permitido`, L96-106) vincula o papel **Checker** a `gemini-3.1-pro-high`; `gemini-3.8-flash-medium` está catalogado **apenas para Classificador/Searcher**.
4. `PROJECT.md` (`## Preferências operacionais`, L62-95) confirma o mesmo: linha "Checker report-only" → `gemini-3.1-pro-high`; linha "Searcher sob demanda" → `gemini-3.8-flash-medium` explicitamente descrita como "restrição conservadora de entrada" daquele papel, não do Checker.
5. `resume.json.effective_authors = ["openai"]` — a autoria efetiva do diff é família OpenAI/Codex (`Maker Codex gpt-5.6-terra`, consistente com o catálogo). A política `checker_independence: preferred` exige família distinta de toda autoria efetiva antes de admitir mesma família em sessão nova.

**Conferência contra a governança:**

- **Independência de família**: satisfeita no nível grosso — Gemini ≠ OpenAI (autor efetivo). Não há violação de `checker_independence` por família.
- **Catálogo do papel**: **violado**. O verdict `approved` foi emitido por um candidato (`gemini-3.8-flash-medium`) catalogado para **Searcher/Classificador**, não para **Checker** (`gemini-3.1-pro-high`). O "Catálogo permitido" (L96-106) é explícito: "Registre pares válidos [...] capacidade desconhecida bloqueia a resolução, não permite herdar defaults" e "Alternativas de trabalho além das restrições conservadoras exigem reconciliação da preferência" — nada disso foi feito antes do despacho registrado em `deferred-work.md`.
- Não encontrei, nas seções lidas, nenhuma reconciliação de preferência ou autorização explícita do usuário permitindo Flash-medium como Checker desta unidade (diferente do pin de 2026-09-07 para Maker Native em `lynvia-mkauth-connector:T004`, que é escopo distinto e não cobre este Checker).

**Determinação:** a aprovação r1 foi emitida por candidato **não autorizado para o papel Checker** — é desvio de despacho (papel/modelo trocado), não aprovação regular. Isto não implica necessariamente que o conteúdo técnico do parecer esteja errado (a mudança em si — troca do literal fechado por prefixo estável em `release_test.go:242` — é pequena e plausível), mas o **verdict não tem valor de portão** enquanto não vier de candidato cadastrado no catálogo do papel, em sessão limpa.

---

## Proposta de regularização

1. **Preservar** `checker-dw-6-0a-01-r1.md` inalterado como registro do desvio (não é substituído nem apagado — serve de evidência de trilha).
2. **Reclassificar** a pendência em `deferred-work.md`: reverter o marcador de "RESOLVIDO" para pendente de revisão válida, anotando a causa ("aprovação por candidato fora do catálogo do papel Checker — `gemini-3.8-flash-medium` é Searcher/Classificador, não Checker").
3. **Nova revisão (r2)**, em sessão nova, por candidato dentro do catálogo do papel Checker: `gemini-3.1-pro-high` (preferência de perfil) — respeitando `checker_independence: preferred` frente ao autor efetivo (`openai`).
4. Se `gemini-3.1-pro-high` for indisponível, registrar `same_family_fresh_session` e abrir pendência em `review_followups` no cabeçalho global, conforme o contrato — não substituir silenciosamente pelo par errado de novo.
5. O escopo da r2 é estritamente confirmar/reavaliar a mesma mudança de 1 linha em `release_test.go:242` (diff já congelado, vazio no checkpoint — reobter do estado real da árvore antes do despacho).

## Briefing para o Checker (r2)

- **Papel:** Checker report-only, sessão nova, sem escrita.
- **Modelo exigido:** `gemini-3.1-pro-high` (catálogo do papel; fallback conforme item 4 acima).
- **Objeto:** diff de 1 arquivo, `modules/lynvia/internal/connectorgate/release_test.go`, troca do literal de usage esperado por prefixo estável (ver `deferred-work.md`, texto integral acima).
- **Contexto obrigatório:** citar `checker-dw-6-0a-01-r1.md` como parecer anterior inválido por desvio de despacho (não por mérito técnico) — não descartar o conteúdo técnico do r1, apenas sua autoridade de portão.
- **Pergunta a responder:** o oráculo revisado ainda discrimina regressão real de usage sem fixar o conjunto de subcomandos do CLI `lynvia-mkauth-connector`? Exigir evidência de sonda contrafactual (mutação temporária + reversão por hash), como já descrito em `deferred-work.md`.
- **Saída esperada:** mesmo schema (`verdict`, `action_items`, `deferred`, `rejected`) do r1, agora com procedência de modelo/papel corretos.

Nenhum arquivo foi alterado e nenhum agente foi despachado — este é o encaminhamento proposto para autorização.
