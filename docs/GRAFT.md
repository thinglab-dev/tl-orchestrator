# Graft: economia de contexto (opcional)

Graft é um acelerador **opcional e local**: ele lê seu código uma vez e monta um mapa
estrutural (funções, classes, quem chama quem), para o agente gastar menos tempo
reexplorando o repositório a cada tarefa. Nada nele é pré-requisito do tl-orchestrator —
sem ele, o agente continua trabalhando normalmente com leitura direta e `rg`.

## Onde o helper mora (importante para os comandos abaixo)

O `tl_graft.py` é distribuído **dentro do pacote**, não solto na raiz do seu projeto. Num
consumidor que instalou o tl-orchestrator, ele está em:

```
_tl-orc/package/scripts/tl_graft.py
```

Por isso todos os comandos precisam (a) apontar para o helper onde ele realmente está e
(b) dizer em que projeto operar, com `--target`. O helper **não** assume que o diretório
atual é o alvo. Em caminhos com espaços ou acentos — comuns no Windows — as aspas são
obrigatórias nos dois lugares:

```
python "_tl-orc/package/scripts/tl_graft.py" --target "C:/Users/Você/Meu Projeto" status
```

Se o layout do consumidor for outro, localize o arquivo antes de usar (`rg --files -g
tl_graft.py`) e use o caminho encontrado. As opções globais `--target` e `--json` vêm
**antes** do subcomando; `--mode`/`--arg` vêm depois dele.

## Como ativar

Basta pedir em linguagem natural, por exemplo:

> "ative a economia de contexto"

O agente executa o `setup` por você:

```
python "_tl-orc/package/scripts/tl_graft.py" --target "<seu projeto>" setup
```

Esse comando:

1. Verifica se há Node.js/npm no seu ambiente. Se não houver, ele avisa e segue sem
   travar a tarefa — nada é instalado.
