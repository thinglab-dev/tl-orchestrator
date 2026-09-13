# Perfis e despacho

Complemento do [contrato do Orquestrador](orchestrator.md). O Classificador dimensiona o trabalho;
o Orquestrador valida a recomendação e executa a cadeia de despacho autorizada.

## Searcher sob demanda

O Searcher é auxiliar de consulta. Quando necessário, use sessão nova: o Searcher recebe modelo e
effort da classificação da fase (papel auxiliar searcher, que usa a mesma estrutura dos demais
papéis e cujo tier dimensiona a consulta) ou de pin explícito do usuário ou do consumidor, ainda assim
passado ao Classificador como restrição. A classificação da fase cobre as buscas daquela fase (não se reclassifica a cada busca). O Searcher não decide,
implementa, aprova ou despacha, e devolve apenas o resumo verificável previsto em
[seu contrato](searcher.md). Busca trivial direta continua sem agente.

## Perfil-padrão

O **Orquestrador** conserva o harness, modelo e effort selecionados pelo usuário na sessão.
Não participa do roteamento por tier e não se torna fallback automático dos outros papéis.

O **Classificador** usa uma sessão auxiliar curta, somente leitura, com esta cadeia fixa:

| Prioridade | Harness | Modelo | Effort |
| :--- | :--- | :--- | :--- |
| 1 | Agy/Antigravity | `gemini-3.8-flash-medium` | `medium`, incorporado ao ID |
| 2 | Codex | `gpt-5.6-luna` | `medium` |
| 3 | Claude | `sonnet` | `medium` |

Chame apenas o primeiro candidato utilizável; a lista é fallback, não um painel de três consultas.
Confirme o modelo concreto resolvido por aliases como `sonnet`. O Classificador não escolhe seu
próprio modelo ou effort e não herda os parâmetros do Orquestrador.

Para os papéis de trabalho, o Classificador escolhe **modelo e effort por papel e por harness**.
A ordem de preferência dos harnesses é operacional:

| Papel | Cadeia de preferência e fallback |
| :--- | :--- |
| Planner | Claude → Codex → Agy |
| Maker | Agy → Codex → Claude |
| Checker report-only | Codex → Claude → Agy, priorizando família diferente de toda a autoria efetiva |
| Searcher | Agy → Claude → Codex |
| Advisor | Cross-family preferido em relação à proposta desafiada (contra-família) |

Essas cadeias publicadas constituem a política global padrão do pacote quando os três harnesses (Agy, Claude e Codex) estão disponíveis:
- **Classifier**: Agy `gemini-3.8-flash-medium` (`medium`) → Codex `gpt-5.6-luna` (`medium`) → Claude `sonnet` (`medium`).
- **Planner**: Claude `sonnet` (`medium` ou `high`) → Codex `gpt-5.6-terra` (`medium` ou `high`) → Agy Gemini (`high`).
- **Maker**: Agy `gemini-3.8-flash-high` (`high`) → Codex `gpt-5.6-terra` (`high` ou `xhigh` conforme classificação) → Claude `sonnet` (`high`).
- **Checker report-only**: Codex `gpt-5.6-terra` (`high`) → Claude `sonnet` ou `claude-opus-5` (`high`) → Agy Gemini (`high`, quando elegível).
- **Searcher**: Agy `gemini-3.8-flash-medium` (`medium`) → Claude → Codex.
- **Advisor**: Cross-family preferido em sessão limpa (`fresh_session: required`), subordinado a `advisor_independence` (preferred vs required) e contra-família da proposta desafiada.

A cadeia nominal do Checker (`Codex → Claude → Agy`) permanece **estritamente subordinada a `checker_independence` e à autoria efetiva completa** (incluindo Maker inicial, reworks e correções do Orquestrador): se OpenAI participou da autoria, Codex é inelegível; se Google participou, Agy é inelegível; se Anthropic participou, Claude é inelegível; se Google e OpenAI participaram, Claude é o único elegível.

Essas escolhas são preferências operacionais e econômicas, não pins rígidos: o Classificador pode alterar modelo/effort diante de complexidade, disponibilidade comprovada ou pressão de quota. A hierarquia de autoridade preserva:
$$\text{instrução explícita do usuário} > \text{configuração local do projeto (_tl-orc/PROJECT.md)} > \text{perfil-padrão publicado}$$

