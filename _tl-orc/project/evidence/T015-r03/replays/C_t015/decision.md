## Avaliação formal — DW-6.0A-01

### O que os registros mostram

`deferred-work.md` contém **duas entradas** para DW-6.0A-01:

1. Uma entrada riscada (`~~DW-6.0A-01~~`), marcada **"RESOLVIDO em 2026-09-08"**, atribuindo a correção a "Checker Agy `gemini-3.8-flash-medium`, `approved`, zero achados", referenciando `pareceres/checker-dw-6-0a-01-2026-09-08.md`.
2. Logo abaixo, uma entrada **não riscada**, descrevendo o mesmo problema (oráculo de usage em `release_test.go:243` desatualizado em relação ao CLI real do `lynvia-mkauth-connector`), com condição de quitação explícita ainda pendente e o aviso **"Bloqueia `make check` do módulo `lynvia` inteiro"**.

O parecer `checker-dw-6-0a-01-r1.md` fornecido nesta rodada é **outro artefato**, com veredito `approved` e três hipóteses de fragilidade rejeitadas (não achados) — consistente com o conteúdo técnico da entrada riscada, mas gerado por um harness/modelo diferente do citado no texto do deferred-work (aqui não há metadado de harness no corpo do parecer; o candidato aparece apenas no bloco de classificação embutido).

### Achado central: candidato Checker fora do catálogo

O bloco `## Classificação (resultado bruto)` embutido em `checker-dw-6-0a-01-r1.md` mostra que o Classificador ordenou como **primeiro candidato ao papel de Checker**:

```
harness: agy, model: gemini-3.8-flash-medium, effort: medium
```

Conferindo contra `## Perfil de despacho > ### Catálogo permitido` em `_tl-orc/PROJECT.md` (raiz, `work_method: native`):

| Papel | Harness | Modelo | Effort |
|---|---|---|---|
| Classificador | Agy | `gemini-3.8-flash-medium` | medium |
| Searcher | Agy | `gemini-3.8-flash-medium` | medium |
| **Checker** | Agy | `gemini-3.1-pro-high` | **high** |

`gemini-3.8-flash-medium/medium` **não consta na linha de Checker**. É um par catalogado apenas para Classificador e Searcher. A cláusula do catálogo é explícita: *"Pares fora do catálogo são inválidos e devem ser rejeitados."*

Isso não é um problema de independência de revisor (Agy é família distinta do autor efetivo `openai`, então `checker_independence: preferred` estaria satisfeito nesse eixo) — é um **erro de catálogo**: o Classificador aparentemente reaproveitou o par fixo de si mesmo (o candidato Classificador padrão) como se fosse um candidato de Checker válido, sem checar a linha correta da tabela. Nenhum dos três candidatos listados no bloco de classificação (`agy/gemini-3.8-flash-medium/medium`, `codex/gpt-5.6-terra/medium`, `claude/sonnet/medium`) está em *effort* `high`, que é o único effort autorizado para Checker em qualquer harness do catálogo atual.

### Achado secundário: evidência de diff ausente

`release_test.diff` no checkpoint congelado tem **0 bytes** (digest confere com sha256 de string vazia — verificado). Ou seja, a rodada r1 teria sido "aprovada" sem que o diff real da mudança estivesse disponível como artefato anexo nesta cadeia de evidência — o conteúdo técnico só existe reconstituído em prosa dentro de `deferred-work.md`. Uma nova revisão precisa do diff real de `release_test.go` anexado, não apenas da narrativa.

## Distinção: aprovação irregular vs. aprovação regular

A aprovação r1 **não é uma aprovação regular do papel Checker**: foi emitida por um par modelo/effort não autorizado para esse papel (era autorizado apenas para Classificador/Searcher, em effort inferior ao piso exigido). Ela não pode ser tratada como quitação válida da pendência, mesmo que o conteúdo técnico do parecer pareça correto — legitimidade procedimental (par autorizado no papel certo) é pré-condição, não é suprida por qualidade do conteúdo.

Isso também explica a inconsistência em `deferred-work.md`: a entrada foi riscada como "resolvida" com base nessa aprovação irregular, mas a entrada de bloqueio original permanece ativa e não removida — o próprio arquivo delata o desvio ao preservar as duas versões lado a lado.

## Encaminhamento proposto

1. **Preservar** `checker-dw-6-0a-01-r1.md` e a entrada riscada em `deferred-work.md` inalterados, como registro do desvio (não editar nem apagar).
2. **Reclassificar** a revisão: manter tier `simple` (mudança de uma linha em asserção de teste, sem produção afetada — condiz com os fatos já levantados pelo próprio Classificador), mas corrigir o par Checker para a linha correta do catálogo, respeitando `checker_independence: preferred` contra `effective_authors: ["openai"]` (família Codex é a autora efetiva; famílias não-Codex têm prioridade):
   - 1ª opção: `claude/sonnet/high` ou `claude/claude-opus-5/high` (família não autora, catalogado para Checker).
   - 2ª opção: `agy/gemini-3.1-pro-high/high` (família não autora, catalogado para Checker).
   - `codex/gpt-5.6-terra/high` (padrão da cadeia) e `codex/gpt-6-astra/high` (piloto) compartilham família com a autoria efetiva; sob `preferred`, só devem ser usados se as opções acima estiverem comprovadamente indisponíveis, registrando `same_family_fresh_session` — não é o caso aqui.
3. **Despachar nova revisão (r2)** em sessão limpa, candidato registrado do catálogo (não reaproveitar sessão/contexto de r1), anexando o diff real de `release_test.go` (hoje ausente no checkpoint — `release_test.diff` está vazio) como evidência obrigatória.
4. **Corrigir `deferred-work.md`**: não riscar a entrada original até que r2 aprove regularmente; anotar explicitamente no changelog da tarefa que a aprovação r1 foi um desvio de catálogo (candidato Checker inválido), não uma quitação válida.

## Briefing estruturado para a nova revisão (r2)

```
work_item: DW-6.0A-01
status: pendência reaberta — aprovação r1 invalidada por desvio de catálogo
tier: simple
effective_authors: [openai]
checker_independence: preferred
candidatos_autorizados_papel_checker:
  - claude/sonnet/high        (preferido — família não autora)
  - claude/claude-opus-5/high (preferido — família não autora)
  - agy/gemini-3.1-pro-high/high (preferido — família não autora)
  - codex/gpt-5.6-terra/high  (fallback mesma família — requer justificativa de indisponibilidade)
escopo_da_revisao:
  - confirmar que release_test.go:242 troca o literal fechado
    "uso: lynvia-mkauth-connector [--version]" pelo prefixo estável
    "uso: lynvia-mkauth-connector [--version" (sem "]"), preservando
    capacidade discriminatória (sonda contrafactual + make check completo)
  - anexar diff real (ausente no checkpoint atual — release_test.diff = 0 bytes)
  - reavaliar as 3 hipóteses já rejeitadas em r1 (oráculo de usage,
    --version, SIGTERM/lifecycle) de forma independente, sem herdar
    a conclusão de r1 como pressuposto
evidencia_a_preservar: checker-dw-6-0a-01-r1.md (registro do desvio, não editar)
acao_vedada: riscar/"resolver" a entrada de deferred-work.md sem aprovação
  regular do papel Checker por candidato catalogado em effort high
```

Nenhum arquivo em disco foi modificado e nenhum agente foi despachado — esta resposta é apenas a proposta de condução e o briefing solicitados, conforme o aviso restritivo.
