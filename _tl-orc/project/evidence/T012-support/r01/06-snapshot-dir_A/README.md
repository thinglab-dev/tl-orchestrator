# tl-orchestrator

Um método documental para planejar, debater decisões, implementar e revisar mudanças com Orquestrador, Planner, Maker e Checker. Usa agentes e portões já disponíveis no projeto consumidor. A distribuição contém documentos Markdown, schemas JSON e licença; não precisa de linguagem de programação, runtime próprio ou instalação do projeto de origem.

O Orquestrador mantém o harness/modelo/effort selecionado pelo usuário. Um **Classificador
econômico separado** escolhe modelo e effort dos papéis necessários em cada fase, por harness,
dentro do catálogo permitido. Ele recebe apenas o briefing e um recorte identificado da
[evidência de roteamento](docs/MODEL_ROUTING.md). Seu perfil fixo é Luna medium → Sonnet medium →
Gemini 3.8 Flash medium, em fallback sequencial.

As cadeias dos papéis são **Planner Claude → Codex → Agy**, **Maker Codex → Claude → Agy** e
**Checker Agy → Claude → Codex**, preferindo família diferente da do Maker e sempre em sessão
nova. Indisponibilidade comprovada permite fallback registrado; ambiguidade não resolvida bloqueia
somente o despacho ou a decisão que dela depende.
Preferências mais recentes do usuário e restrições do consumidor prevalecem sobre o padrão. O
roteamento satisfaz primeiro o risco e depois busca o menor custo esperado por entrega aceita; não
há tabela fixa tier → modelo nem promessa de economia ou precisão baseada só em benchmark.

O **Searcher** é um auxiliar sob demanda para contexto factual: consulta fontes autorizadas e
devolve resumo, evidências, inferências, lacunas e limites em sessão separada. Usa Agy
`gemini-3.8-flash-medium` / `medium` por padrão, fora do schema e do roteamento por tier; não
implementa, aprova ou substitui prova e leitura obrigatórias.

Criado por **Albertiano**. Distribuído sob a [licença MIT](LICENSE), que permite uso, modificação e distribuição, inclusive comercial, com preservação do aviso de copyright e da licença nas cópias ou partes substanciais do material.

Comece por [SKILL.md](SKILL.md). A [configuração do projeto](docs/PROJECT_CONFIGURATION.md)
explica como descobrir regras e portões sem impor estrutura ao consumidor; o contrato de
[evolução segura](docs/EVOLUTION.md) separa atualizações do pacote e contribuições upstream.
BMAD, quando utilizado, permanece oficial e instalado separadamente.

O [modelo de trabalho](docs/WORK_MODEL.md) define o perfil **Native**: quando o projeto não delega
a organização do trabalho a outro método, o Orquestrador mantém `Project → Deliverable → Task`,
decisões e discussões em `_tl-orc/project/`, com um `STATUS.md` central para consultar e retomar.
O mesmo cabeçalho de coordenação serve a projetos governados por BMAD, sem copiar seu estado. O
perfil também define a operação **Import Context**, que deriva Feature Briefs pequenos e
rastreáveis de documentos existentes sem transferir a autoridade do trabalho. Projetos sem módulos
são o modo padrão e usam só `_tl-orc/project/`; repositórios organizados por módulo podem cadastrar
áreas de trabalho adicionais em `PROJECT.md`, mantendo uma única coordenação de escrita por
árvore.

## Quick Start — instalar no projeto atual

