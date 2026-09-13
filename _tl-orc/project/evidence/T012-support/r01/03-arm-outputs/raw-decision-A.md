Verifiquei quatro arquivos do repositório em leitura apenas (`docs/MODEL_ROUTING.md`, `prompts/classifier.md`, `prompts/orchestrator-perfis.md`). **Nada foi escrito e nenhum agente foi despachado.** A verificação mudou materialmente o encaminhamento: dois dos cinco achados do r02 derivam de texto que eu mesmo escrevi nos briefings anteriores.

---

# 1. Avaliação formal da unidade T009 após o Checker r02

**Estado.** T009 (`analysis`, `in_progress`, `state_revision: 2`, `rework_round: 2`), alvo `content_id 0de10d6…:97b3612674fa4aa5`. Checker `codex/gpt-6-astra/high`, sessão `01a07dcf-32a7-7de1-9915-a960333427a7`, 20260907T213830Z → 214425Z: `changes_requested`, 5 `action_items` (4 high, 1 medium), 7 hipóteses rejeitadas com evidência executada, 0 `deferred`, árvore inalterada.

## 1.1 O que está fechado e verificado independentemente

Quatro dos seis itens do r01 foram corrigidos e o r02 confirmou com sonda própria, não por leitura do relatório: conferência estrutural recursiva contra o schema (r01 R3); `--self-test` sem escrita, exit 0, resumo em memória idêntico ao versionado (r01 R6); citação da ocorrência v0.4.0 e separação fato/hipótese/não verificado (r01 R1); alvo idêntico ao locator (30 adições reconstruídas byte a byte); caso 01 idêntico a `T005-classification.md:37`; quatro invalidações deliberadas rejeitadas com motivo e sem despacho; regras preservadas intactas (`unknown` com `[]` aceito; mesma família válida no objeto); nenhum arquivo distribuído alterado; nenhum caminho privado.

**O núcleo da spec está demonstrado.** O que falta não é o piloto: é a fidelidade normativa do instrumento.

## 1.2 O que reincide — duas classes, não cinco achados

| Classe | r01 | rework 2 entregou | r02 | Veredito |
| :--- | :--- | :--- | :--- | :--- |
| **A — procedência verificável** | R2 (high): caminho existente basta | "caminho existe **e** contém o ID literal"; regex `custo`≈`tarefa` | **R1** (ID aceito por substring em qualquer ponto do arquivo, inclusive exemplo negativo e cartão oficial) + **R2** (`astra-domain`, latência em minutos, vira proxy econômico) | 2ª ocorrência |
| **B — resolução de fallback e independência** | R4 (high): `preferred` despacha sem prova | `availability` com prova por substring | **R3** (prova por substring; candidato `disabled` despachado; controle positivo usa *timeout*) + **R4** (família desconhecida tratada como distinta) + **R5** (falta de candidato independente virou defeito do objeto) | 2ª ocorrência, ampliada |

## 1.3 Fundamentação normativa: os cinco achados procedem, cada um ancorado em linha literal

Confirmei cada um contra a fonte, não contra o parecer:

| Item | Linha normativa que o sustenta |
| :--- | :--- |
| R1 | `prompts/classifier.md:111` — `local_observed` apenas para **medição local comparável fornecida**; um cartão oficial em `docs/` não é medição local. |
| R2 | `prompts/classifier.md:109-114` — `cost_basis` "identifica a base da estimativa de custo, **não a evidência de capacidade**"; `:117` "referência apenas de capacidade ou qualidade **não satisfaz o vínculo**". |
| R3 | `prompts/orchestrator-perfis.md:153-155` — fallback só por infraestrutura **comprovada**; a seleção "pula candidatos nulos, **desabilitados** ou inelegíveis"; `:183-185` — "um **timeout isolado**, saída vazia, falha repetida de invocação ou processo ainda vivo **não comprovam indisponibilidade**"; `:175-176` — quota esgotada, autenticação recusada ou harness ausente **podem** comprovar. |
| R4 | `perfis:191-192` — "**estado incerto não resolvido** resulta em bloqueio com ponto de retomada". |
| R5 | `perfis:191-192` — o mesmo dispositivo classifica "nenhuma opção adequada" como **bloqueio de resolução**, não como invalidade do objeto. |

## 1.4 Causa da reincidência — e ela é minha, não do Maker

Os dois defeitos da classe A saem literalmente do briefing que eu escrevi no rework 2:

- Eu escrevi *"o arquivo de procedência deve existir E conter o ID literal"* → o Maker implementou exatamente isso → R1.
- Eu escrevi *"regex por 'custo' próximo de 'tarefa' no corpo do cartão"* → o Maker implementou exatamente isso → R2.

