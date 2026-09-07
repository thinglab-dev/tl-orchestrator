# Perfis e despacho

Complemento do [contrato do Orquestrador](orchestrator.md). O Classificador dimensiona o trabalho;
o Orquestrador valida a recomendação e executa a cadeia de despacho autorizada.

## Searcher sob demanda

O Searcher é auxiliar de consulta, não papel classificado por tier e não integrante do schema de
papéis classificados. Quando necessário, use sessão nova com Agy/Antigravity
`gemini-3.8-flash-medium` / `medium`; política local ou pedido explícito do usuário pode substituir
esse perfil após validação e registro. Não chame o Classificador para cada busca. O Searcher não
decide, implementa, aprova ou despacha, e devolve apenas o resumo verificável previsto em
[seu contrato](searcher.md). Busca trivial direta não exige agente.

## Perfil-padrão

O **Orquestrador** conserva o harness, modelo e effort selecionados pelo usuário na sessão.
Não participa do roteamento por tier e não se torna fallback automático dos outros papéis.

O **Classificador** usa uma sessão auxiliar curta, somente leitura, com esta cadeia fixa:

| Prioridade | Harness | Modelo | Effort |
| :--- | :--- | :--- | :--- |
| 1 | Codex | `gpt-5.6-luna` | `medium` |
| 2 | Claude | `sonnet` | `medium` |
| 3 | Agy/Antigravity | `gemini-3.8-flash-medium` | `medium`, incorporado ao ID |

Chame apenas o primeiro candidato utilizável; a lista é fallback, não um painel de três consultas.
Confirme o modelo concreto resolvido por aliases como `sonnet`. O Classificador não escolhe seu
próprio modelo ou effort e não herda os parâmetros do Orquestrador.

Para os papéis de trabalho, o Classificador escolhe **modelo e effort por papel e por harness**.
A ordem de preferência dos harnesses é operacional:

| Papel | Cadeia de preferência e fallback |
| :--- | :--- |
| Planner | Claude → Codex → Agy |
| Maker | Codex → Claude → Agy |
| Checker report-only | Agy → Claude → Codex, priorizando família diferente da identidade Maker aplicável |

Essas cadeias publicadas autorizam fallback dentro dos seus limites. Uma instrução atual do
usuário prevalece sobre a configuração do consumidor, que prevalece sobre o perfil publicado.
Escolhas fixadas explicitamente para um papel continuam restrições do Classificador; não as
transforme em mera capacidade observada. O padrão por tier não fixa Terra, Sonnet ou Gemini como
modelo de trabalho de todos os tiers. Diversidade adicional do Planner é desejável, mas não basta
sozinha para reordenar sua cadeia nem revogar uma preferência.

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
chamada normal. Quota explicitamente esgotada, autenticação recusada ou harness ausente podem
comprovar indisponibilidade e acionar o fallback. Um timeout isolado, saída vazia ou processo ainda
vivo não comprovam isso nem erro de capacidade do modelo. Não confunda falta de quota com falha de
raciocínio e não promova ou rebaixe tier/effort para contorná-la. Toda chamada, inclusive a que
falhou, tentativas descartadas e sondas, entra na tabela `Agent runs`
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

## Independência do Checker

Use sempre uma **nova sessão**, somente leitura, sem reutilizar a sessão de Maker, Classificador
ou debate. As famílias que escreveram a entrega são todas as famílias efetivas envolvidas na autoria
do artefato, incluindo Maker inicial, reworks, experimentos comparativos e correção feita pelo
próprio Orquestrador. Por padrão, `checker_independence: preferred`: tente primeiro candidatos de
família diferente de todas as famílias efetivas que escreveram a entrega, preservando a ordem
Agy → Claude → Codex dentro desse grupo. Se nenhum for utilizável e a indisponibilidade estiver
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

Em **Debater**, use o dossiê comum e os limites do
[playbook consultivo](orchestrator-playbook.md#debater); não forneça schema de aprovação.
Configure permissões com capacidades verificadas. Instrução report-only não equivale a trava
técnica. Traduza effort para flags somente depois de conferir o transporte local; passe modelo e
effort explicitamente para evitar herdar um default caro, e registre qualquer divergência.

## Acompanhar e retomar

Use o mecanismo de acompanhamento fornecido pela ferramenta. Preserve identificador, resposta
original, resultado e exit observado; processo vivo, log crescente e exit zero isolado não provam
conclusão. Respeite limites de tempo e custo do briefing. Não prometa ser acordado depois de
encerrar a sessão.