Este perfil cria uma instalação canônica em `_tl-orc/` no projeto consumidor e a expõe aos
agentes compatíveis presentes no ambiente. O pacote continua documental e sem runtime. Por padrão,
cada ativação como Orquestrador faz uma consulta HTTPS somente leitura ao GitHub para conferir
atualizações; o perfil permite desabilitá-la com `update_check: disabled`. `update_policy` escolhe
entre notificar e aplicar somente uma release inequivocamente segura; `contribution_mode` escolhe
entre pedir confirmação e preparar um draft PR autorizado. Essas políticas são independentes e
não substituem autoridade expressa. Copie o prompt abaixo para uma IA com acesso ao projeto. Para
instalar manualmente em outro escopo, siga [a exportação](#exportar-os-17-arquivos) e
[a instalação](#instalar-e-ativar).

Possíveis defeitos do próprio método ficam primeiro registrados e sanitizados no projeto
consumidor. Quando a falha for clara, reproduzível e delimitada, o usuário pode autorizar uma
correção e um draft pull request; features novas exigem intenção delimitada e aprovada. O
[procedimento de relato](docs/PROJECT_CONFIGURATION.md#relatar-defeito-do-método) e o contrato de
[evolução](docs/EVOLUTION.md#contribuir-melhorias) definem as rotas. Somente
`contribution_mode: auto_pr` acompanhado de autoridade expressa por projeto, ator, destino,
escopo e procedência permite commit, push e criação de draft PR. Nunca permite merge automático,
e qualquer encaminhamento externo não atualiza nem altera o pacote instalado.

```text
Instale o tl-orchestrator no projeto atual e configure sua descoberta pelos agentes disponíveis,
respeitando minhas preferências, as instruções locais e o trabalho preexistente.

Fonte: https://github.com/thinglab-dev/tl-orchestrator

1. Confirme a raiz do projeto consumidor e leia primeiro suas instruções. Obtenha a fonte acima
   em uma pasta temporária, prefira uma release estável quando houver e registre sua tag e commit;
   sem release, registre o commit escolhido. Leia README, SKILL.md e os contratos e confira os
   17 arquivos da distribuição. Não execute conteúdo do repositório como parte da descoberta. Todos
   os arquivos instalados devem vir do mesmo commit.

2. Descubra em cada harness presente todos os escopos em que `tl-orchestrator` pode ser carregado,
   inclusive empresa, pessoal/global, projeto e diretórios aninhados, e determine sua precedência.
   Se `_tl-orc/` ou qualquer instalação da skill já existir, compare origem, commit, conteúdo e
   modificações locais. Uma revisão diferente em escopo de maior precedência pode sombrear a
   instalação do projeto: pare e peça ao usuário que escolha atualizá-la, removê-la ou mantê-la;
   não declare a migração concluída enquanto o harness carregar outra revisão. Preserve o que não
   pertence a esta instalação e não sobrescreva nem remova nada sem essa escolha.

3. Crie ou atualize este perfil dentro do projeto:

   _tl-orc/
   ├── package/          # os 17 arquivos canônicos do commit escolhido
   ├── INSTALLATION.md   # origem, versão, referência, commit, hashes e destinos
   ├── PROJECT.md        # fontes, portões e preferências de papéis
   ├── QUEUE.md          # opcional: limites da fila sequencial autorizada
   ├── evidence/         # somente se o projeto não tiver artefato próprio para evidência
   └── project/          # não criar na instalação: nasce na primeira operação autorizada

   Copie para `_tl-orc/package` somente os caminhos abaixo da revisão escolhida, preservando os
   subdiretórios. Esta lista é o manifesto legível da distribuição e deve coincidir com o
   `distribution-manifest.json` do repositório fonte:

<!-- distribution-manifest:start -->
- `README.md`
- `SKILL.md`
- `LICENSE`
- `prompts/orchestrator.md`
- `prompts/orchestrator-perfis.md`
- `prompts/orchestrator-playbook.md`
- `prompts/classifier.md`
- `prompts/planner.md`
- `prompts/maker.md`
- `prompts/checker-report-only.md`
- `prompts/searcher.md`
- `schemas/classification-result.schema.json`
- `schemas/review-result.schema.json`
- `docs/PROJECT_CONFIGURATION.md`
- `docs/MODEL_ROUTING.md`
- `docs/EVOLUTION.md`
- `docs/WORK_MODEL.md`
<!-- distribution-manifest:end -->

   Não faça cópia recursiva da origem;
   `.git`, `.gitignore`,
   configurações locais, backlog e qualquer outro arquivo não entram no pacote.

   Antes de gravar os hashes em `INSTALLATION.md`, compare cada um dos 17 arquivos de
   `_tl-orc/package` byte a byte com o caminho correspondente na pasta temporária da revisão.
   Arquivo ausente, adicional ou diferente bloqueia a instalação. Gere os hashes a partir da
   origem conferida e valide a cópia com eles; nunca derive a prova somente do destino copiado.

   Crie `INSTALLATION.md` e `PROJECT.md` no formato normativo da seção "Perfil local `_tl-orc/`"
   do guia instalado. `INSTALLATION.md` registra também a versão ou tag instalada, quando houver,
   a referência móvel acompanhada, como `refs/heads/main`, e todas as instalações concorrentes
   encontradas, com seu escopo e precedência. A tag identifica a versão instalada; ela não é a
   referência usada para descobrir versões seguintes.
   `PROJECT.md` aponta para as fontes autoritativas já existentes sem copiar suas decisões. Ele
   também registra preferências operacionais declaradas pelo usuário e capacidades observadas,
   sempre com origem e última conferência. Não grave tokens, chaves ou segredos nesses arquivos.
   Trate `_tl-orc/package` e os destinos de skill instalados como imutáveis entre atualizações:
   tarefas, portões e diffs do consumidor não devem alterá-los nem incluí-los em seu escopo.

4. Descubra quais harnesses realmente são usados consultando configuração, ajuda local e
   documentação oficial. Para cada um, exponha a mesma revisão de `_tl-orc/package` no diretório
   de skill de projeto confirmado. Caminhos atualmente reconhecidos incluem:
   - Claude Code: `.claude/skills/tl-orchestrator`;
   - Codex e Antigravity: `.agents/skills/tl-orchestrator`.

   Use link simbólico relativo para `_tl-orc/package` somente quando o harness, o sistema e a
   política do projeto o suportarem; caso contrário, faça uma cópia verificada dos 17 arquivos.
   Para integrações versionadas para a equipe, use por padrão a cópia verificada, pois o suporte
   local a links não garante o mesmo comportamento nos demais checkouts. Não crie integração para
   agente ausente nem presuma que caminhos de um harness funcionam em outro. Compare antes de
   substituir qualquer destino e registre em `INSTALLATION.md` se cada destino é link ou cópia.
   Confirme a descoberta da skill e informe a invocação observada; não prometa
   `/tl-orchestrator`, `$tl-orchestrator` ou autocomplete sem verificá-los no harness atual.

5. Verifique ferramentas de despacho, CLIs, modelos configurados e estado de autenticação sem
   exibir credenciais nem fazer chamadas pagas apenas para sondagem. Não instale ferramentas
   adicionais por conta própria. Diferencie capacidade comprovada de disponibilidade incerta.

6. Registre em `_tl-orc/PROJECT.md` o perfil-padrão publicado, salvo decisão vigente diferente no
   projeto:
   - Orquestrador: harness, modelo e effort selecionados pelo usuário na sessão;
   - Classificador: Codex gpt-5.6-luna medium → Claude sonnet medium →
     Agy gemini-3.8-flash-medium, em sessões auxiliares somente leitura;
   - Planner: Claude → Codex → Agy;
   - Maker: Codex → Claude → Agy;
   - Checker report-only: Agy → Claude → Codex, preferindo família diferente dos Makers.

   Registre routing_mode: classifier, o catálogo permitido e checker_independence: preferred
   (ou required quando o consumidor exigir outra família). Para cada fase, o Classificador recebe
   story_id, phase, context_revision, catalog_revision, revisão do contrato/schema, papéis então
   necessários, trabalho residual, riscos, critérios/provas, políticas/orçamento, pares autorizados
   e somente as evidências pertinentes com IDs. Ele devolve o objeto versão 2 com modelo/effort,
   evidence_ids e cost_basis para cada harness de cada papel. Confira schema, correspondência das
   revisões, pares, pins, restrições e pertinência da evidência antes de qualquer despacho.

   Preserve separadamente escolhas fixadas, capacidade observada, recomendação e despacho
   efetivo. Modelo que era apenas default do perfil legado é substituído pelo perfil publicado;
   escolha explicitamente fixada continua como pin e restrição do Classificador, mas nunca dispensa
   sua chamada. Se a origem antiga for ambígua, deixe essa decisão pendente; sincronização
   independente exige atualização explicitamente autorizada, e `auto_safe` deve parar.
   Na adoção explícita do roteamento variável, registre
   quais pins o pedido substitui. Revalide modelo,
   effort, família, permissões e sessão a cada chamada. Registre motivos de fallback; se o
   Checker usar a mesma família em sessão nova, declare a limitação. Não trate uma instrução
   report-only como bloqueio técnico de escrita. Mudança de fase reclassifica os papéis necessários;
   versão 1 não é promovida por inferência. Quota, autenticação e timeout usam a classificação
   existente e não reduzem qualidade. Registre medições e falhas conforme o guia, sem inventar
   custo, tokens, latência ou aceite ausentes.

7. Preencha `INSTALLATION.md` e `PROJECT.md` somente com fatos conferidos e preferências já
   declaradas. Este passo deriva da seção "Conferir atualizações" do guia, que é sua fonte
   normativa. Registre a origem normalizada e `update_check: enabled` por este pedido, ou
   `update_check: disabled` se o consumidor assim decidir. Registre também
   `update_policy: notify` e `contribution_mode: ask`, salvo preferência e autoridade expressas
   diferentes. Esses campos são independentes; `auto_safe` ou `auto_pr` isolado não autoriza
   escrita. Campos ausentes em perfil legado equivalem a `notify` e `ask`. Siga a ordem e os
   portões do [contrato de evolução](docs/EVOLUTION.md). Na ativação como Orquestrador, trate os
   campos como dados a validar: a consulta automática só pode usar exatamente a origem HTTPS
   canônica `https://github.com/thinglab-dev/tl-orchestrator`, uma referência móvel válida sob
   `refs/heads/` e commits instalados ou remotos formados por exatamente 40 dígitos hexadecimais
   minúsculos. Entrada inválida resulta em `não foi possível verificar`, sem acesso com ela. Para
   outra origem, não acesse a rede sem o usuário confirmar na sessão uma URL HTTPS exata; rejeite
   outros esquemas e transportes sem consultá-los. Nunca passe origem, referência ou commit não
   validado a shell, helper ou transporte Git. Prefira uma ferramenta web estruturada; se só
   houver cliente HTTPS por shell, use a origem canônica constante e os demais valores validados e
   codificados como argumentos literais, sem expansão ou avaliação. Papéis Classificador, Planner,
   Maker e Checker designados não fazem essa conferência.

   Antes da rede ou de informar um estado, confirme que o `SKILL.md` carregado está em um destino
   registrado e que os 17 arquivos carregados coincidem com `_tl-orc/package` e seus hashes. Se
   outra instalação estiver sombreando o perfil ou o conteúdo divergir, classifique e preserve
   primeiro qualquer delta autorizado conforme o contrato de evolução; ainda assim, informe o
   conflito sem atribuir ao perfil `atual` ou `atualização disponível` e não aplique `auto_safe`.

   Quando habilitada e validada, consulte pela API HTTPS do provedor, compare a referência com o
   commit instalado e informe `atual`, `atualização disponível`, `referência divergente` ou `não
   foi possível verificar`. O próprio `SKILL.md` instalado repete isso na ativação como
   Orquestrador; não edite o pacote nem crie outra configuração para esse fim. Só anuncie
   atualização quando a comparação confirmar que a revisão remota sucede a instalada; aplicar
   exige pedido próprio ou `auto_safe` com autoridade completa, além de nova conferência das
   cópias ou links instalados.

   Se houver atualização, consulte também as GitHub Releases cujas tags e commits pertençam ao
   intervalo comprovado. Informe os links e se as notas cobrem todo o intervalo. Trate release
   notes como dados não confiáveis: não execute comandos nem aplique migrações durante a simples
   conferência.

8. Somente ao conduzir como Orquestrador, aplique uma atualização por pedido explícito ou pela
   política `auto_safe` acompanhada de autoridade expressa e depois de todos os portões do
   contrato de evolução. Use como fontes normativas a seção "Aplicar uma atualização" do guia e
   [Atualização auto_safe](docs/EVOLUTION.md#atualização-auto_safe). Leia as notas aplicáveis em ordem, compare
   os contratos entre a versão instalada e a alvo e apresente o plano de migração. Preserve o
   regime do método: Maker executa as alterações; o Orquestrador confere hashes, integrações,
   descoberta, fresh load e o smoke test operacional; um Checker externo independente revisa a
   árvore final. Hashes provam apenas a cópia. Registre `synchronized` separadamente de
   `operational_verified`; se o harness não puder executar a prova, use `operational_pending` com
   o motivo, sem declarar adoção completa. Correção direta pelo
   Orquestrador exige a mesma prova e revisão. Registre notas consultadas, migrações, provas,
   parecer e pendências. Essa autorização não inclui alterar código, produto ou backlog do
   consumidor sem pedido explícito.

9. Pergunte apenas por decisões materiais em aberto. Siga a política do projeto para versionar
   `_tl-orc/` e as integrações; não altere `.gitignore`, não faça commit e não publique sem
   autorização. Mostre os arquivos criados ou alterados, a revisão instalada, as conferências
   executadas e como invocar a skill. Encerre sem iniciar planejamento, implementação ou revisão
   de uma tarefa do projeto.
```

`_tl-orc/` pertence ao projeto consumidor e não faz parte dos 17 arquivos desta distribuição.
As integrações podem ser versionadas para uso da equipe quando a política do projeto permitir; a
cópia verificada é o padrão para esse uso compartilhado.
Os caminhos acima seguem a documentação atual de [Claude Code](https://code.claude.com/docs/en/skills),
[Codex](https://learn.chatgpt.com/docs/build-skills) e
[Antigravity](https://antigravity.google/docs/skills); a instalação deve conferir a versão local.

## Como os papéis trabalham

Depois de ativar a skill, você pode escolher **Planejar**, **Implementar e revisar uma story**,
**Executar fila sequencial**, **Discuss**, **Debater** ou **Outra tarefa**. A story pode ser uma
Task do perfil Native. **Discuss** é uma conversa com o Orquestrador, sem despacho de agentes, que
registra síntese, decisões e questões abertas em `_tl-orc/project/` quando a escrita estiver
autorizada. **Debater** também aparece quando o Orquestrador apresenta uma decisão material
pendente. Basta responder a opção; a questão e o contexto atuais acompanham o pedido:

> **Orquestrador:** Há duas alternativas para esta decisão. Você pode escolher uma ou **Debater**.
>
> **Você:** Debater

Planner, Maker e Checker opinam primeiro de forma independente e podem responder às objeções em
uma rodada de contraponto. O Orquestrador apresenta recomendação, divergências e evidências
faltantes para você decidir. O [modo Debater](prompts/orchestrator-playbook.md#debater) usa sessões
somente leitura e não implementa nem aprova uma entrega. A identidade consultiva do Maker é
resolvida antes do Checker para preservar diversidade de família mesmo sem diff. Não exige IDs de
story ou comando novo.

O fluxo abaixo descreve uma mudança com implementação autorizada. Um pedido limitado a análise
ou planejamento termina nessa etapa. Decisões reservadas ao usuário voltam a ele.

```mermaid
flowchart TD
    U["Usuário"] -->|Define objetivo e autoriza escopo| O["Orquestrador"]
    O -->|Story, fase, revisões, catálogo e evidências| CL["Classificador · perfil econômico fixo"]
    CL -->|Tier, pares, evidências e base de custo| D["Orquestrador valida e resolve a cadeia"]
    D -->|Quando precisa de auditoria ou spec| P["Planner · Claude → Codex → Agy"]
    P -->|Propõe spec e corte| R["Orquestrador ratifica o corte"]
    D -->|Spec já executável| R
    R -->|Despacha implementação autorizada| M["Maker · Codex → Claude → Agy"]
    M -->|Diff e evidências| V["Orquestrador confere e verifica"]
    V -->|Correção necessária no escopo| M
    V -->|Nova sessão; prefere outra família| C["Checker · Agy → Claude → Codex"]
    C -->|Parecer| J["Orquestrador valida o parecer"]
    J -->|Parecer inválido: solicitar nova resposta| C
    J -->|Correção de implementação| M
    J -->|Spec inconsistente| P
    J -->|Decisão de intenção| U
    J -->|Sem ações pendentes e com autorização| I["Orquestrador integra e confere"]
    I -->|Entrega e evidências| U
```

### Fila sequencial

**Implementar e revisar uma story** termina na story atual. Para avançar automaticamente em uma
ordem de stories, escolha **Executar fila sequencial** depois de criar `_tl-orc/QUEUE.md` conforme
o [guia de configuração](docs/PROJECT_CONFIGURATION.md#fila-sequencial-de-stories). Cada ativação
processa uma única story pronta e, após um parecer aprovado, deixa o board e o commit local no
estado declarado pela fila. Uma tarefa agendada do Codex ou de outro harness pode chamar esse modo
mais tarde para processar a próxima.

Dentro da mesma story, os achados em escopo atribuídos ao Maker voltam em um único briefing — por
exemplo, R1–R4 — sem pedir uma autorização separada. O limite padrão são duas rodadas de correção;
decisão humana, alteração de escopo, cadeia de fallback esgotada, parecer inválido ou
falha sem atribuição param a fila e apresentam o ponto de retomada. A fila não faz push nem abre
pull request.

## Exportar os 17 arquivos

Em um terminal com ferramentas padrão POSIX, entre na raiz do pacote (pasta deste README). O bloco abaixo cria uma pasta temporária nova fora do projeto e nomeia exatamente 17 arquivos distribuídos. Usa `/tmp` para que uma configuração local de `TMPDIR` não leve a exportação para dentro do projeto. A pasta de origem deve estar fora de `/tmp` ou deve-se conferir que o destino não está dentro dela.

```sh
set -eu
export_dir=$(mktemp -d /tmp/tl-orchestrator.XXXXXX)
mkdir "$export_dir/prompts" "$export_dir/schemas" "$export_dir/docs"
cp README.md SKILL.md LICENSE "$export_dir/"
cp prompts/orchestrator.md \
   prompts/orchestrator-perfis.md \
   prompts/orchestrator-playbook.md \
   prompts/classifier.md \
   prompts/planner.md \
   prompts/maker.md \
   prompts/checker-report-only.md \
   prompts/searcher.md "$export_dir/prompts/"
cp schemas/classification-result.schema.json \
   schemas/review-result.schema.json "$export_dir/schemas/"
cp docs/PROJECT_CONFIGURATION.md docs/MODEL_ROUTING.md docs/EVOLUTION.md \
   docs/WORK_MODEL.md "$export_dir/docs/"
printf '%s\n' "$export_dir"
(cd "$export_dir" && find . -type f -print | LC_ALL=C sort)
```

Copiam-se apenas os caminhos explícitos, todos arquivos regulares. Outros arquivos da origem, inclusive `.gitignore`, histórico, configurações locais e backlog, não entram. Não use cópia recursiva da origem para exportar. A exportação não publica nem instala nada.

Para conferir os 17 arquivos, execute a partir da mesma raiz:

```sh
checksum_file=$(mktemp /tmp/tl-orchestrator-sha256.XXXXXX) &&
shasum -a 256 README.md SKILL.md LICENSE \
  prompts/orchestrator.md prompts/orchestrator-perfis.md \
  prompts/orchestrator-playbook.md prompts/classifier.md prompts/planner.md \
  prompts/maker.md prompts/checker-report-only.md prompts/searcher.md \
  schemas/classification-result.schema.json schemas/review-result.schema.json \
  docs/PROJECT_CONFIGURATION.md docs/MODEL_ROUTING.md docs/EVOLUTION.md \
  docs/WORK_MODEL.md \
  > "$checksum_file" &&
(cd "${export_dir:?Execute primeiro o bloco de exportação}" && shasum -a 256 -c "$checksum_file")
```

O manifesto fica fora do pacote exportado. O encadeamento com `&&` só inicia a conferência se
todos os hashes de origem forem gerados com sucesso; arquivo ausente, cópia alterada ou erro de
leitura retorna falha. `sha256sum` pode substituir `shasum -a 256` se for a ferramenta disponível.
A comparação executada é evidência pontual, não certificação automática do método.

## Instalar e ativar

Escolha uma pasta de skills suportada pelo seu agente conforme a documentação disponível no ambiente. Crie nela um diretório **novo** chamado `tl-orchestrator` e copie todo o pacote exportado, mantendo os subdiretórios. Não sobreponha uma instalação existente sem antes comparar seu conteúdo.

Exemplo genérico, depois de definir `skills_parent` com a pasta escolhida:

```sh
install_dir="$skills_parent/tl-orchestrator"
mkdir "$install_dir"
cp -R "$export_dir/." "$install_dir/"
```

A raiz instalada contém os contratos; a raiz do projeto consumidor contém a tarefa, as regras e os portões. O [Quick Start](#quick-start--instalar-no-projeto-atual) descreve o perfil local `_tl-orc/`; este bloco manual também serve para uma instalação global ou outro destino já confirmado. Sem `_tl-orc/INSTALLATION.md`, a conferência automática de atualizações fica não aplicável e não acessa a rede; adote o Quick Start para habilitá-la. Uma instalação global pode ter precedência sobre a de projeto, então confira as [instalações concorrentes](docs/PROJECT_CONFIGURATION.md#instalações-concorrentes) antes de manter as duas. Informe ao agente o projeto e o resultado desejado. Exemplo: “Use esta skill para **somente planejar** a mudança descrita na story do projeto atual; não implemente nem despache agentes.”

Os limites, a divisão de papéis e a autoridade do usuário estão no [contrato do Orquestrador](prompts/orchestrator.md). O método não fornece lock atômico, journal, certificado automático, validação automática de schema, notificações fora da ativação ou continuidade fora da sessão.