Projetos consumidores herdam este perfil publicado por omissão. O arquivo local `_tl-orc/PROJECT.md` deve conter apenas fontes autoritativas, portões e exceções/overrides locais deliberados, sem duplicar desnecessariamente tabelas de participantes que reproduzam o padrão. Em projetos com os três harnesses disponíveis, o fluxo canônico esperado é:
- Com planejamento: `Gemini 3.8 Medium Classifier → Claude Planner → Gemini 3.8 High Maker → Codex Terra High Checker`.
- Sem planejamento: `Gemini 3.8 Medium Classifier → Gemini 3.8 High Maker → Codex Terra High Checker`.
Quando algum dos harnesses estiver ausente no ambiente, a cadeia é filtrada deterministicamente pelos harnesses disponíveis, conservando a independência estrita do Checker.

## Catálogo permitido

Antes de classificar, confira ferramentas, configuração vigente, ajuda local e documentação
oficial necessária. O catálogo entregue ao Classificador contém, para cada harness, os modelos
permitidos pela política vigente, família real, efforts suportados pelo harness e pela API,
capacidade adequada e limites de custo/quota. Separe autorização de uso, disponibilidade observada
e seleção efetiva. Uma lista da CLI comprova descoberta, não acesso garantido, preferência ou
permissão para gastar sem limite.

Use IDs aceitos pelo harness atual. Um modelo listado pelo Agy pode pertencer à Anthropic: o nome
do harness não identifica a família. Quando effort estiver incorporado ao ID, como nas variantes
Gemini do Agy, entregue cada par modelo/effort válido; não combine sufixo `medium` com effort
`high`. Registre aliases e sua resolução. Opções fora do catálogo, proibidas para o papel ou acima
do orçamento não são candidatas. Se não houver modelo adequado, informe a lacuna.

Use [MODEL_ROUTING.md](../docs/MODEL_ROUTING.md) como catálogo de evidências, não de autorização.
Selecione apenas cartões pertinentes e medições locais comparáveis, preserve seus IDs e ressalvas
e registre a revisão. Não envie artigos, gráficos ou histórico inteiros. Preços vencidos exigem
revalidação antes de alegar vantagem monetária, mas não anulam por si só sinais de capacidade.
Ausência de medição não é custo, latência ou falha zero. Benchmarks e consenso de classificadores
não garantem precisão estatística, economia local nem aceite da entrega. Modelo menor não é
automaticamente mais rápido por tarefa, e throughput não equivale a latência ponta a ponta.

O catálogo pode oferecer modelos econômicos e mais capazes para o mesmo harness. Disponibilidade
de Luna, por exemplo, não o torna fallback implícito de Terra: seu uso em um papel precisa estar
permitido no catálogo e selecionado pelo Classificador para aquela tarefa.

## Classificar e resolver

1. Prepare um briefing curto com `story_id` (`null` apenas sem story; no perfil Native, o ID da
   Task ou do Deliverable, como `T012` ou `D002`, qualificado como `billing:T012` quando houver
   áreas cadastradas, com `area_id` informado como contexto do briefing e nunca como campo do
   resultado), `phase`,
   `context_revision`, `catalog_revision` e revisão do contrato/schema; intenção e modo autorizado;
   trabalho residual, riscos, critérios, provas existentes e faltantes; políticas, orçamento,
   pins e cadeias; `requested_roles` somente da fase atual; catálogo de pares autorizados; e o
   recorte relevante de evidências oficiais e medições locais, sempre com IDs. Não envie pacote,
   artigos, histórico ou diff inteiros. Ausência de perfil local não impede usar o padrão publicado
   depois de conferir as capacidades necessárias.
2. Despache o [Classificador](classifier.md) com seu perfil fixo. Ele devolve tier, justificativa e
   pares modelo/effort para **cada harness de cada papel solicitado**, incluindo alternativas de
   fallback. Entregue contrato, schema compacto e briefing na própria chamada: a sessão não usa
   ferramentas nem explora o projeto. Uma escolha para Maker não dimensiona automaticamente
   Planner ou Checker.
