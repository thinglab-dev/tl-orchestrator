## Avaliação formal — T009 r07

### 1. Vínculo do parecer (spec_revision / content_id / autorização)

Confirmado por leitura direta dos arquivos congelados:

- `resume.json:5` — `spec_revision: 4197dea48f75cd14`, idêntico ao hash da seção `## Spec` em `task-T009-spec.md` (linha 1, campo `spec_revision`) e ao `digest` registrado em `resolved_context[0]` (`4197dea48f75cd14e7a32802e642ef2bf3bdcc3b7530ef4fdfa6439c0db860eb`).
- `content_id` em `resume.json:5` = `0de10d60149cf7c038a0954c6aec302c9fcd111e:938ddfb319408b79`, que casa com o par HEAD/SHA-256 citado no primeiro item `rejected` do veredito (`T009-r07.md:31`): HEAD `0de10d601...` e SHA-256 `938ddfb319408b79...`, "correspondente ao alvo".
- A autorização vigente é a `## Piloto de avaliação do Astra como Checker` em `PROJECT.md:83-97`, que fixa o pin `gpt-6-astra/high` e, crucialmente, declara: **"a revisão do piloto exige família distinta da autoria efetiva, registrada como restrição de entrada, embora a política geral seja `preferred`"** (`PROJECT.md:87-88`) — isso é o `restrição: required` citado em `T009-r07.md:19` e na `Verification profile` da spec (`task-T009-spec.md:34`).

Até aqui, alvo e vínculo formal batem: não há divergência de árvore/spec.

### 2. Achado que muda a conclusão: violação da independência `required`

`T009-r07.md:19` declara: `independence: distinta de toda autoria efetiva (Google, Anthropic)`.

Isso é **incompleto por omissão** frente à própria fonte autoritativa deste checkpoint. `resume.json:62-66` (`effective_authors`) lista **`["anthropic", "google", "openai"]`** — três famílias, não duas. O Checker despachado em r07 é `codex/gpt-6-astra`, família **OpenAI** (`T009-r07.md:6`, coluna `family`), a mesma família também usada pelo Classificador nesta rodada (`T009-r07.md:5`, `gpt-5.6-luna`, família OpenAI).

`PROJECT.md:48-54` define autoria efetiva como "todas as famílias que produziram o conteúdo revisado, incluindo reworks, experimentos comparativos e correções próprias do Orquestrador" e é explícito: sob `required`, um candidato de mesma família da autoria efetiva **não pode ser aceito de nenhuma forma** ("restrição específica `required`, como a deste piloto, impede esse fallback" — `PROJECT.md:52-53`). O próprio protótipo em avaliação implementa essa regra e a testa no caso 15 do piloto (`case_15_r4_required_same_family.json`, tabela em `T009-analysis.md:212`): quando todos os candidatos pertencem a famílias autoras sob `required`, o resultado correto é **BLOQUEADO com ponto de retomada**, nunca uma liberação de despacho.

Ou seja: se `resume.json` está correto ao listar OpenAI como autoria efetiva de T009, então o próprio Checker r07 (família OpenAI) estava inelegível para esta revisão sob a restrição `required` vigente — e, como as três famílias do catálogo de Checker (Codex/OpenAI, Claude/Anthropic, Agy/Google) coincidem exatamente com as três famílias autoras declaradas, **não existe candidato independente disponível no catálogo**, configurando o mesmo impasse estrutural do caso 15: aprovação mecânica possível, mas despacho deveria ter sido bloqueado com ponto de retomada para decisão do mantenedor (relaxar para `preferred` ou registrar exceção fundamentada), não seguir como aprovação silenciosa.

O parecer do Checker cita "Google, Anthropic" e silencia sobre OpenAI — que é justamente sua própria família. Isso não está endereçado em nenhum dos 7 itens `rejected` do veredito (`T009-r07.md:28-63`); nenhum deles trata da própria independência do Checker frente a OpenAI como autor.

### 3. Distinção exigida pela tarefa: limitação aceita vs. defeito bloqueante