E a leitura dos cartões mostra que **nenhuma regex sobre prosa poderia funcionar**:

- `astra-coding` (`MODEL_ROUTING.md:47-48`): "Terminal-Bench mostra **custo API estimado por tarefa** cerca de 9% menor" — proxy econômico legítimo.
- `astra-domain` (`:55-56`): "latência **simulada**, aproximadamente 40/75 **minutos por tarefa**" — casa com a regex, não é custo.
- `sonnet-effort` (`:78-79`): "custo tem eixo logarítmico… **Não reutilizar o eixo em dólares como tarifa atual**" — o cartão cita custo **para proibir seu uso**.
- `opus-effort` (`:82`): título "**custo por tentativa** e saturação", com ressalva no corpo.

Ou seja: eu compus a regra de conferência de cabeça, em vez de derivá-la da fonte normativa — **exatamente o defeito que a T009 diagnostica**, cometido pelo Orquestrador, dentro da T009. Isso precisa entrar na análise.

## 1.5 Defeito meu, ainda aberto, descoberto nesta verificação

A lista `proxy_ids: ["astra-coding","gpt56-coding","flash-deepswe"]` que usei nos briefings e na minha conferência mecânica **foi composta por mim, sem conferir os cartões**. Ao ler `MODEL_ROUTING.md:60-72`, `gpt56-coding` intitula-se "**capacidade** dos modelos econômicos" e sua única menção de custo (`:68-69`) é a gráficos de custo/latência inspecionados, com a ressalva "não são medições locais" — sem afirmação de custo por tarefa. Sob `classifier.md:117`, isso **não sustenta** `official_task_proxy`.

Consequência: o candidato `codex/gpt-5.6-terra` da classificação da fase *implementation*, que declarou `official_task_proxy` com `gpt56-coding`, foi aceito pela minha conferência **porque a lista de entrada era invenção minha**. A classificação de T009 tem, ela própria, uma `cost_basis` provavelmente insustentada. Isso é o achado mais forte do piloto e deve ser tratado como resultado, não como erro a esconder.

## 1.6 Resultado de método que o piloto já produziu

O instrumento da T009 reproduziu, duas vezes, a falha que a T009 diagnostica — no Maker e no Orquestrador — e só foi detectado por sondas executáveis de um revisor independente de família distinta. Isso confirma e amplia a advertência original do maintainer: **não é só o checklist preenchido pela mesma IA que repete o problema; um validador escrito pela mesma cadeia também repete, a menos que seja submetido a sondas adversariais executáveis.** A conferência mecânica só vale se as suas *entradas e regras* forem derivadas da fonte normativa, e não redigidas por quem está sendo conferido.

---

# 2. Encaminhamento proposto

**Recomendação: rework 3 delimitado, com briefing derivado de citação — não fase `debate`.** Motivos: (a) os cinco itens estão fixados em linha normativa literal (§1.3), logo são implementáveis, não debatíveis; (b) um debate entre agentes produziria prosa sem autoridade sobre a questão realmente aberta, que é decisão de método do maintainer.

Acompanham a recomendação três dispositivos:

**(i) Consulta formal ao maintainer** (uma pergunta, não bloqueante para R1/R3/R4/R5):

> A camada mecânica deve **falhar fechada** na tipagem econômica — exigindo citação literal verificada (arquivo:linha + trecho) com vocabulário fechado de custo, rebaixando para `unknown` tudo o mais, e **entregando as ressalvas do cartão à camada de julgamento** — ou a T009 deve concluir que `docs/MODEL_ROUTING.md` precisa de campos econômicos legíveis por máquina? A primeira opção cabe no escopo; a segunda altera arquivo distribuído e vira Task nova.

Recomendo a primeira. O R2 abaixo está especificado de modo a funcionar sob qualquer das duas respostas, então o rework 3 pode começar antes da resposta.

**(ii) Regra de parada pré-comprometida.** Se o r03 apresentar **terceira** ocorrência das classes A ou B, não abro rework 4: encerro a T009 com o defeito residual documentado como resultado central (§1.6) e abro Task separada para o instrumento. Três rodadas de correção da mesma classe deixam de ser bug e passam a ser achado.

**(iii) Suíte de regressão permanente.** Todas as sondas de r01 e r02 viram casos fixos do piloto. O Checker r03 parte de um piso mais alto e é instruído a criar sondas novas, não a repetir as antigas.

