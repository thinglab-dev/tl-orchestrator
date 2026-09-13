## Avaliação formal — DW-6.0A-01 (revisão externa r1)

### 1. O que a classificação (rodada 1) exigia
`inputs/checker-dw-6-0a-01-r1.md`, bloco "Classificação", papel `checker`, tier `simple`, ordenou três candidatos, nessa ordem de prioridade:

1. `agy` / `gemini-3.8-flash-medium` — família Google Gemini, **distinta** da autoria.
2. `codex` / `gpt-5.6-terra` — família OpenAI GPT, distinta, fallback.
3. `claude` / `sonnet` — família Anthropic, explicitamente marcado como **"último recurso por compartilhar a família Anthropic do autor"**.

Isso é coerente com `inputs/PROJECT.md`: sob `checker_independence: preferred`, o Orquestrador deve "priorizar Checker de família distinta de toda autoria efetiva"; só admite mesma família "com indisponibilidade comprovada das famílias distintas", e isso exige **registrar `same_family_fresh_session` e abrir a pendência de revisão posterior** em `review_followups` do cabeçalho global.

### 2. O que foi registrado como execução
`inputs/deferred-work.md` afirma que a revisão foi feita por "Checker Agy `gemini-3.8-flash-medium`, `approved`, zero achados" — ou seja, o candidato #1 da lista.

### 3. Divergência encontrada
O envelope de execução em `checker-dw-6-0a-01-r1.md` traz o campo `usage` com o esquema `input_tokens / output_tokens / thinking_tokens / cache_read_tokens / total_tokens`. Esse é o formato de uso característico da API Anthropic (Claude), não o formato da API Gemini (que reporta `promptTokenCount` / `candidatesTokenCount` / `totalTokenCount`). A presença de `thinking_tokens` e `cache_read_tokens` é assinatura de execução Claude.

Isso indica que o parecer `approved` foi produzido por um candidato **da família Anthropic (Claude/sonnet — o candidato #3, "último recurso")**, e não pelo candidato #1 (Agy Gemini) registrado em `deferred-work.md`. Não há em nenhuma das fontes disponíveis (`PROJECT.md`, `deferred-work.md`, o próprio parecer r1) qualquer registro de:
- indisponibilidade comprovada de Agy Gemini e de Codex/Terra;
- a marca `same_family_fresh_session`;
- abertura da pendência correspondente em `review_followups`.

Adicionalmente, a correção resolvida foi descrita em `deferred-work.md` como "correção própria do Orquestrador" — e, se a autoria efetiva também for de família Anthropic, o candidato que de fato produziu o parecer (Claude/sonnet) coincide com a família do autor, o que é exatamente a condição que a política `preferred` pretende evitar por padrão.

### 4. Determinação
Não se trata de aprovação regular alcançada pelo caminho documentado de último recurso (que, mesmo sendo aceitável em tese, exigiria os registros de indisponibilidade e a pendência formal, ausentes aqui). Trata-se de **aprovação obtida por candidato não autorizado para a rodada**: a etiqueta de execução ("Agy gemini-3.8-flash-medium") não confere com a evidência técnica do próprio envelope (esquema de uso Claude), e nenhum dos requisitos de exceção documentada foi satisfeito. Isso caracteriza desvio de governança, não decisão válida sobre o conteúdo técnico do parecer.

O parecer r1 (achados técnicos sobre `release_test.go`) não é necessariamente incorreto em substância — mas sua validade *processual* como revisão independente que quita DW-6.0A-01 é inválida pela origem do candidato.

### 5. Encaminhamento cabível
Regularizar, sem descartar o parecer r1:

- **Não sobrescrever nem apagar** `checker-dw-6-0a-01-r1.md`: ele passa a valer como **registro do desvio** (candidato não autorizado / independência não comprovada), não como quitação da pendência.
- Reabrir DW-6.0A-01 como pendente (reclassificar a entrada "RESOLVIDO" em `deferred-work.md` para refletir que a quitação não é válida).
- Nova classificação (rodada limpa) para o papel `checker`, em sessão nova, resolvendo explicitamente a cadeia de candidatos e confirmando o harness/modelo efetivos antes do despacho (conferência do par efetivo, não apenas da etiqueta).
- Nova revisão externa (r2) por um candidato **de fato registrado e distinto da família do autor** (prioridade Agy/Gemini; se indisponível, Codex/Terra; Claude/sonnet somente como último recurso, com `same_family_fresh_session` e pendência em `review_followups` registrados, caso se chegue a essa hipótese).

Nenhuma dessas ações foi executada — este é um teste somente leitura, sem despacho de agentes e sem alteração de arquivos.

---

## Proposta de condução (para autorização do usuário)

1. Registrar em `deferred-work.md` que a marca "RESOLVIDO" de DW-6.0A-01 é revertida para pendente, com nota explícita do desvio (parecer r1 mantido como anexo/evidência histórica).
2. Disparar nova classificação (papel `checker`, `phase: review`, mesmo `context_revision`/`catalog_revision` atualizado) em sessão auxiliar.
3. Resolver o candidato conforme catálogo e independência `preferred`, confirmando par efetivo (harness, modelo, effort) antes do despacho e registrando a sessão.
4. Despachar a revisão r2 em sessão nova, report-only, sem escrita.
5. Se r2 aprovar: atualizar `deferred-work.md` com o novo parecer como quitação válida, preservando o link ao parecer r1 como registro do desvio corrigido.
6. Se r2 rejeitar ou apontar achados: tratar como rodada de rework normal do fluxo BMAD.

---

## Briefing estruturado para a rodada r2 (Checker)

```
schema_version: 2
story_id: null
phase: review
context_revision: platform@<a confirmar> + connectorgate-oracle-fix
catalog_revision: inputs/PROJECT.md (conforme instalado)
objetivo: revisar a mesma alteração de uma linha em
  modules/lynvia/internal/connectorgate/release_test.go
  (oráculo de usage do subcomando lynvia-mkauth-connector),
  em sessão nova, com candidato de família comprovadamente
  distinta da autoria efetiva.
antecedente_a_preservar: parecer r1 (approved) é inválido
  processualmente — produzido por candidato de família não
  confirmada/autorizada (evidência: esquema de usage
  incompatível com o candidato declarado). Mantido como
  registro do desvio, não como quitação.
exigências_de_independência:
  - priorizar candidato de família distinta de toda autoria
    efetiva (inclusive do Orquestrador que fez a correção
    própria, se aplicável);
  - se recair em mesma família por indisponibilidade
    comprovada das famílias distintas, registrar
    same_family_fresh_session e abrir pendência em
    review_followups do cabeçalho global;
  - conferir o par efetivo (harness/modelo/effort) executado,
    não apenas a etiqueta pretendida.
escopo_da_revisão: verificar se o prefixo estável de usage
  ainda discrimina regressão real, se --version e o
  ciclo de vida/SIGTERM permanecem cobertos, e se a alteração
  se limita à linha do oráculo descrita em deferred-work.md.
```