3. Valide o objeto contra o [schema](../schemas/classification-result.schema.json) e confira a
   semântica: schema versão 2; correspondência exata de story, fase e revisões de contexto e
   catálogo; papéis exatos; um candidato por harness na ordem configurada; pares, efforts, pins,
   restrições e orçamento; `model: null` se e somente se `effort: null`; e cada `evidence_id`
   fornecido no briefing e pertinente ao modelo/tarefa. Confira também se `cost_basis` não promete
   mais que a evidência e, quando diferente de `unknown`, tem ao menos um ID econômico pertinente;
   fontes apenas de capacidade não satisfazem esse vínculo. Não complete IDs ausentes durante a
   validação. Confira ainda se razões são curtas e se `max`/`ultra` têm risco e ganho concretos,
   além de orçamento e, para `ultra`, autorização multiagente. Use validador existente; sem ele,
   declare a conferência manual e sua limitação. A confiança declarada não prova acerto.
4. Preserve a resposta canônica do harness. A única normalização adicional admitida é remover uma
   cerca JSON que envolva a resposta inteira, nos mesmos limites do
   [playbook](orchestrator-playbook.md#revisão-externa). Saída inválida permite no máximo uma correção
   de formato/contrato na mesma sessão; se continuar inválida, bloqueie. Não invente campos nem
   consulte outros modelos até obter uma classificação conveniente.
5. O Orquestrador não refaz a otimização no próprio modelo caro: monta e confere os fatos, rejeita
   inconsistências e escolhe o primeiro candidato validado que esteja disponível. Antes de cada
   despacho, revalide disponibilidade, modelo/effort efetivos, permissões e sessão. Não substitua
   o par por palpite nem transforme orçamento em autorização para ampliar escopo ou agentes.
6. Em implementação e rework, resolva o Checker depois de conhecer todos os autores efetivos do
   artefato. Em debate, resolva primeiro a identidade consultiva efetiva do Maker e depois escolha
   Checker de família diferente dela e de autores efetivos de artefato, se houver; ausência de diff
   não torna esse conjunto vazio. Se fallback mudar o Maker, revalide o Checker. Aplique a
   [preferência de independência](#independência-do-checker) e registre recomendação, candidato
   efetivo, motivo de cada salto e identidade da sessão.

Classifique antes do primeiro despacho autorizado de Planner, Maker ou Checker, em toda fase, conforme a
regra de escolha de modelo do [contrato do Orquestrador](orchestrator.md#perfil-padrão-de-despacho). Planejamento ou debate só dimensiona os papéis
necessários e não autoriza implementar. Toda mudança de fase reclassifica apenas os papéis então
necessários: debate pode ser pesado sem diff; Planner pode exigir mais capacidade que execução
delimitada; review considera alcance, riscos e contraprovas; rework considera achados e residual,
sem herdar tier anterior.

No debate, o briefing explicita o trabalho consultivo de cada papel: arquitetura e alternativas do
Planner; viabilidade, manutenção e provas do Maker; premissas, riscos e contraprovas do Checker.
Ausência de diff ou escrita não torna Maker ou Checker ociosos nem sustenta tier `simple`; o risco
específico de cada contribuição decide o tier, sem impor uniformidade.

Reutilize uma resposta somente com igualdade de story, fase, papéis, revisões de contexto,
catálogo e contrato, pins e política. Com áreas cadastradas, a igualdade de story compara a forma
canônica `<area_id>:<id>`; um `story_id` sem prefixo só é canonizado quando a área é inequívoca, e
uma classificação anterior é normalizada pelo seu próprio briefing de origem, registrado e
verificável, nunca pelo briefing atual. Sem essa procedência, reclassifique; dois formatos aceitos
nunca permitem reutilizar classificação entre áreas diferentes. Uma resposta versão 1 nunca vira versão 2 por preenchimento
inferido: reclassifique. Caches e registros anteriores são evidência aproveitável, não runtime de
reuso ou reclassificação automática. Quota, autenticação e timeout não reclassificam nem reduzem a
qualidade exigida: percorra os candidatos já classificados.

## Fallback e interrupção

O fallback é sequencial e limitado aos candidatos autorizados. Falhas de execução só o acionam
quando comprovadamente de infraestrutura; a seleção também pula candidatos nulos, desabilitados ou
inelegíveis conforme a política. Recusa de segurança não autoriza tentar outro modelo para
contornar a proteção, reduzir salvaguardas ou procurar uma resposta conveniente.

Candidato com `model: null` e `effort: null` não tem opção adequada no catálogo: registre a
lacuna e siga para o próximo candidato com par válido. Nunca despache valores nulos. Mudanças de
disponibilidade não alteram a revisão do catálogo de modelos autorizados nem invalidam, por si
só, os perfis já classificados. O catálogo prova apenas elegibilidade, nunca disponibilidade.

Distinga os estados:

| Estado observado | Ação |
| :--- | :--- |
| `available` | tentar o par modelo/effort validado |
| `unavailable` | registrar evidência e tentar o próximo candidato |
| `disabled` | respeitar a desativação e seguir a cadeia |
| `unknown` | conferir por meios disponíveis; se continuar ambíguo, bloquear |

A disponibilidade se comprova por evidência recente pertinente (run registrado no mesmo harness,
mesma conta e mesma sessão de trabalho) ou pela própria chamada autorizada ao papel. Uma sonda
separada só cabe para resolver dúvida concreta quando o estado permanecer `unknown` após a
chamada normal. Quotas explicitamente esgotadas, autenticação recusada ou harness ausente podem
comprovar indisponibilidade e acionar o fallback. Diante de ausência de saída ou suspeita de processo
sem avanço após o intervalo de liveness configurado (`liveness_probe_after`), realize investigação
mecânica proporcional do subprocesso (inspecionando estado do processo, CPU, streams e descritores/pipes
de I/O de forma agnóstica ao sistema operacional, garantindo que `stdin` recebeu EOF / `< /dev/null` e
não há bloqueio local) antes de qualquer inferência de latência de agente. Comandos e utilitários
específicos (como `ps`, `lsof`, APIs de plataforma ou cmdlets) são apenas adaptadores de sistema
operacional. Falhas mecânicas simples de invocação devem ser corrigidas localmente nos limites da
autorização vigente e registradas na contabilidade de esforço da amostra. Um timeout isolado, saída
vazia, falha repetida de invocação ou processo ainda vivo não comprovam indisponibilidade nem autorizam
troca de modelo ou família. Não confunda falta de quota com falha de raciocínio e não promova ou
rebaixe tier/effort para contorná-la. Toda chamada, inclusive a que falhou, tentativas descartadas e
sondas, entra na tabela `Agent runs`
([docs/WORK_MODEL.md#registro-de-revisão](../docs/WORK_MODEL.md#registro-de-revisão)). Se uma quota
compartilhada foi comprovadamente esgotada, marque somente os candidatos cobertos por essa mesma
quota; não presuma que outro harness usa a mesma conta. Não tente uma cadeia circular. Todos
indisponíveis, nenhuma opção adequada, restrição fixada incompatível ou estado incerto não
resolvido resultam em bloqueio com ponto de retomada.

Em interrupção durante implementação, preserve base, diff parcial, evidências e causa observada.
Confirme que o escritor anterior cessou antes de despachar substituto; confira novamente árvore,
spec e trabalho residual. Continue a partir do estado preservado, sem repetir operações externas
já realizadas. O substituto recebe o par previamente classificado para seu harness; mudanças
substantivas no trabalho residual exigem reclassificação. O Orquestrador permanece na sessão
selecionada pelo usuário; seu próprio esgotamento exige retomada pelo usuário ou pelo harness,
não uma promessa de continuidade automática do pacote.

Após N rodadas de rework (N padrão 3; o consumidor pode fixar outro valor em `PROJECT.md`) em que o
Checker aponte achados centrais da mesma classe, o Orquestrador classifica uma fase consultiva (fase
`debate`, papéis conforme o risco) e despacha um consultor com a pergunta "estamos corrigindo
manifestações do mesmo problema ou descobrindo requisitos que precisam ser consolidados antes de
continuar?". A orientação é consolidada (spec, abordagem ou critérios) antes de classificar outro
rework; correções delimitadas seguem o fluxo normal.

## Independência do Checker

Use sempre uma **nova sessão**, somente leitura, sem reutilizar a sessão de Maker, Classificador
ou debate. As famílias que escreveram a entrega são todas as famílias efetivas envolvidas na autoria
do artefato, incluindo Maker inicial, reworks, experimentos comparativos e correção feita pelo
próprio Orquestrador. Por padrão, `checker_independence: preferred`: tente primeiro candidatos de
família diferente de todas as famílias efetivas que escreveram a entrega, preservando a ordem
Codex → Claude → Agy dentro desse grupo. Se nenhum for utilizável e a indisponibilidade estiver
comprovada, tente os de mesma família, também na ordem configurada, em sessão nova; registre
`same_family_fresh_session` como limitação da revisão e abra uma pendência de revisão por outra
família no bloco `## RF-<unit_id>-rNN` na evidência da unidade
([docs/WORK_MODEL.md#registro-de-revisão](../docs/WORK_MODEL.md#registro-de-revisão)). Família
desconhecida exige conferência antes da escolha.

O consumidor pode exigir `checker_independence: required`; nesse caso, a ausência de família
distinta bloqueia a revisão com ponto de retomada, sem abrir bloco de pendência. A
indisponibilidade comprovada nunca converte `required` em `preferred`. Uma política local estrita
continua vigente até mudança autorizada. Não apresente revisão de mesma família como diversidade de
modelos nem revisão própria como Checker externo.

## Independência do Advisor

Use sempre uma **nova sessão limpa** (`fresh_session: required`), somente leitura (`report_only: true`),
sem reutilizar contextos anteriores.
A independência do Advisor é calculada em relação ao **conjunto completo de famílias autoras materiais**
que contribuíram para a proposta, plano ou artefato sob desafio (`challenged_author_families`), e não
meramente em relação a uma única família ou ao último autor:
```text
challenged_author_families = conjunto completo das famílias que contribuíram materialmente para o artefato desafiado
eligible_cross_family = famílias disponíveis - challenged_author_families
```

Resolução obrigatória:
- **Casos com 1 família autora:**
  * `[google]` → OpenAI (Codex) ou Anthropic (Claude);
  * `[openai]` → Google (Agy) ou Anthropic (Claude);
  * `[anthropic]` → Google (Agy) ou OpenAI (Codex).
- **Casos com pares de famílias autoras materiais:**
  * `[google, openai]` → obrigatoriamente Anthropic (Claude) quando disponível; não pode depender do último autor;
  * `[google, anthropic]` → obrigatoriamente OpenAI (Codex);
  * `[openai, anthropic]` → obrigatoriamente Google (Agy).
- **Caso extremo com as 3 famílias (`[google, openai, anthropic]`):**
  * Sob `advisor_independence: required`: nenhuma família independente disponível (`eligible_cross_family = ∅`), bloqueia terminantemente o despacho do Advisor (`blocked`) com emissão de impedimento formal e ponto de retomada.
  * Sob `advisor_independence: preferred`: admite fallback na mesma família em sessão nova, obrigatoriamente registrado como `advisor_independence: degraded_same_family`, com `fallback_reason` obrigatório não vazio detalhando todas as famílias conflitantes.

Por padrão, vigora `advisor_independence: preferred`:
- O Orquestrador busca primeiro candidatos em `eligible_cross_family` recomendados na classificação.
- Se todas as opções de famílias alternativas estiverem comprovadamente indisponíveis (falta de quota,
  autenticação recusada ou harness ausente), admite-se o despacho do Advisor em sessão nova,
  como fallback degradado com registro mandatório na evidência (`advisor_independence: degraded_same_family`,
  `fallback_reason: <motivo>`).

Sob `advisor_independence: required`:
- A indisponibilidade de famílias alternativas em `eligible_cross_family` bloqueia terminantemente o despacho
  do Advisor com emissão de impedimento formal e ponto de retomada. Indisponibilidade comprovada nunca converte
  `required` em `preferred`.

## Briefing concreto

Forneça o caminho real do contrato dentro da **raiz do pacote** e a **raiz consumidora**
separadamente. Confira acesso aos dois. Para Planner, Maker e Checker, inclua:

- papel, resultado, modo autorizado e critério de parada;
- classificação versão 2, story, fase, revisões de contexto/catálogo/contrato, tier, harness,
  modelo, effort, família, evidências e base de custo;
- story/spec, decisões reservadas e estado base;
- árvore, caminhos de escrita permitidos, evidências e arquivos protegidos;
- portões, diretório de execução, recursos compartilhados e operações proibidas;
- para Checker, base, diff inteiro, critérios congelados, schema e grau de independência;
- no perfil Native, `spec_revision`, `content_id` e `content_paths` da Task, o perfil de
  verificação da spec e o conjunto inicial de contexto selecionado pelo
  [modelo de trabalho](../docs/WORK_MODEL.md#carregamento-e-envelhecimento): `CONTEXT.md`, índice,
  briefs das features afetadas e dependências diretas, unidade ativa e decisões referenciadas. O
  tipo da Task não entra no briefing do Classificador como sinal de tier.

Cada informação do briefing declara a fonte do seu tipo e o conteúdo dessa fonte sustenta o valor
declarado, conforme a tabela normativa de procedência:

| Tipo de informação | Fonte autorizada | Conteúdo que sustenta o valor e conferência |
| :--- | :--- | :--- |
| `story_id`, fase e papéis solicitados | solicitação ou spec da Task/fase | o registro citado contém o valor literal |
| catálogo (harness/modelo/effort), pins e cadeias | fontes de política conforme a [precedência vigente](#perfil-padrão) (instrução atual do usuário registrada; configuração do consumidor em `PROJECT.md`; ou o perfil publicado quando não há configuração local) | o registro citado cita exatamente o par, o pin ou a cadeia |
| autoria efetiva e famílias | registro de `Agent runs` efetivo | a linha citada declara harness, modelo e família usados |
| evidências de custo e capacidade | [docs/MODEL_ROUTING.md](../docs/MODEL_ROUTING.md) | pertinência ao modelo e, para proxy de custo, afirmação de custo por tarefa no cartão |
| medição local | linha de tabela estruturada em evidência do projeto | ID na primeira coluna |
| julgamento | registro documental vinculado por hash ao objeto e às entradas | hash coincide e veredito explícito |

Localização que resolve (arquivo existe, âncora resolve, linha existe) não basta; fonte existente
mas incompatível com o tipo ou com o valor é rejeitada. Listas compostas na hora sem procedência por
entrada ou fontes genéricas como "um arquivo existente" não valem como origem e são rejeitadas; o
Classificador só recebe IDs com origem. Um catálogo montado para a chamada é legítimo quando cada
entrada deriva de uma dessas fontes com procedência verificável; rejeita-se a entrada sem
procedência, não o catálogo montado; isso preserva projetos sem perfil persistido. A autorização de
fontes além das raízes informadas segue o [escopo de leitura](orchestrator.md#invariantes).

Em **Debater**, use o dossiê comum e os limites do
[playbook consultivo](orchestrator-playbook.md#debater); não forneça schema de aprovação.
Agentes subordinados atuam instruindo e analisando alternativas, prós e contras; nunca possuem
autoridade para conceder autorizações de escopo, orçamento ou ações restritas em nome do usuário.
Configure permissões com capacidades verificadas. Instrução report-only não equivale a trava
técnica. Traduza effort para flags somente depois de conferir o transporte local; passe modelo e
effort explicitamente para evitar herdar um default caro, e registre qualquer divergência.

## Acompanhar e retomar

Use o mecanismo de acompanhamento fornecido pela ferramenta. Preserve identificador, resposta
original, resultado e exit observado; processo vivo, log crescente e exit zero isolado não provam
conclusão. O Orquestrador exerce a autonomia técnica já delegada pelo escopo da unidade e da spec,
executando diretamente escolhas técnicas rotineiras sem paradas desnecessárias. Quando formular
perguntas ao usuário, o cômputo do prazo humano inicia-se estritamente no evento tecnicamente
observável `question_emitted_at` (retorno bem-sucedido de emissão pelo runtime; `transport_ack_at`
é admitido se fornecido pelo canal); é terminantemente proibido presumir leitura ou cognição humana.
A consulta classificada pós-prazo só é despachada sob cláusula explícita no lote (`auto_consult_after`,
`max_calls`). Respeite limites de tempo e custo do briefing. Não prometa ser acordado depois de
encerrar a sessão.