- **Limitação aceita (classe "procedência por conteúdo", encaminhada a T010):** está corretamente delimitada em `T009-analysis.md:185` — o envelope de procedência rastreia a *localização declarada* de cada entrada, não o *conteúdo* dela (valores de pins/autoria não comparados, fontes genéricas, etc.). Isso é uma limitação de escopo explicitamente reconhecida na spec e nas contraprovas AC02 (`T009-r07.md:39-41`), sem indício de regressão. **Não bloqueia.**
- **Defeito bloqueante (achado acima):** a independência do Checker é critério obrigatório e explicitamente `required` para este piloto — não é uma limitação declarada na spec, é uma condição de validade do próprio parecer de aprovação. Se confirmada a presença de OpenAI em `effective_authors`, o parecer `approved` foi produzido por um Checker inelegível, o que **invalida a própria aprovação como prova de conformidade ao AC relativo a independência (parte do escopo AC02/verification profile)**, independentemente do mérito técnico do conteúdo revisado.

Não estou tratando `approved` como passe livre: a conferência de alvo/spec/content_id passou, mas a conferência da condição de independência exigida pela própria autorização vigente não se sustenta com os dados apresentados no parecer.

### 4. Encaminhamento proposto

Dentro da autorização vigente, **não recomendo fechamento de T009 com base neste parecer r07 como está**. Recomendo **impedimento fundamentado**, com duas ramificações possíveis a esclarecer antes de qualquer novo despacho (nenhum despacho é proposto aqui — apenas a decisão de rota):

**(a) Se `effective_authors: openai` em `resume.json` estiver correto** (isto é, alguma rodada anterior r01–r06 de T009 teve o conteúdo revisado produzido/reworkado por família OpenAI, e não apenas o Classificador desta rodada): o parecer r07 é inválido quanto à independência `required`; não há candidato elegível no catálogo atual para Checker desta Task; o caso deve ser registrado como bloqueado com ponto de retomada (mesmo padrão do case_15), escalado ao mantenedor para decidir entre (i) relaxar a restrição para `preferred` nesta Task específica com justificativa registrada, ou (ii) aceitar exceção documentada de mesma família em sessão nova (`same_family_fresh_session`), já que nenhuma família alternativa existe.

**(b) Se `effective_authors` estiver desatualizado/impreciso** (por exemplo, se OpenAI ali só reflete o papel do Classificador desta própria rodada r07, e não autoria de conteúdo revisado em rounds anteriores): a inconsistência entre `resume.json` e o texto do parecer do Checker (que cita apenas Google/Anthropic) ainda precisa ser reconciliada e documentada — a origem da lista de autoria efetiva deve ter procedência verificável, não pode ficar como divergência não explicada entre duas fontes do mesmo checkpoint.

Em ambos os casos, a rota correta agora é **impedimento**, não fechamento, até essa reconciliação ser feita por quem tem acesso à cadeia de rounds r01–r06 (fora do escopo desta leitura, que só recebeu o checkpoint congelado).

### Minuta de briefing de condução (proposta, não executada)

```
Task: T009 (r07) — impedimento, não fechamento
Motivo: parecer approved do Checker r07 (codex/gpt-6-astra, família OpenAI) não
demonstra independência exigida como `required` frente à autoria efetiva declarada
em resume.json (["anthropic","google","openai"]), que inclui a própria família do
Checker. O parecer cita independência apenas de "Google, Anthropic" (T009-r07.md:19),
omitindo OpenAI.
Ação solicitada (fora deste teste, sem despacho): reconciliar a origem de
`effective_authors` (procedência por round r01–r06) com o texto do parecer.
  - Se OpenAI for autor confirmado: não há candidato independente no catálogo de
    Checker (Codex/OpenAI, Claude/Anthropic, Agy/Google = as 3 famílias autoras);
    registrar BLOQUEADO com ponto de retomada e escalar ao mantenedor para decidir
    relaxamento para `preferred` ou exceção `same_family_fresh_session` documentada.
  - Se OpenAI não for autor de conteúdo (só rotulagem imprecisa do Classificador
    desta rodada): corrigir `resume.json` e reemitir o parecer de independência
    citando as 3 famílias corretamente antes de considerar fechamento.
Limitação não bloqueante, mantida para T010: classe "procedência por conteúdo"
(T009-analysis.md:185) — rastreia localização declarada, não conteúdo; sem
regressão nas contraprovas AC02 (T009-r07.md:39-41). Não é motivo de impedimento.
Nenhum arquivo alterado, nenhum agente despachado (modo somente leitura).
```
