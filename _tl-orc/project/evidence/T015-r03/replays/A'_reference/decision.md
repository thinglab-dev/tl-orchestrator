## Avaliação formal — Task Native T009, parecer do Checker r07

### 1. Vínculo formal do parecer (spec_revision / content_id)

Conferido cruzando `resume.json`, `task-T009-spec.md` e o JSON de veredito em `T009-r07.md`:

- `resume.json.spec_revision` = `4197dea48f75cd14`, coincide com o digest da seção `## Spec` no manifest (`4197dea48f75cd14e7a32...`) e com o valor citado pelo Checker no primeiro item rejeitado ("A seção Spec produz `4197dea48f75cd14`").
- `resume.json.active_work_ref` traz `content_id: 0de10d60149cf7c038a0954c6aec302c9fcd111e:938ddfb319408b79`. O Checker cita exatamente o mesmo HEAD (`0de10d60149cf7c038a0954c6aec302c9fcd111e`) e o mesmo SHA-256 truncado (`938ddfb319408b79...`) como "correspondente ao alvo".

**Alvo e spec_revision estão corretamente vinculados** — não há divergência de árvore ou de especificação entre o parecer e o checkpoint.

### 2. Independência do Checker — ERRO BLOQUEANTE DE GOVERNANÇA encontrado

Este é o ponto crítico e a razão pela qual **não proponho fechamento**.

- `PROJECT.md` fixa, para este piloto especificamente (não a política geral `preferred`), a restrição `checker_independence: required` — "a revisão do piloto exige família distinta da autoria efetiva, registrada como restrição de entrada" — sem fallback de mesma família admitido.
- O Review record do Checker r07 declara: `independence: distinta de toda autoria efetiva (Google, Anthropic)` → **cobre apenas duas famílias**.
- Porém `resume.json` — a fonte canônica deste checkpoint, listada em `effective_authors` — declara **três** famílias: `["anthropic", "google", "openai"]`.
- Rastreei a origem de cada uma:
  - **Anthropic**: autor original do protótipo (`T009-mechanical-check.py`, docstring: "autoria original: Anthropic") + correção própria do Orquestrador em r07 (linha 185/276 da análise, "autoria Anthropic").
  - **Google**: Maker Agy `gemini-3.8-flash-high`, autor do rework 5 da análise e evolução do protótipo.
  - **OpenAI**: não justificada no texto do Review record, mas presente no `resume.json`. A única atividade OpenAI neste round é `T009-r07-classifier-1` (`codex/gpt-5.6-luna`), registrada no `Agent runs` como parte do processo deste próprio parecer r07.
- O Checker r07 é `codex/gpt-6-astra` — **também OpenAI**, mesmo harness (`Codex`) da entrada classificadora.

Ou seja: pela própria contabilidade de `resume.json` (documento que a spec trata como fonte de autoria efetiva, não uma lista "composta na hora"), o Checker pertence à mesma família (`OpenAI`) que um dos autores efetivos listados. O texto do veredito do Checker omite essa família ao declarar independência, cobrindo apenas Google/Anthropic. Sob restrição `required` — que não admite fallback de mesma família em hipótese alguma — essa é uma **incompatibilidade de independência não resolvida**, exatamente o tipo de defeito que a governança deste piloto exige verificar antes de qualquer proposta de fechamento (item 2 da instrução).

Não decido aqui, de forma leiga, se a classificação despachante (`gpt-5.6-luna`) *deveria* contar como autoria efetiva do conteúdo revisado (ela não escreveu `T009-analysis.md`/`mechanical-check.py`; apenas selecionou o candidato a Checker deste round). Mas essa é precisamente a ambiguidade que bloqueia o fechamento: **ou** `resume.json` está errado ao listar `openai` como autor efetivo (e precisa correção/justificativa), **ou** o Review record está incompleto/enganoso ao restringir a independência declarada a duas famílias quando a fonte canônica lista três — e nesse caso o parecer `approved` foi emitido sem demonstrar a independência exigida pelo próprio pin do piloto.

### 3. Distinção do mérito de conteúdo (não bloqueante)

Separado do problema de independência, o exame do conteúdo do parecer é sólido:

- As 7 rejeições (AC01–AC06 + divergência de árvore) trazem citação por arquivo:linha, comandos reexecutados (`--self-test`, `validate_repository.py`, sondas em memória) e resultados coerentes com `pilot_summary.json` (38 casos, 33 sem despacho).
- A limitação residual de "procedência por conteúdo" (linha 276 de `T009-analysis.md`) é tratada corretamente como **classe aceita e encaminhada a T010**, não como defeito a corrigir — o próprio AC02 da spec já previa essa lacuna como resíduo normativo, e a "fase consultiva" (c01) já havia formalizado esse encaminhamento antes do r07. **Não há aqui motivo para exigir rework**; tratar essa limitação como bloqueio seria incorreto.
- O veredito `approved` **não pode**, contudo, ser tratado como passe livre só porque o texto do conteúdo é robusto — a robustez do conteúdo não supre a checagem de independência do próprio Checker, que é um pré-requisito formal e distinto.

### 4. Encaminhamento proposto

Dado (2), a única condução compatível com a autorização vigente é **impedimento fundamentado**, não fechamento:

> **T009 r07 — IMPEDIDO para fechamento.** O parecer `approved` do Checker r07 (`codex/gpt-6-astra`, restrição `checker_independence: required`) não demonstra independência de toda a autoria efetiva registrada em `resume.json` (`anthropic`, `google`, `openai`). O texto do Review record declara independência apenas frente a Google e Anthropic, omitindo a família OpenAI — a mesma família do próprio Checker — sem justificar por que a atividade OpenAI do round (`T009-r07-classifier-1`, `codex/gpt-5.6-luna`) foi excluída do cômputo de autoria efetiva apesar de estar listada como tal na fonte canônica do checkpoint. Sob `required`, essa reconciliação é pré-condição de qualquer aprovação válida; sua ausência é erro bloqueante de governança, independentemente do mérito técnico do conteúdo revisado (que, isoladamente, está bem fundamentado e não apresenta defeito residual além da limitação já aceita e encaminhada a T010).
>
> **Ação exigida antes de nova decisão de fechamento:** reconciliar a lista de autoria efetiva — corrigindo `resume.json` com justificativa (se `openai` não deveria constar) ou emitindo novo parecer de Checker de família comprovadamente distinta de todas as três famílias listadas (Anthropic, Google, OpenAI), respeitando o pin do piloto e sem fallback de mesma família, dado que a restrição desta revisão é `required`.
> **Não** se trata de rework do conteúdo de T009 (AC01–AC06 seguem satisfeitos no nível fixado pela spec); trata-se exclusivamente de saneamento do requisito de independência do Checker antes de qualquer registro de fechamento.

Nenhum arquivo foi alterado e nenhum agente foi despachado nesta sessão, em conformidade com o modo somente leitura solicitado.