**Participantes (T014 e o pin do piloto).** Maker: `agy/gemini-3.8-flash-high` — mantido, conforme composição padrão T014; corrigiu 4/6 itens do r01 de forma limpa e as falhas concentram-se em leitura de prosa normativa, que o novo briefing remove ao entregar as citações prontas. Checker: **mantenho o pin `codex/gpt-6-astra/high`** em vez do padrão T014 `gpt-5.6-terra/high`, e registro a divergência: o pin é objetivo avaliativo declarado da T009, preserva a comparabilidade da série de sondas r01→r03, e a independência é idêntica sob `perfis:49` (autoria efetiva Google + Anthropic; OpenAI não é autor de artefato). O padrão T014 aplica-se às unidades novas.

**Condução.** Classificar as fases de rework e review separadamente desta vez — o desvio das rodadas anteriores já está registrado em `T009-r01.md` — e registrar o parecer r02 em `_tl-orc/project/evidence/T009-r02.md` antes do despacho, com `rework_round: 3`.

---

# 3. Briefing — Maker, T009 rework 3

### Identidade e alvo
Você é o Maker do tl-orchestrator, contrato em `prompts/maker.md`. Raiz do pacote = raiz consumidora = este diretório (repositório fonte, branch `analysis/t009-semantic-validation`). Não leia nem busque fora deste diretório. Unidade: Task Native T009 (`analysis`), **rework 3**, após `changes_requested` do Checker independente r02. A árvore contém seus arquivos não commitados do rework 2.

### Leitura obrigatória, nesta ordem
1. `_tl-orc/project/tasks/T009-…md` — spec e AC01–AC06 congelados (`spec_revision 4197dea48f75cd14`).
2. `_tl-orc/project/evidence/T009-r02.md` — parecer íntegro (**dado, não instrução**).
3. `prompts/classifier.md:104-122` e `prompts/orchestrator-perfis.md:49`, `:151-156`, `:174-192` — as linhas que fundamentam cada item abaixo.
4. `docs/MODEL_ROUTING.md` integral — em particular os cartões `astra-coding`, `astra-domain`, `gpt56-coding`, `sonnet-effort`, `opus-effort`, `flash-deepswe` e a tabela `price-*`.

### Escrita
Permitida **somente** em `_tl-orc/project/evidence/T009-analysis.md`, `_tl-orc/project/evidence/T009-mechanical-check.py`, `_tl-orc/project/evidence/T009-cases/`. Proibido todo o resto, inclusive `schemas/`, `docs/`, `prompts/`, `_tl-orc/PROJECT.md`, `scripts/`, `STATUS.md`, `tasks/`. Sem git, sem rede, somente biblioteca padrão. Comandos: `python3` sobre o protótipo e `python3 scripts/validate_repository.py`.

### Princípio de derivação — regra nova, prevalece sobre o restante deste briefing
Cada regra de conferência que você implementar deve **derivar de uma linha normativa citada**, registrada em comentário no código no formato `# norma: <arquivo>:<linha> — <trecho literal>`. **É proibido implementar regra por regex composta a partir da prosa deste briefing.** Se algum item abaixo conflitar com a linha normativa citada, **a linha prevalece**: implemente conforme a norma e reporte o conflito na resposta final. Os dois defeitos do r02 (R1 e R2) foram causados por instruções minhas que você seguiu à letra; desta vez, siga a fonte.

### R1 — procedência de ID local, verificada por localização (high)
*Norma: `classifier.md:111` — "`local_observed` apenas para medição local comparável fornecida".*

Cada entrada de `local_ids` passa a exigir `{id, source: "<caminho>#<âncora>" ou "<caminho>:<linha>", quote: "<trecho literal>"}`. A conferência deve: resolver a localização declarada (a âncora tem de existir como cabeçalho; a linha tem de existir); exigir que `quote` esteja **naquela localização** — no corpo da seção ancorada ou naquela linha exata — e não em qualquer ponto do arquivo; exigir que `quote` contenha o ID; e restringir a classe do caminho a `_tl-orc/project/evidence/` ou `_tl-orc/evidence/`, rejeitando `docs/` (cartão oficial não é medição local) e `.py` (código e exemplos negativos).

Controles novos, todos com motivo e `despacho: nenhum`: `sonnet-effort` declarado como local com `docs/MODEL_ROUTING.md#ancora-inexistente`; `local-fake` com `T009-mechanical-check.py:999999`; ID que só aparece como exemplo negativo no código; e o caso positivo `local-t005-checker-astra` com âncora real em `T005-r01.md` e trecho conferido.

### R2 — classe econômica por citação, nunca por inferência (high)
*Norma: `classifier.md:109-114` e `:116-121`.*

