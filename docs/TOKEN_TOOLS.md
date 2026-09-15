# Ferramentas de economia de tokens

Quatro ferramentas externas reduzem o que entra e o que sai do contexto sem mudar o critério de
admissão do [playbook](../prompts/orchestrator-playbook.md#admissão-de-saída-de-ferramenta) nem
afrouxar a prova exigida do Maker e do Checker. Todas ficam em **escopo de usuário** do harness,
por isso valem em qualquer projeto sem instalação por consumidor e sem que alguém precise
lembrar delas. O pacote traz apenas a política (este documento) e o script opcional
`scripts/tl_tools.py`, de biblioteca padrão, que instala, verifica e mantém tudo ligado.

Estas quatro ferramentas são globais, de usuário. [Graft](GRAFT.md) é outro acelerador, distinto
e opcional: um mapa local e por projeto do próprio código, ativado sob pedido explícito como
"prepare o mapa de código deste projeto" ou "ative o Graft".

## Política

| Ferramenta | O que reduz | Padrão | Onde age | Origem |
| :--- | :--- | :--- | :--- | :--- |
| rtk | Saída de comandos Bash lida pelo agente (tokens de entrada) | ligado | Claude Code: hook `PreToolUse` nativo que reescreve `git status` em `rtk git status`; Codex: instrução global em `AGENTS.md` | github.com/rtk-ai/rtk |
| headroom | Resultados de ferramenta já admitidos no histórico, antes de cada chamada ao modelo | ligado, modo `cache`, porta 8790 | Proxy local; roteia as sessões do `claude` em terminal via `ANTHROPIC_BASE_URL` no `settings.json` do usuário | github.com/headroomlabs-ai/headroom |
| ponytail | Código escrito além do necessário (saída e a entrada das rodadas seguintes) | `full` | Plugin do Claude Code e do Codex, mais bloco gerenciado em `~/.codex/AGENTS.md` | github.com/dietrichgebert/ponytail |
| caveman | Prosa das respostas (tokens de saída) | `lite` | Plugin do Claude Code; skill no Codex (`~/.agents/skills`) mais o mesmo bloco gerenciado | github.com/juliusbrussee/caveman |

Decisões que sustentam os padrões:

- **rtk sempre ligado.** Condensa sem apagar: a saída truncada declara como recuperar o bruto
  (`rtk recall <id>`), e `rtk proxy <comando>` repete o comando sem filtro. É o ganho mais
  direto para o Maker, que vive de portões, `git` e listagens.
- **headroom em modo `cache`.** Comprime só o delta mais novo de cada turno e congela os
  anteriores, então o cache de prefixo do provedor continua batendo; o modo `token` reescreve
  turnos antigos e invalida o prefixo, o que custa mais do que economiza em sessões longas. O
  conteúdo comprimido fica reversível por marcador `<<ccr:...>>`, recuperável pela ferramenta
  que o próprio proxy injeta. Sem PyTorch, o proxy usa apenas os compressores estruturais
  (JSON, log, código, leituras repetidas), que são os que importam para saída de ferramenta.
- **ponytail em `full`.** É a configuração medida pelo próprio projeto em sessões agênticas
  reais: menos código, menos custo e nenhuma perda de guardas de segurança. `lite` só sugere
  a alternativa mais simples; `ultra` discute o requisito, o que não cabe numa spec ratificada.
- **caveman em `lite`.** Mantém frases completas e o vocabulário técnico, o que preserva
  relatórios legíveis por humanos e por outro agente. O benchmark agêntico do ponytail mediu
  que a prosa `full` do caveman não reduz tokens em tarefas de código (+7%), e o repositório do
  caveman retirou sua porcentagem fixa de economia por falta de resultado revisado. `lite` é o
  padrão seguro; o usuário sobe o nível quando quiser.
- **Codex sem headroom por padrão.** O roteamento do Codex pelo proxy usa a autenticação
  ChatGPT e não foi validado; quem quiser, aplica `headroom install apply --providers manual
  --target codex` e registra o resultado.

### Hook de sessão

`install` registra um hook `SessionStart` de usuário
(`python ~/.claude/tl-tools/tl_tools.py session-hook`) que roda em toda sessão nova, retomada,
limpeza ou compactação. Ele garante o proxy do headroom no ar (inicia destacado e espera até
30 s), devolve o caveman ao modo da política caso um `/caveman` anterior tenha ficado colado no
flag legado, e injeta uma única linha no contexto:

```text
tl-tools: rtk ok (saída Bash condensada; `rtk proxy <cmd>` devolve o bruto) | headroom ok :8790 cache (roteado nesta sessão) | ponytail full | caveman lite
```

Quando algo falha, a mesma linha traz `INATIVO` e a causa. O hook nunca falha nem bloqueia: sai
com 0 sempre, e em falha do proxy remove `ANTHROPIC_BASE_URL` do `settings.json` para que as
próximas sessões não apontem para um proxy morto (falha aberta).

## Comandos

Rode a partir da raiz do pacote com o Python já presente no ambiente:

| Comando | Efeito |
| :--- | :--- |
| `python scripts/tl_tools.py status` | Estado por ferramenta e por harness, sem efeitos colaterais; `--brief` devolve só a linha, `--json` a estrutura. |
| `python scripts/tl_tools.py doctor` | Sondas reais (versões, proxy, PATH, `rg`, `node`); sai com 1 quando algo ligado está inativo. `--fix` instala o que faltar antes. |
| `python scripts/tl_tools.py install` | Instala e configura tudo que estiver ligado; idempotente; `--dry-run` lista as ações; `--only rtk,headroom,ponytail,caveman,self` restringe. |
| `python scripts/tl_tools.py disable <ferramenta>` | Reversão por ferramenta: remove o hook do rtk, desroteia e para o proxy do headroom, ou grava `off` para ponytail e caveman. `enable` refaz. |
| `python scripts/tl_tools.py set-mode <ponytail\|caveman> <lite\|full\|ultra\|off>` | Intensidade padrão, gravada no `env` do `settings.json`, no config da ferramenta e no bloco do Codex. |
| `python scripts/tl_tools.py proxy ensure\|start\|stop\|status` | Gerência direta do proxy local. |

A configuração fica em `~/.claude/tl-tools/config.json` (porta, modo, quais ferramentas e
harnesses). Desligar uma ferramenta é decisão do usuário; o Orquestrador só roda
`doctor --fix` quando a linha `tl-tools:` faltar ou trouxer `INATIVO`, conforme o
[SKILL.md](../SKILL.md).

## Como o método usa as ferramentas

- **Maker:** trata saída condensada e marcadores `<<ccr:...>>` como o resultado normal; repete
  com `rtk proxy <comando>` só quando o resultado vier vazio, contraditório com o exit ou
  truncado onde a prova exige o bruto, e registra quando o faz. Entrega a solução mínima que
  cumpre a spec e um relatório curto sem omitir comando, caminho, exit ou erro exato.
- **Checker:** saída condensada não é prova. Leitura obrigatória de diff, log de portão ou erro
  vem da fonte: artefato bruto, arquivo, ou `rtk proxy` somente leitura. Parecer curto continua
  exigindo achado, caminho, linha e evidência.
- **Orquestrador:** a linha `tl-tools:` no início da sessão é a evidência de ativação; sem ela,
  ou com `INATIVO`, a correção é `doctor --fix`, não uma conversa de diagnóstico. As sessões
  despachadas em terminal (`claude -p`, `codex exec`) são as que mais se beneficiam, porque
  concentram volume de saída de ferramenta e passam pelo proxy.

## Limites conhecidos

- **App desktop do Claude não passa pelo headroom.** O app sobrescreve `ANTHROPIC_BASE_URL`
  (issue #869 do headroom). Só sessões do `claude` em terminal, inclusive as despachadas pelo
  condutor, são roteadas. A linha `tl-tools:` diz em qual caso a sessão está.
- **Sem serviço persistente no Windows.** `headroom install apply --preset persistent-service`
  cai para o Agendador de Tarefas e falha sem privilégio (`Acesso negado`). O `tl_tools.py`
  mantém o proxy como processo destacado; depois de reiniciar a máquina, o primeiro hook de
  sessão o sobe de novo em poucos segundos.
- **Porta 8787 pode estar ocupada.** O padrão do headroom colidiu com outro programa na máquina
  de referência; o padrão do `tl_tools.py` é 8790 e muda em `config.json`.
- **Python da Microsoft Store virtualiza `AppData`.** Escritas em `%APPDATA%` feitas por esse
  Python vão para uma pasta privada do pacote e o Node dos plugins não as vê. Por isso o modo
  padrão de ponytail e caveman é fixado por variável de ambiente no `settings.json`
  (`PONYTAIL_DEFAULT_MODE`, `CAVEMAN_DEFAULT_MODE`), herdada pelos hooks, e o `config.json` de
  cada ferramenta é apenas melhor esforço. O mesmo Python também não consegue lançar os
  launchers do uv (`uv trampoline failed to canonicalize script path`), então o script delega o
  início do proxy ao interpretador de `Programs\Python`, e registra o hook de sessão com ele.
- **Flag legado do caveman é pegajoso.** `~/.claude/.caveman-active` tem precedência sobre a
  configuração em toda sessão nova; o hook de sessão o devolve ao modo da política.
- **PATH do Codex é herdado do processo pai.** Um app aberto antes de `~/.local/bin` entrar no
  PATH não enxerga `rtk`; o bloco gerenciado em `~/.codex/AGENTS.md` informa o caminho completo,
  e reiniciar o app resolve. `rtk` também precisa de `rg` (ripgrep) no PATH.
- **Hooks de plugin do Codex exigem confiança interativa.** A ativação sempre ligada de ponytail
  e caveman no Codex vem do bloco em `AGENTS.md`, não dos hooks do plugin.
- **Compressão é perda controlada.** O headroom guarda o original e o devolve sob demanda, mas o
  modelo decide quando pedir. As regras do Checker acima existem por isso.
- **Sessões curtas não pagam a ativação.** Cada ferramenta acrescenta contexto fixo (regras do
  ponytail e do caveman, `RTK.md`, a linha `tl-tools:`), e o ganho aparece com volume de saída
  de ferramenta e turnos. Ver as medições.

## Medições

Ambiente de referência: Windows 11, Claude Code 2.1.271 (Opus), Codex CLI 0.154.0, rtk 0.49.0,
headroom 0.37.0, ponytail 4.10.0, caveman 2.6.0, 2026-09-14. São medições pontuais desse
ambiente, não taxas transferíveis.

**Ativação automática (Claude Code em terminal, `claude -p`).** Sem nenhum pedido sobre
ferramentas, a sessão citou a linha `tl-tools:` recebida no início, rodou `git status` e `ls`
e relatou a saída condensada com o marcador de recuperação do rtk. O `rtk gain` registrou 416
tokens de entrada, 171 de saída e 58,9% economizados nos dois comandos; o `/stats` do headroom
contou a requisição roteada; o hook de sessão levou 0,2 s.

**Ativação automática (Codex, `codex exec`).** Com o bloco gerenciado em `AGENTS.md`, o Codex
declarou rtk em todo comando, ponytail `full` e caveman `lite`, e executou `rtk git status`
como primeiro comando. Antes do bloco, ponytail e caveman apareciam apenas como skills
disponíveis, sem ativação.

**Auto-recuperação do proxy.** Com o proxy encerrado à força (`tl_tools.py proxy stop`), uma sessão
nova `claude -p` recebeu a linha `tl-tools:` com `headroom proxy iniciado agora`, o hook levou 8,8 s
para subir o proxy e a primeira requisição respondeu normalmente; sessão inteira em 17 s. Antes da
correção do interpretador (ver limites), o mesmo teste falhava com `Connection refused` depois de
217 s de tentativas.

**Mesma tarefa com e sem a configuração pessoal (2 rodadas cada).** Tarefa: rodar uma suíte,
listar assinaturas de um módulo, criar e provar um script pequeno. A baseline foi uma
configuração limpa, sem nenhum plugin; a variante com ferramentas carregou a configuração real
do usuário, com onze plugins ativos além dos quatro desta política.

| Variante | Turnos | Custo (US$) | Cache escrito | Cache lido | Saída | Linhas do script |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| limpa 1 | 8 | 0,35 | 20.690 | 189.651 | 1.940 | 18 |
| limpa 2 | 11 | 0,27 | 11.773 | 152.523 | 3.030 | 18 |
| ferramentas 1 | 7 | 0,50 | 33.910 | 154.833 | 3.130 | 6 |
| ferramentas 2 | 8 | 0,47 | 33.756 | 115.689 | 3.046 | 6 |

Leitura honesta: menos turnos e um script três vezes menor com as ferramentas (efeito do
ponytail), mas custo maior, porque a variante carregou todo o contexto fixo da configuração
pessoal, não só o das quatro ferramentas. Essa comparação mede o preço da configuração inteira,
não o das ferramentas; a comparação justa está abaixo.

**Mesma tarefa, mesma configuração pessoal, só as quatro ferramentas desligadas (2 rodadas
cada).** A variante "sem" usou uma cópia da configuração real com o hook do rtk e o hook de
sessão removidos, `ANTHROPIC_BASE_URL` e os modos retirados do `env`, `@RTK.md` fora do
`CLAUDE.md` e os plugins ponytail e caveman desabilitados; tudo o mais igual.

| Variante | Turnos | Custo (US$) | Cache escrito | Cache lido | Saída | Linhas do script |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| sem 1 | 8 | 0,54 | 30.267 | 329.830 | 2.938 | 17 |
| sem 2 | 11 | 0,51 | 31.344 | 210.060 | 3.561 | 17 |
| com 1 | 8 | 0,48 | 34.182 | 117.007 | 2.991 | 18 |
| com 2 | 11 | 0,51 | 34.402 | 115.360 | 4.148 | 18 |

Leitura: mesmos turnos e mesmas quatro partes entregues (suíte verde, assinaturas corretas,
script executado) nas quatro sessões, sem perda observável de qualidade. O cache lido caiu 45% a
65% com as ferramentas, porque o proxy adia os esquemas de ferramentas e comprime os resultados
admitidos; o custo caiu 12% numa rodada e empatou na outra, já que o cache escrito subiu cerca
de 4 mil tokens por sessão (regras do ponytail e do caveman, `RTK.md`, ferramenta de
recuperação do proxy). O tamanho do script não mudou nesta amostra, ao contrário da comparação
anterior; o efeito do ponytail em tarefas triviais é inconsistente com duas rodadas. Durante a
rodada 1 com ferramentas, o `/stats` do headroom acumulou 11 requisições, 22 mil tokens removidos
por compressão e 228 mil tokens economizados somando todas as camadas; o contador é global da
máquina, então outros processos podem contribuir. A conclusão prática: em sessão curta o
resultado é neutro a levemente positivo; o ganho cresce com volume de saída de ferramenta e
número de turnos, que é o perfil das stories despachadas pelo condutor.