2. Cria o cache isolado `.tl-orc-graft-cache/` **já auto-excluído** (veja a seção
   seguinte) e só então instala uma versão fixa e conferida do Graft oficial
   (`@nanonets/graft@0.18.0`, pacote `graft` da
   [trailhq/Graft](https://github.com/trailhq/Graft)). A instalação é local ao seu
   projeto: não é global e não mexe em outros projetos.
3. Gera o mapa estrutural do código (`.tl-orc-graft-cache/graph/`) **sem usar nenhuma
   IA e sem precisar de chave de API** — é só análise sintática (tree-sitter).

Isso é "ativar": preparar (instalar) e gerar o mapa acontecem juntos, num único passo.
**Nenhum arquivo do seu projeto é criado ou reescrito por esse comando** — nem o seu
`.gitignore`, nem o seu `.ignore`. Tudo o que o helper escreve fica dentro de
`.tl-orc-graft-cache/`.

**Importante:** este helper nunca roda `graft init`. O `init` do Graft oficial escreve
arquivos em `.claude/`, `AGENTS.md`, `GEMINI.md`, `~/.codex/` etc. para "religar" outros
agentes de código — isso é justamente o que não fazemos aqui, para preservar suas
integrações existentes e não configurar nada global sem uma ação explícita separada.

### Layouts que o helper recusa

- **Pasta-guarda-chuva sem Git próprio contendo vários repositórios.** Nesse arranjo o
  Graft oficial passaria a construir um mapa *dentro de cada repositório filho*,
  escrevendo em projetos que você não indicou. O helper detecta o layout e recusa antes
  de chamar o CLI (`workspace_layout_unsupported`); aponte `--target` para um repositório
  específico.
- **Cache redirecionado.** Se `.tl-orc-graft-cache/` (ou uma pasta dentro dele) for um
  link simbólico ou uma junção do Windows, o helper recusa (`cache_path_redirected`) em
  vez de instalar, consultar ou apagar através do link.
- **Cache de outro dono.** Se já existir um `.tl-orc-graft-cache/` que não foi criado por
  este helper (ele deixa um selo de propriedade), nada é sobrescrito nem removido.

Em todos os casos a tarefa segue: o agente volta para `rg`/leitura direta.

## Consultar o mapa

Quando o agente precisar entender uma dependência, assinatura de função ou "quem usa
isso" antes de editar, ele pode consultar o mapa em vez de reabrir vários arquivos:

```
python "_tl-orc/package/scripts/tl_graft.py" --target "<projeto>" --json query --mode ask --arg "como funciona o login"
python "_tl-orc/package/scripts/tl_graft.py" --target "<projeto>" --json query --mode callers --arg nome_da_funcao
python "_tl-orc/package/scripts/tl_graft.py" --target "<projeto>" --json query --mode skeleton --arg caminho/do/arquivo.py
python "_tl-orc/package/scripts/tl_graft.py" --target "<projeto>" --json query --mode grep --arg "TODO"
python "_tl-orc/package/scripts/tl_graft.py" --target "<projeto>" --json query --mode map
```

Se o caminho exato do código já é conhecido, o agente continua lendo o arquivo
diretamente — a consulta é só para exploração ambígua. Se a consulta falhar, der
timeout, vier vazia ou o mapa estiver desatualizado/ausente, isso **não** significa que o
código não existe: o agente cai de volta para `rg`/leitura direta automaticamente.

**Uma resposta só é entregue como boa se o mapa foi verificado como atual.** Depois de
cada consulta bem-sucedida o helper roda uma checagem de frescor (`graft check`) e, se o
mapa tiver ficado para trás em relação ao código, devolve `ok: false` com motivo
`stale_graph` em vez de uma resposta possivelmente desatualizada. O custo disso é uma
segunda chamada ao CLI por consulta — é deliberado: uma resposta silenciosamente velha
sobre "quem chama esta função" é pior que uma consulta a mais.

## Ver o estado atual

```
python "_tl-orc/package/scripts/tl_graft.py" --target "<projeto>" --json status
```

Mostra se o Graft está ativo neste projeto e se o mapa está em dia ou precisa ser
regenerado. Falha de execução (timeout, erro, saída ilegível) aparece como falha — nunca
como "tudo certo".

## Desativar

```
python "_tl-orc/package/scripts/tl_graft.py" --target "<projeto>" disable
```

Remove só o cache (`.tl-orc-graft-cache/`) deste projeto, e só se o selo de propriedade
indicar que foi este helper que o criou. Seu código e suas configurações de outros
agentes não são tocados. Rodar `setup` de novo reativa normalmente.

## Isolamento por worktree e caminhos com espaços

O cache é sempre calculado a partir da raiz do worktree Git atual (ou do diretório
indicado em `--target`), então cada worktree/clone tem o seu próprio mapa — nada é
compartilhado entre diretórios diferentes. Caminhos com espaços e acentos funcionam
normalmente, desde que citados entre aspas na linha de comando.

## O que muda nos seus arquivos de ignore: nada

O cache se auto-exclui. O helper escreve `.tl-orc-graft-cache/.gitignore` e
`.tl-orc-graft-cache/.ignore` contendo `*`, o que deixa **o cache inteiro** — CLI
instalado, `node_modules`, mapa, estado interno — fora do `git status`, fora de diffs e
fora de buscas do `rg`. Isso acontece antes de qualquer instalação, e permanece mesmo se
a instalação falhar no meio.

Seus arquivos de ignore na raiz não são lidos nem alterados. Por padrão o `graft build`
mescla regras próprias no `.gitignore`/`.ignore` do projeto; o helper desliga esse
comportamento no processo que ele inicia (`GRAFT_NO_GITIGNORE` / `GRAFT_NO_IGNORE`), de
modo que a exclusão fique inteiramente dentro do cache.

## Local vs. `--deep` (pago/com IA)

Tudo que este helper faz (`build`/`ask`/`grep`/`skeleton`/`callers`/`map`/`check`) é
**estrutural**: tree-sitter, determinístico e sem custo. O Graft oficial também oferece um
modo `--deep`, que usa um modelo de linguagem (sua própria chave de API) para escrever
resumos por símbolo — isso está **fora do escopo** desta integração e nunca é acionado
automaticamente. O helper ainda remove do ambiente do subprocesso as chaves e
configurações que poderiam habilitá-lo (`GRAFT_*`, `OPENAI_*`, `ANTHROPIC_*`,
`OPENROUTER_*`, `AZURE_*`, `NODE_OPTIONS`) e aponta o carregador de `.env` do Graft para
um arquivo inexistente, para que um `.env` seu com credenciais não seja lido por ele.

## Rede e telemetria

- **`npm install`**, no `setup`: a única rede que esta integração usa deliberadamente.
- **Checagem de atualização do próprio Graft**, no upstream: o CLI dispara, em segundo
  plano e destacado, um `graft _update-check` que consulta o registro npm — em *qualquer*
  comando, não só no install. O helper suprime isso apontando `HOME`/`USERPROFILE` do
  subprocesso para dentro do cache e semeando ali um registro de checagem recente, o que
  faz o upstream considerar a informação atual e não disparar o processo. Efeito colateral
  bem-vindo: o seu `~/.graft` real nunca é escrito.
- **Telemetria**: o Graft oficial coleta telemetria anônima por padrão (contadores, nunca
  código, caminhos ou nomes de símbolos — ver `TELEMETRY.md` upstream). O helper define
  `DO_NOT_TRACK=1` em todo processo que inicia, mecanismo documentado pelo próprio
  projeto. Conferido na prática: sem a variável, uma build enfileira um evento local; com
  ela, nenhum evento é enfileirado.

## Solução de problemas

| Sintoma | O que fazer |
| --- | --- |
| "Node.js/npm não encontrados" | Instale Node.js LTS, ou simplesmente ignore — o agente segue sem o acelerador. |
| Consulta retorna erro/timeout | Não indica ausência de código. Peça para o agente ler o arquivo direto ou usar `rg`. |
| Consulta retorna `stale_graph` | O código mudou desde o último mapa. Rode `setup` de novo para regerar. |
| Mapa "desatualizado" no `status` | Normalmente não exige nada: a próxima consulta atualiza o mapa antes de responder. Rode `setup` se quiser atualizar agora. |
| `workspace_layout_unsupported` | Aponte `--target` para um repositório específico, não para a pasta que contém vários. |
| `cache_path_redirected` / `foreign_cache_dir` | Remova você mesmo o `.tl-orc-graft-cache/` suspeito e rode `setup` de novo. |
| `dotenv_file_present` | Existe um `.tl-orc-graft-cache/no-dotenv.env`. Ele só existe para *não* ser lido; apague ou renomeie esse arquivo e rode de novo. |
| `disable_incomplete` | Algum arquivo do cache está em uso. Feche o programa que o usa e rode `disable` outra vez — o que sobrou continua ignorado por Git e por buscas. |
| `install_failed` no Windows, em pasta muito profunda | Veja [caminho muito longo](#windows-caminho-muito-longo-na-instalação). |
| Quer remover tudo | Rode `disable`; para reinstalar, rode `setup` de novo. |

### Windows: caminho muito longo na instalação

Parte das dependências que o Graft instala compila código nativo, e essas ferramentas ainda
esbarram no limite histórico de 260 caracteres do Windows (`MAX_PATH`). Observado na prática
neste projeto: a partir de uma raiz muito profunda o `setup` terminou em `install_failed` e o
helper caiu para `rg`, sem quebrar a tarefa.

O que fazer, nesta ordem:

1. Ative o acelerador a partir de uma raiz mais curta (por exemplo, um worktree em
   `C:\w\<projeto>`) — é o caminho que funcionou aqui.
2. Se precisar manter a pasta profunda, habilite caminhos longos no Windows
   (`LongPathsEnabled`) e no Git (`git config --global core.longpaths true`) e tente de novo.

Não há garantia de profundidade ilimitada: a compilação nativa é de terceiros e pode falhar
mesmo com as duas opções ligadas. Se falhar, siga sem o acelerador — `rg` e leitura direta
continuam funcionando normalmente.