**Remova a regex de prosa.** A classe econômica de um ID nunca é inferida do texto do cartão. Cada entrada declarada como `official_task_proxy` traz `{id, source: "docs/MODEL_ROUTING.md:<linha>", quote}` e a conferência exige, cumulativamente: o ID está **registrado** (título `### \`id\`` ou linha de tabela `| \`id\` |`); a linha declarada cai **dentro do corpo daquele cartão**; o `quote` está literalmente naquela linha; o `quote` contém um termo do **vocabulário fechado de custo** (`custo`, `preço`, `tarifa`, `USD`, `US$`, `$`) **e** um termo de unidade por trabalho (`por tarefa`, `por tentativa`, `por story`). Grandezas de tempo ou score (`minutos`, `latência`, `%`) não qualificam. `token_price_only` só a partir de linha da tabela de preços (`price-*`), conferida como linha de tabela. **Tudo o mais rebaixa para `unknown`** — falha fechada, e `unknown` permanece legítimo com lista vazia.

**Ressalvas entregues ao julgamento, nunca ocultadas:** extraia do mesmo cartão as frases com marcador de negação (`Não `, `não é`, `não prova`, `não extrapolar`, `não reutilizar`, `não presumir`, `não comparar`) e anexe-as ao registro de julgamento. A camada mecânica não decide se a ressalva anula o uso; ela é obrigada a exibi-la.

Controles novos: `astra-domain` como proxy → **rejeitado** (só minutos e latência, `:55-56`); `sonnet-effort` como proxy → **rejeitado**; `official-2026-09-05` como `evidence_id` → **rejeitado** (marcador de revisão em `:3`, regressão do r01); `astra-coding` com o trecho "custo API estimado por tarefa" de `:47-48` → **aceito**; `flash-deepswe` com "eixo de custo por tarefa" de `:93` → **aceito**.

Dois controles de fronteira, que são o ponto da Task:

- **`gpt56-coding` como `official_task_proxy`** → deve **falhar** e cair para `unknown`: o cartão (`:60-72`) é de capacidade e sua menção de custo (`:68-69`) não afirma custo por tarefa. Registre na análise a consequência: a classificação da fase *implementation* desta própria Task (`T009-classification.md`) usou `gpt56-coding` para sustentar `official_task_proxy` e foi aceita pela conferência do Orquestrador **porque a lista de proxies foi composta à mão por ele** — é a mesma falha de origem das entradas, cometida pelo Orquestrador dentro da T009.
- **`opus-effort` como `official_task_proxy`** → passa a conferência mecânica (o cartão diz "custo por tentativa", `:82`) e vai ao julgamento **acompanhado da ressalva** de `:87-88`. Este controle demonstra o limite honesto da camada mecânica: ela aprova o que é decidível e entrega o resto, explicitamente, a quem julga.

### R3 — fallback sob `preferred` com indisponibilidade comprovada (high)
*Normas: `perfis:153-155`, `:175-176`, `:183-185`, `:191-192`.*

`availability` por candidato passa a ser `{state: available|unavailable|disabled|unknown, proof_class, proof_quote, source: "<caminho>:<linha>"}`, com prova exigida apenas para `unavailable`. Conferência: arquivo e linha existem; `proof_quote` está literalmente naquela linha; `proof_class` pertence ao conjunto fechado que a norma admite — `quota_exhausted`, `auth_refused`, `harness_absent` (`:175-176`) — e o trecho corresponde à classe declarada. **Não comprovam indisponibilidade**, por `:183-185`: timeout isolado, saída vazia, falha repetida de invocação, processo ainda vivo, e erro genérico de serviço como 503.

Seleção: pule candidatos nulos, `disabled` ou inelegíveis (`:154`), **inclusive o próprio fallback de mesma família**, cujo estado precisa ser `available`. Sob `preferred`, o fallback de mesma família só é liberado se **todos** os candidatos de família distinta à frente estiverem `unavailable` com prova conferida; qualquer `unknown` → bloqueio com ponto de retomada (`:191-192`).

Corrija o controle positivo: `synthetic_unavailable_evidence.md` hoje usa *endpoint timeout*, que a norma exclui. Reescreva com classes admitidas. Controles: prova ausente na linha declarada → bloqueado; indisponibilidade comprovada de todas as famílias distintas com fallback `available` → despacho `same_family_fresh_session`; o mesmo com fallback `disabled` → bloqueado; `proof_class: timeout` → não comprovado, bloqueado; `required` → mesma família inelegível, sem despacho.

### R4 — família desconhecida é estado não resolvido (high)
*Norma: `perfis:191-192` — "estado incerto não resolvido resulta em bloqueio com ponto de retomada"; `perfis:49` — a elegibilidade depende da família.*

