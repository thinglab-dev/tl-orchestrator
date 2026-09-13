## Achados (leitura seletiva com verificação de digest)

**1. Falha de integridade no manifesto `resume.json`.** Recalculei os digests das seções via `read_section.py` (que recomputa SHA-256 do conteúdo real, não confia em valor declarado) e comparei com os digests que `resume.json` declara:

| Fonte | Digest declarado (resume.json) | Digest computado (real) | Status |
|---|---|---|---|
| `PROJECT.md` `frontmatter` | `adcd36f9...` | `983eafd3f9fd80922a9c925a7437b8d03c5034e392f407153e9da0e0c50dc162` | **MISMATCH** |
| `checker-dw-6-0a-01-r1.md` `## Parecer (objeto extraído)` | `01f027ee...` | `b4e84a0a857755f052acfe562a3f74e867e59302c8fb9602fa6225a79d18245d` | **MISMATCH** |
| `deferred-work.md` `## Deferred from...` | `1ed58894...` | `1ed58894593bbe3aa22b3b7c65dae45a4e6caa103d7113285e75862cc7ca189a` | match |
| `release_test.diff` `full` | `e3b0c442...` | (arquivo vazio, 0 bytes — digest de string vazia) | match |

Dois dos quatro pontos de procedência do manifesto de retomada não se sustentam contra o conteúdo atual dos arquivos. Por política de context economy (T015), isso desqualifica confiança cega no `resume.json` para essas duas fontes — o que segui fazendo (recorte por seção com verificação própria, não pelo manifesto), e reporto aqui porque é, em si, uma não-conformidade a corrigir na evidência da unidade.

**2. Divergência de identidade do Checker que produziu o parecer r1.**

- `deferred-work.md` registra a pendência como `RESOLVIDO em 2026-09-08` citando: *"Revisão externa: parecer — Checker Agy `gemini-3.8-flash-medium`, `approved`, zero achados."*
- O classificador que precedeu o despacho (bloco `## Classificação (resultado bruto)` do próprio `checker-dw-6-0a-01-r1.md`) ordenou os candidatos por família distinta da autoria: 1º Agy `gemini-3.8-flash-medium`, 2º Codex `gpt-5.6-terra` (fallback), 3º Claude `sonnet` ("último recurso").
- O envelope original do parecer (`## Envelope original`) traz `usage.thinking_tokens: 5047` e `usage.cache_read_tokens: 191339` — campos de telemetria característicos da API Anthropic (extended thinking + prompt caching), incompatíveis com uma resposta Agy/Gemini Flash. Isso é evidência técnica de que a sessão executada **não foi** o candidato citado em `deferred-work.md`.
- `PROJECT.md` exige explicitamente: *"Antes de cada revisão, o Orquestrador registra o modelo e a família efetivos e escolhe um Checker de família distinta do Maker"*, e sob `checker_independence: preferred`, uso de família igual à autoria em sessão nova deve abrir pendência registrada (`same_family_fresh_session`) em `review_followups` do cabeçalho global. Nada disso está presente: não há registro do modelo/família efetivos, não há `same_family_fresh_session`, não há entrada em `review_followups`.
- `resume.json.effective_authors = ["openai"]` (a correção foi do Orquestrador, catalogado como família OpenAI GPT em `PROJECT.md`), o que também contradiz a própria justificativa do classificador para o candidato Claude ("compartilha a família Anthropic do autor") — mais um sinal de que o encadeamento de decisão não foi coerente nem auditável.

## Determinação

A aprovação r1 (`approved`, zero action items/deferred) **não pode ser certificada como aprovação regular**. Não é porque o modelo efetivamente usado (aparentemente Claude/Anthropic, por telemetria) estivesse fora do catálogo — ele consta como candidato de fallback legítimo na própria classificação — mas porque:

1. a identidade do executor não foi registrada nem citada corretamente (citação em `deferred-work.md` aponta para candidato diferente do que a telemetria indica);
2. a mudança de candidato não passou pelo procedimento obrigatório de registro de fallback/independência (`same_family_fresh_session` + pendência em `review_followups`);
3. a cadeia de procedência que sustenta essa aprovação no manifesto de retomada (`resume.json`) tem dois digests que não conferem contra o conteúdo real.

Isso caracteriza **aprovação por candidato não autorizado/não verificado**, não aprovação regular — mesmo com verdict favorável no mérito técnico do diff. O parecer r1 deve ser **preservado como registro do desvio** (não apagado, não reclassificado retroativamente), e a pendência DW-6.0A-01 deve ser **reaberta para regularização**: nova classificação e nova revisão por candidato efetivamente registrado, em sessão limpa, com identidade e família citadas e verificáveis.

## Proposta de regularização (encaminhamento)

1. **Não remover** `checker-dw-6-0a-01-r1.md` nem a linha "RESOLVIDO" atual de `deferred-work.md`; anexar nota de desvio referenciando esta análise (digests mismatch + identidade não verificada), preservando o parecer original como evidência histórica.
2. **Corrigir o `resume.json`** desta fase: recomputar e substituir os digests de `PROJECT.md#frontmatter` e de `checker-dw-6-0a-01-r1.md#Parecer` pelos valores reais acima, ou marcar essas duas entradas como `digest_mismatch: true` até nova geração do manifesto.
3. **Reclassificar a pendência** com o Classificador (schema v2, papel `checker`, fase `review`), citando explicitamente `effective_authors: ["openai"]` como autoria a evitar por família.
4. **Nova revisão** por candidato do catálogo que seja, de fato, executado e citado com harness/modelo/família efetivos registrados no artefato (não apenas no bloco de classificação prévia) — preferencialmente Agy `gemini-3.8-flash-medium` (1º candidato família-distinta); caso indisponível, registrar formalmente o fallback com `same_family_fresh_session` e abrir a pendência em `review_followups`, conforme o contrato.
5. Marcar o item em `deferred-work.md` como **regularização em andamento**, não mais "RESOLVIDO", até a nova revisão concluir com identidade verificável.

## Briefing estruturado para a nova revisão (a ser despachado quando autorizado)

```
unit: DW-6.0A-01 (deferred-work.md, item "internal/connectorgate/release_test.go:243")
diff: release_test.go — troca do literal "uso: lynvia-mkauth-connector [--version]" pelo prefixo
      estável "uso: lynvia-mkauth-connector [--version" (sem "]"), 1 linha
autoria efetiva: Orquestrador, família OpenAI GPT (resume.json effective_authors)
motivo da reabertura: parecer r1 (checker-dw-6-0a-01-r1.md) citado em deferred-work.md como
  "Checker Agy gemini-3.8-flash-medium" não confere com a telemetria do envelope original
  (thinking_tokens/cache_read_tokens de padrão Anthropic); nenhum registro de modelo/família
  efetivos, nenhum same_family_fresh_session, nenhuma entrada em review_followups.
escopo da nova revisão: confirmar (a) especificidade do novo prefixo como oráculo discriminante,
  (b) preservação das asserções de --version e SIGTERM, (c) ausência de outros oráculos frágeis
  no arquivo — mesmo escopo do r1, sem reabrir o mérito além do necessário.
requisito de citação: registrar harness, modelo e família efetivos no artefato de saída;
  se família repetir a do autor, declarar same_family_fresh_session e abrir pendência em
  review_followups conforme checker_independence: preferred.
evidência a preservar: checker-dw-6-0a-01-r1.md (íntegro, como registro do desvio).
```

Nenhum arquivo foi alterado e nenhum agente foi despachado nesta sessão — conforme o aviso restritivo, esta é apenas a proposta de condução e o briefing.