`families.get(model)` retornando `None` produz `família: não resolvida`, **nunca** "distinta". O candidato não pode ser selecionado; se for o único, o despacho é bloqueado com ponto de retomada. O objeto permanece mecanicamente válido. Controle: remover `gpt-6-astra` de `families` sob `required` com `authors = [OpenAI, Google]` → nenhum despacho, motivo "família não resolvida", objeto APROVADO na camada mecânica.

### R5 — validade e resolução separadas nos dois sentidos (medium)
*Norma: `perfis:191-192`; e a própria AC03 da análise.*

"Nenhum candidato elegível sob `required`" sai de `problems` e passa a ser desfecho de **resolução**: mecânica `APROVADA`, julgamento conforme o caso, despacho `BLOQUEADO` com ponto de retomada — nunca `REJEITADA`. Atualize `case_15`, `pilot_summary.json` e AC03/AC04. Fixe a semântica das três colunas: `mecânica ∈ {APROVADA, REJEITADA}`; `julgamento ∈ {CONFIRMADO, PENDENTE, N/A}`; `despacho ∈ {LIBERADO:<par>, BLOQUEADO:<motivo + ponto de retomada>, NENHUM}`. `REJEITADA` passa a designar exclusivamente invalidade do objeto.

### Regressão obrigatória
Todas as sondas de r01 e r02 tornam-se casos permanentes do piloto: ID inventado com caminho existente; `sonnet-effort` como proxy; `official-2026-09-05` como ID; `reason` ausente no candidato; `facts: []`; propriedade extra; `preferred` sem prova; prova por substring em âncora inexistente; candidato `disabled` despachado; família removida sob `required`; `astra-domain` como proxy. A entrega não é aceita se qualquer uma voltar a passar.

### Atualizações na análise
AC01 e AC05 passam a registrar, como **resultado do piloto**: a reincidência das classes A e B ao longo de três rodadas; a causa verificada — as regras de conferência dos reworks 1 e 2 foram redigidas pelo Orquestrador em prosa, não derivadas da fonte normativa, e os defeitos R1/R2 do r02 saem literalmente dessas instruções; o caso `gpt56-coding` como demonstração do mesmo defeito na conferência do próprio Orquestrador; e a **fronteira de mecanização**: pertencimento ao catálogo, `story_id` inclusive `null`, fase, revisões, papéis, ordem da cadeia, pins, registro do ID e citação literal em localização declarada são mecanicamente decidíveis; a leitura de ressalva de cartão em prosa e a pertinência da evidência à tarefa não são, e pertencem ao julgamento registrado. Mantenha `rework_round: 3` e `date_utc` real de conclusão.

### Portões
`python3 _tl-orc/project/evidence/T009-mechanical-check.py --self-test` exit 0 **sem escrever nada** (confira por hash de `pilot_summary.json` antes e depois); `python3 scripts/validate_repository.py` verde; nenhum arquivo distribuído alterado; nenhum caminho privado; somente biblioteca padrão.

### Resposta final (sem escrever arquivo de relatório, sem commit)
Para cada item R1–R5: `arquivo:linhas` alterados, a **linha normativa da qual a regra deriva**, e o controle que a prova. Lista dos casos novos com resultado. Saída literal do `--self-test` e do validador, com exits. Declaração explícita de qualquer conflito encontrado entre este briefing e uma linha normativa citada. Confirmação de que nenhum outro trecho foi alterado.

---

### Delta do briefing do Checker r03 (mesmo pin `codex/gpt-6-astra/high`, sessão nova)

Acrescentar ao modelo vigente: as correções declaradas do rework 3 por item; a instrução de **não repetir** as sondas de r01/r02 — agora casos fixos do piloto, cuja permanência deve ser apenas conferida — e de construir **ao menos três sondas novas**, priorizando as classes A e B; a exigência de que cada `action_item` cite a linha normativa violada, e não apenas o comportamento observado; e a nota de que a T009 está sob regra de parada, de modo que achado de terceira reincidência das classes A ou B deve ser relatado como tal, porque encerra a unidade em vez de gerar nova rodada. Mantida a exigência de hipótese rejeitada por critério AC01–AC06 e a ressalva conhecida do `validate_repository.py` em sandbox somente leitura (`scripts/validate_repository.py:142`, ausência de temporário utilizável), que não deve ser tratada como regressão.

---

**Nada executado.** Aguardo autorização para registrar o r02, aplicar `rework_round: 3` e despachar, e — em paralelo — sua resposta à consulta de §2(i), que define a forma final do R2.
