# Protocolo de execução por artefatos

Este documento define como uma unidade autorizada é despachada, executada e devolvida sem conversa
de acompanhamento. O condutor (a sessão que coordena) despacha uma unidade, recebe um recibo
compacto e volta a gastar turnos apenas para um resultado terminal ou uma decisão material. Os
agentes trabalham por artefatos; portões e revisão independente continuam decidindo qualidade.

O protocolo é documental: vale com ou sem automação. O [supervisor opcional](../scripts/tl_job.py)
apenas transporta uma execução já autorizada; ele não escolhe modelo, não inventa comando e não
aprova entrega.

## Orçamento de contexto do Orquestrador

O custo dominante pode ser a quantidade de requisições que reenvia um contexto grande, não uma
leitura isolada. Por isso estas regras são verificáveis:

- dispare o processo em segundo plano uma vez e espere sua notificação de fim, sem polling, leitura
  parcial de saída ou checagens de progresso;
- por parada, leia do `result.json` somente `blocking` e `reason`;
- diagnóstico que exija código do condutor vira unidade de manutenção ou sessão nova, nunca leitura
  exploratória na conversa do Orquestrador;
- não envie mensagens de status entre passos triviais e agrupe comandos independentes numa chamada;
- acima de aproximadamente 120 mil tokens de contexto, grave um handoff curto em arquivo e
  recomende sessão nova.

Essas regras também delimitam ownership: salvo permissão manual explícita e específica, o
Orquestrador não edita nem diagnostica o consumidor; despacha trabalho e lê recibos.

## Unidade de execução

Uma **unidade** (`unit`) é um despacho com começo, critério de aceite e resultado terminal únicos.
Ela é identificada por um `unit` estável e nunca é reaproveitada para outro conteúdo.

**O despacho padrão de topo é a story inteira**, com a cadeia de papéis autorizada correndo dentro
dela: `<story>-<rodada>`, como `T012-1`. O condutor despacha uma vez e volta a gastar turno apenas
por resultado terminal ou decisão material. Os recibos de Maker, portões e Checker são internos ao
condutor da unidade; eles ficam no disco e não sobem como turnos.

Um job por papel — `<story>-<papel>-<rodada>`, como `T012-maker-1` — é **opcional** e existe para
consulta pontual ou uso direto do supervisor. Quebrar a story em microjobs não autoriza turnos de
acompanhamento: se cada papel volta ao condutor para ser empurrado adiante, a conversa de
acompanhamento apenas mudou de nome.

Limite real: encadear os papéis dentro de uma unidade exige um condutor adaptado no consumidor, que
leia o `result_file` de cada papel e decida o próximo despacho sem perguntar. Sem daemon ou
callback comprovado no ambiente, o que existe é uma unidade por vez, despachada pela ativação
corrente. Declare esse limite em vez de prometer uma automação que ainda não existe ali.

### Execução sob Modo Automático (batches)

Quando o condutor opera sob um lote autorizado no Modo Automático ([WORK_MODEL.md](WORK_MODEL.md#modo-automático-execução-de-lote-finito-autorizado)), a execução de cada unidade individual no estado `EXECUTE` segue este protocolo por artefatos. O snapshot congelado do batch (`_tl-orc/project/batches/Bnnn.md`) fornece os limites de escopo e autoridade; o condutor consome o recibo terminal compacto (< 4 KiB) de cada unidade para validar o critério de aceite, registrar o encerramento da unidade e avançar para a próxima unidade elegível ou disparar os portões canônicos de fronteira de integração (T016), sem subir logs intermediários para a conversa principal.

O envelope de despacho declara, em texto ou em arquivo:

| Campo | Conteúdo |
| :--- | :--- |
| `unit` | identificador estável da execução |
| `role` | papel executado (Planner, Maker, Checker, Searcher) |
| `spec_ref` | caminho da spec e a revisão de conteúdo revisada (`content_id` ou hash) |
| `authority_ref` | referência da autorização já existente que cobre esses efeitos |
| `task` | resultado esperado e condição de parada |
| `acceptance` | critérios verificáveis do aceite |
| `scope_paths` | caminhos que o papel pode escrever |
| `references` | leituras obrigatórias por caminho e hash, não por transcrição |
| `result_file` | caminho relativo do JSON final que o papel escreve ao terminar; não existe antes da unidade começar |

Referência é por caminho e hash. Não cole conteúdo de arquivo, log ou transcrição no envelope
quando o destinatário puder abrir o caminho; o hash é o que prende o parecer ao conteúdo revisado.

## Resultado da unidade

Ao terminar, o papel grava em `result_file` um único objeto JSON com esta lista fechada:

```json
{
  "outcome": "ready_for_delivery",
  "decision": "uma frase sobre a decisão material tomada ou pendente",
  "blockers": ["impedimento observável, se houver"],
  "next_action": "o próximo passo concreto de quem recebe",
  "observable_usage": "unknown",
  "proof_refs": ["_tl-orc/project/evidence/<story>-verification.md"]
}
```

`outcome` aceita apenas `delivered`, `ready_for_delivery`, `blocked` e `failed`. As quatro são
distintas: `ready_for_delivery` não é entrega, `blocked` não é falha e retorno vazio não é sucesso.
Campos fora da lista são descartados no recibo, e o descarte é declarado. Narrativa, log e relatório
longo ficam no disco e entram por referência.

`observable_usage` é **consumo observado**, não verificação do resultado nem estimativa. Ele aceita
uma única string curta e vale em três formas: uma medida que o papel realmente observou
(`"3 despachos, 2 rodadas de portão"`); uma referência ao lugar onde a métrica existe
(`"harness: painel de uso da sessão"` ou um caminho de artefato); ou `"unknown"`, que é a resposta
correta quando nada foi medido. Não escreva número inventado nem `0` para preencher o campo, e não
descreva ali como conferir a árvore — isso pertence a `next_action` e a `proof_refs`. O supervisor
não coleta tokens, custo nem uso do harness: ele repassa o que o papel escreveu, recortado por bytes.

## Contexto por papel

Cada papel executa em sessão própria, com o contexto do seu envelope. Não existe contexto
compartilhado implícito entre papéis: o que um papel precisa saber está na spec, nos caminhos
referenciados ou no resultado do papel anterior.

Retomada em sessão nova usa um **checkpoint limitado** — unidade, revisão da spec, o que já foi
escrito, o que falta, provas já executadas — validado contra a árvore atual antes de qualquer
escrita. Resumo de conversa não é fonte de estado por padrão: ele descreve o que foi dito, não o que
existe no disco. Divergência entre checkpoint e árvore é ponto de parada, não detalhe a conciliar em
silêncio.

## Cadeia de execução

No condutor do consumidor, a cadeia autorizada é:

1. **Maker** implementa dentro do escopo congelado e grava seu resultado.
2. **Portões** do consumidor rodam sobre a árvore resultante.
3. **Checker** independente revisa **o diff integral**, sem editar, e emite parecer vinculado ao
   conteúdo revisado. Ler acréscimo e remoção linha a linha é responsabilidade dele, não do condutor.
4. **Correção limitada** volta ao Maker apenas para os achados em escopo, dentro do limite de
   rodadas declarado.
5. **Prova própria** do condutor, que confere a revisão sem refazer a leitura integral:
   - **identidade e revisão** — o parecer e os portões são da revisão entregue (`content_id` ou hash
     do diff), não de outra rodada;
   - **cobertura** — os caminhos e critérios da spec aparecem no que foi revisado; caminho fora de
     `scope_paths` ou critério sem menção é achado, não detalhe;
   - **portões** — rodaram na árvore final, com comando e saída literais no artefato;
   - **riscos e achados abertos** — cada um tem destino declarado: corrigido, aceito ou registrado;
   - **amostra crítica dirigida** — leia na árvore o trecho de que o aceite depende, escolhido pelo
     risco, e a fonte de uma prova. Para sondagem independente, despache um verificador próprio.
6. **Entrega** conforme a autoridade existente.

Verificação visual ou outra ação humana marcada pela spec como `deferred`, com responsável,
procedimento e resultado esperado, é preservada no parecer e na evidência como pendência
não bloqueante. Ela não vira `intent_gap` nem interrompe o condutor, salvo se a política do consumidor
a exigir antes da entrega. O rótulo não serve para adiar prova automatizável ou encobrir falha.

Não peça o parecer integral de volta ao contexto do condutor: o Checker entrega veredito, achados e
caminho do relatório; o corpo do relatório e o diff ficam no disco. Reproduzir o diff inteiro no
condutor refaz exatamente o trabalho pesado que o despacho por artefatos existe para evitar.

O condutor recebe, entre os passos, apenas: uma exceção material (decisão humana, escopo alterado,
falha sem atribuição, capacidade ausente) ou o resultado terminal da unidade. Progresso repetido não
é evento; o que merece um turno é uma mudança de estado que altera a próxima ação.

Exit zero do transporte não aprova nada. Aprovação continua exigindo prova real: parecer vinculado à
revisão, portões executados com saída literal e a conferência dirigida do condutor. Autorrelato,
silêncio de processo e recibo com exit zero não são prova.

## Espera local não é polling de modelo

Esperar uma unidade longa deve custar um processo local, não turnos de modelo. Um processo local lê
arquivos e dorme; ele não faz chamadas de IA e não consome contexto.

Sem um callback comprovado no ambiente, não prometa retomada autônoma depois que o harness fechar: o
processo local continua até terminar e grava seu resultado no disco, mas quem lê esse resultado é a
próxima ativação. Uma tarefa agendada do harness pode iniciar essa ativação quando o consumidor a
configurar; o método não fornece daemon, agendador ou notificação própria.

## Recuperação operacional e estado em worktrees

Se um `advance` falhar depois de invalidar o checkpoint, `--resume` não recupera a execução.
Registre a causa, execute `stop` e rode a story novamente; não tente reconstruir o checkpoint
invalidado à mão.

Hooks e guardas de manutenção que procurem `state.json` em repositórios Git resolvem primeiro o
git-dir do worktree com `git rev-parse --absolute-git-dir`. Somente se não houver estado próprio
consultam o common-dir. Assim worktrees simultâneos não leem nem alteram a sessão um do outro, e um
estado legado comum continua disponível como fallback controlado.

## Supervisor opcional

`scripts/tl_job.py` usa apenas a biblioteca padrão do Python 3 e é opcional: o método documental
permanece utilizável sem ele, com as limitações de automação descritas acima.

Três comandos:

- `start` reivindica a unidade, grava o manifesto e inicia um supervisor local destacado (sem
  janela no Windows, em nova sessão no POSIX). Devolve um recibo inicial só com identidade, estado e
  localizadores.
- `wait` espera localmente pelo resultado terminal, lendo arquivos. O `--timeout` é validado antes do
  laço, como em `start`: zero, negativo, não numérico, infinito, `NaN` ou acima do limite viram
  `invalid_input` de imediato, sem espera.
- `result` e `status` imprimem, respectivamente, o resultado terminal sob a lista fechada e um
  instantâneo curto que nunca lê os logs.

Além desses há o subcomando interno `supervise`, que é como o `start` reentra no script já destacado.
Ele é alcançável da linha de comando, então não confia em diretório algum que lhe entreguem: recebe
`--state-dir` e `--unit` — nunca um diretório de job arbitrário —, refaz o limite de caminho do
`start` (diretório de estado fora do pacote, componentes simples, job contido na árvore de estado,
link recusado por `realpath`) e valida o manifesto inteiro antes de ler ou executar qualquer coisa:
lista fechada de campos, tipos, schema, `unit` coincidente com o pedido, `cwd` e arquivo de
resultado dentro dos limites. Qualquer divergência é recusada com `invalid_input` e efeitos `none`,
sem executar argv e sem criar log. Isso fecha a reentrada do próprio método; não substitui a
permissão do sistema de arquivos sobre um diretório de estado que o consumidor escolha expor.

Uma unidade terminada nunca é reaberta. Antes de tomar o lease e antes de qualquer execução, o
`supervise` recusa com `conflict`, efeitos `none` e saída `3` a unidade que já tem `result.json`, sem
tocar em arquivo algum. A checagem é a existência do arquivo terminal, não o conteúdo dele: resultado
corrompido ou truncado também barra a segunda execução, e apagar o arquivo de resultado nomeado pelo
manifesto não devolve a unidade ao estado executável. Uma autorização responde por uma execução.

Essa validação do manifesto é a mesma para todo leitor da reivindicação — `start` na reentrada,
`status`, `wait` e `result`. Manifesto ilegível, com campo faltando, com tipo errado ou escrito para
outra unidade vira recibo `invalid_input` com efeitos `none` e saída `2`; ele nunca é consertado,
reaproveitado como identidade nem executado. Manifesto ausente e manifesto ilegível não são a mesma
coisa: a reivindicação chega por rename, então só o nome que ainda não existe é esperado pela janela
curta de reivindicação concorrente. Um arquivo presente que não se lê como reivindicação — JSON
inválido, texto que não é UTF-8, acima do teto de bytes ou que não é objeto — nunca vai virar um; ele
é recusado de imediato como `invalid_input`, e não reportado como `conflict` depois da espera. O
mesmo vale para o arquivo que sequer pode ser inspecionado: só o nome inexistente
(`FileNotFoundError`) conta como ausência esperada, enquanto permissão negada ou erro de E/S no
`stat` responde `invalid_input` na hora, nomeando o motivo, em vez de esperar por uma reivindicação
que não está a caminho.

Entre os dois há um caso estreito, e ele tem janela própria. A publicação é um rename, e no Windows o
nome que o rename acabou de criar pode, por um instante, recusar a abertura de quem chega ali dentro
— acesso negado, violação de compartilhamento ou de trava. Ler essa recusa como reivindicação
ilegível transformava um `start` concorrente legítimo, que é justamente o caso para o qual o
reaproveitamento existe, em `invalid_input`. Então, e só então — nome que acabou de inspecionar bem e
abertura negada —, a leitura é repetida dentro de um orçamento curto e fixo (um segundo), aberto uma
única vez por chamada e nunca reiniciado a cada nova recusa. Passado o orçamento, a resposta é a
mesma recusa de antes, com o motivo original: uma reivindicação que este processo não consegue ler.
Nada é consertado nem reescrito ali; a repetição só relê. No POSIX nenhuma publicação recusa leitor
assim, de modo que a classe é vazia na prática e uma recusa que apareça mesmo assim custa esse atraso
limitado antes da mesma resposta — preferido a um desvio por plataforma que os testes não
conseguiriam exercitar dos dois lados.

Sucesso terminal exige fim comprovado, não arquivo presente. O `result.json` do diretório da unidade
fica ao alcance da própria unidade, e todo campo dele — impressões incluídas — é recomputável a
partir do `manifest.json`; logo o arquivo sozinho não diz quem o escreveu nem quando. Por isso
`wait` e `result` só leem um resultado como terminal depois que o supervisor daquela unidade está
provadamente encerrado, pela mesma trava exclusiva que prova liveness: enquanto ela estiver tomada, o
`wait` continua esperando e o `result` responde `indeterminate` com efeitos `uncertain` e saída `5`,
mesmo com um `result.json` completo no disco. Sem prova de fim — plataforma sem trava exclusiva ou
lease que nunca chegou a existir, lease trocado por outro arquivo — nada é afirmado como sucesso em
silêncio: `wait` e `result` recusam com estado `indeterminate`, efeitos `uncertain` e saída `5`, nunca
com saída `0`, e o recibo declara o campo `termination` (`unproven`, `unsupported`, `replaced`,
`diverged`, `unanchored`) dizendo qual fim não pôde ser provado. A recusa continua sujeita ao teto de bytes do recibo como qualquer
outra: `termination` não é exceção.

Além do fim, a forma conta: o registro terminal precisa carregar todos os campos
que o próprio supervisor sempre grava (`schema`, `job_id`, `unit`, `state`, `effects`, `exit_code`,
`started_at`, `finished_at`, `logs`, `containment`, `result_status`, impressões do manifesto e da
autorização); um registro mais curto é indeterminado, não uma entrega da unidade. A prestação de
contas sobre a árvore é parte dessa forma: `containment` precisa vir completo e tipado — `kind`,
`established`, `unit_ran` e, quando a árvore foi estabelecida, `swept` —, e `logs` precisa trazer
exatamente `stdout` e `stderr`. Campo ausente nunca é lido como prova de que nada escapou; registro
parcial responde `indeterminate` com efeitos `uncertain` e saída `5`. Isso vale também para a
prestação de contas dos escapados: uma varredura de alcance provado só é lida como entrega quando o
registro traz `accounted` num alcance que presta contas, conforme a seção da contenção.

Estados de transporte: `starting`, `running`, `exited`, `timeout`, `crashed`, `start_failed`,
`wait_timeout`, `indeterminate`, `conflict`, `invalid_input`, `unknown` e `receipt_overflow`. Eles
descrevem o transporte, não o mérito da unidade. Estado é rótulo de lista fechada. A lista que o
leitor aceita **do disco** é menor, porque é só o que o próprio supervisor grava em `status.json` ou
`result.json`: `starting`, `running`, `exited`, `timeout`, `crashed` e `start_failed`. Os demais
nascem no próprio recibo, nunca de um arquivo. Qualquer outra coisa gravada no disco — inclusive um
rótulo desta lista maior plantado à mão — é lida como `unknown` e nunca repassada como texto do
recibo.

O recibo bem-sucedido de `start` e `status` traz apenas identidade (`schema`, `job_id`, `unit`),
estado e localizadores; o de `start` acrescenta o token da vinculação em `binding`, e o `start` que
reaproveita a reivindicação acrescenta também `reused`. As impressões
do manifesto e da autorização ficam no manifesto privado e no confronto de identidade, não no recibo:
repeti-las custava bytes sem dar ao condutor nada acionável. O campo `effects` aparece onde há um
motivo observável a declarar — no resultado terminal, no recibo de erro ou conflito e no
`wait_timeout` — com os valores `none`, `known` ou `uncertain`.

O teto de bytes do recibo é promessa, não preferência. Toda string que vem do disco entra no recibo
recortada por bytes, e, quando o teto pedido é pequeno demais até para a identidade, o recibo é
reduzido a um mínimo fixo — `state` `receipt_overflow` com `clipped` — em vez de emitir conteúdo além
do limite. O recibo permanece JSON UTF-8 válido em qualquer um desses cortes.

O próprio `--max-bytes` é validado **dentro** dessa fronteira, como o `--timeout`: o parser recebe o
valor como texto e quem o interpreta é o comando. Valor que não é número inteiro — `nope`, vazio,
`4k`, `12.5`, `inf` — responde um recibo `invalid_input` com efeitos `none` e saída `2`, recortado
pelo teto padrão, antes de reivindicar diretório ou executar argv. Número abaixo do mínimo continua
sendo elevado ao mínimo, como em qualquer outra chamada que imprime recibo. Assim o chamador nunca
recebe despejo de uso do argparse nem traceback no lugar do recibo: o que ele lê continua sendo JSON
de uma linha dentro de um limite conhecido, inclusive quando o inválido é justamente o limite.

Códigos de saída: `0` transporte e unidade bem-sucedidos; `2` entrada inválida; `3` conflito de
identidade; `4` timeout; `5` resultado indeterminado; `6` unidade falhou. Nenhum deles aprova uma
story.

A identidade é `unit` mais a impressão do manifesto (comando, diretório, autorização, timeout,
arquivo de resultado). O diretório da unidade é a reivindicação atômica: um segundo `start` com o
mesmo manifesto reaproveita o resultado sem executar de novo; com manifesto diferente, ele recusa
com `conflict` em vez de reutilizar. Não há repetição automática de escrita.

### Contenção da árvore do job

Uma unidade raramente é um processo só: ela cria filhos. O supervisor assume a árvore antes de a
unidade executar qualquer instrução e, ao terminar, varre a árvore — não apenas o líder. Só a árvore
criada por este despacho é atingida; o supervisor não procura processo por nome nem sinaliza processo
alheio.

- No Windows o processo nasce suspenso e é atribuído a um **Job Object** com `KILL_ON_JOB_CLOSE`
  antes de rodar; encerrar a unidade encerra o job inteiro, inclusive descendente que abriu sessão
  própria.
- No POSIX a unidade vira **líder de sessão e de grupo**, e o encerramento vai ao grupo: `SIGTERM`,
  carência curta, depois `SIGKILL`. A varredura acontece **antes** de colher o líder, para que a
  identidade sinalizada ainda seja a que este supervisor possui — nunca um PID reciclado. Descendente
  que chama `setsid()` sai do grupo e sobrevive à varredura, então varrer o grupo não basta: depois
  dela o supervisor **presta contas dos escapados** antes de soltar o lease. No Linux ele se declara
  `child subreaper` antes de a unidade existir, guarda a lista de filhos que já eram seus e, ao
  final, encerra com `SIGKILL` e colhe o que tiver sido reparentado para ele — o descendente que
  saiu da sessão cai aqui. Onde essa prestação de contas não existe, ela não é fingida (veja abaixo).
- Se a contenção não puder ser estabelecida, o supervisor **não despacha**: estado `start_failed`,
  efeitos `none`. Se ela falhar depois de a unidade já ter rodado, os efeitos são `uncertain` (saída
  `5`). O supervisor não afirma ter terminado uma árvore que não provou ter terminado.

O recibo traz `containment` com `kind`, `established`, `unit_ran` e `swept` — o alcance realmente
varrido (`job_object`, `process_group` ou `unproven`). Só `job_object` e `process_group` são alcances
provados. Varredura `unproven` significa que nenhuma árvore foi provada encerrada, e por isso o
resultado é **indeterminado por definição**: efeitos `uncertain` e saída `5`, mesmo com a unidade
tendo saído com código zero e payload admitido. Um recibo que não prova ter encerrado a árvore não
pode ser lido como unidade entregue. Timeout continua marcando efeitos `uncertain`: conter a árvore
diz o que parou de rodar, não o que já foi escrito antes da parada.

Onde a varredura foi de alcance provado, o `containment` traz também `accounted` — a prestação de
contas dos descendentes que escaparam daquele alcance (`job_object`, `subreaper_scan` ou
`unaccounted`) e, quando ela falha, `account_failed` com o motivo. A razão é direta: o `result.json`
é recomputável a partir do `manifest.json`, então um descendente que sobreviva ao supervisor pode
substituí-lo por um registro completo, coerente e entregue depois que o lease cair — e nenhuma
leitura do conteúdo consegue distinguir isso da escrita da própria unidade. O que separa os dois
casos não é o arquivo, é não existir escritor sobrevivente: a árvore é prestada por inteiro **antes**
de o lease ser solto. Por isso `accounted` ausente, `unaccounted` ou acompanhado de `account_failed`
faz o resultado ser lido como **indeterminado**, efeitos `uncertain` e saída `5`, nunca como
entregue, mesmo com fim provado e payload admitido. Fora do Linux — sem `child subreaper` e sem
`/proc` — a contenção POSIX responde `unaccounted` por princípio; ela declara que não sabe, em vez
de prometer contenção que não tem.

### Falha interna do supervisor

O supervisor também pode falhar por conta própria — disco cheio ao abrir um log, ao gravar o
instantâneo ou ao gravar o resultado. Uma falha dessas não deixa a unidade rodando nem sem resposta:

- a árvore é encerrada pela mesma contenção que a possui, em `finally`, mesmo quando a operação
  interna falhou antes da varredura normal;
- a falha é registrada como `crashed` com efeitos `uncertain` quando a unidade pode ter rodado, e só
  como `start_failed` com efeitos `none` quando está provado que nenhum processo filho existiu. Uma
  falha posterior nunca é rebaixada a `none`;
- se o próprio disco impedir gravar o `result.json`, não há repetição: o supervisor sai indicando
  `5`, sem inventar arquivo terminal.

Para que essa última situação não se torne espera sem fim, o supervisor mantém um **lease
exclusivo** (`supervisor.lock`) no diretório da unidade enquanto vive; o sistema operacional o libera
no encerramento, inclusive em queda. A liveness é provada por esse lease, nunca por PID — um PID pode
ser reciclado e nenhum processo alheio é sinalizado por causa de um arquivo no disco. O `supervisor.json`
guarda só identidade legível (pid, início, situação do lease).

O nome não basta como prova: a unidade tem acesso de escrita ao próprio diretório e poderia pôr outro
arquivo — sem trava alguma — atrás de `supervisor.lock`, fazendo a liveness responder `gone` enquanto
ela continua viva. Por isso o `start` cria o arquivo do lease antes de tudo e grava no `manifest.json`
o campo `lease_identity`, o par dispositivo/inode do arquivo que ele mesmo criou. Todo leitor abre o
nome, compara a identidade do **descritor aberto** com a registrada na reivindicação e, se diferirem,
responde liveness `replaced` e prova `replaced`: nome que leva a outro arquivo nunca é um fim. Uma
reivindicação cujo `lease_identity` não descreve arquivo algum responde `unbound` e prova `unproven`;
um `lease_identity` corrompido é recusado como manifesto inválido (`invalid_input`, saída `2`). Nenhum
desses caminhos chega a `proven`, e por isso nenhum deles entrega registro terminal. O `lease_identity`
não entra na impressão digital do manifesto, de modo que a reutilização idempotente do `start` segue
decidida só pela unidade, autorização, diretório, argumentos, timeout e arquivo de resultado.

Mas a reivindicação também é escrita no diretório da unidade, e é isso que o `lease_identity` sozinho
não resolve: quem troca o `supervisor.lock` pode reescrever o `manifest.json` no mesmo movimento,
apontando o campo para o arquivo recém-plantado. A troca volta a parecer coerente, porque o leitor
compara a identidade do descritor com uma afirmação que o próprio atacante acabou de fazer. Por isso
o `start` publica a **vinculação** fora do que a unidade escreve, em
`<state-dir>/anchors/<unidade>.json`, criada com exclusividade (`O_EXCL`) e antes da reivindicação.
Ela guarda a unidade, a identidade do lease que o `start` criou, as impressões do manifesto e da
autorização, e um token curto derivado desses mesmos campos. O token nunca é acreditado: todo leitor
o recomputa e descarta o registro que não responda por si. Uma vinculação já existente jamais é
sobrescrita — um segundo `start` sobre diretório de unidade apagado recusa com `conflict`, efeitos
`none` e saída `3`, em vez de emitir vinculação nova para a mesma unidade.

Antes de entregar qualquer fim, `wait` e `result` confrontam a reivindicação com essa vinculação. A
resposta é `bound` quando a unidade, as impressões e o `lease_identity` coincidem; `diverged` quando
a reivindicação contradiz a vinculação — inclusive quando só o `lease_identity` foi reescrito —; e
`unanchored` quando não há vinculação legível. `diverged` e `unanchored` entram na mesma lista de
fins não prováveis que `replaced`: o `wait` deixa de esperar e responde na hora, o `result` recusa, e
os dois saem `indeterminate`, com efeitos `uncertain` e saída `5`. A recusa é fechada, não melhor
esforço: sem vinculação que responda pela reivindicação, nada é entregue, mesmo com um `result.json`
completo e bem formado no disco. O `supervise` faz o mesmo confronto antes de tomar o lease e recusa
com `conflict` o diretório cuja vinculação não responde por ele, e o reaproveitamento do `start` só é
oferecido enquanto o estado for `bound`.

Para o condutor que não quer depender de nada no disco, o recibo de `start` devolve o token da
vinculação no campo `binding`, e `wait` e `result` aceitam `--expect-binding <token>`. O token é
conferido pela forma — dezesseis caracteres hexadecimais minúsculos — antes de qualquer diretório ser
procurado, e o que não bate responde `invalid_input` com saída `2`. Token bem formado que não seja o
daquela execução recusa a entrega com `indeterminate`, `termination` `diverged`, efeitos `uncertain`
e saída `5`. Guardado fora do diretório de estado, ele é a única checagem que não é sobre arquivos
que a unidade possa alcançar.

O `wait` consulta esse lease: se ninguém o detém por uma janela curta e ainda não existe `result.json`,
ele responde `indeterminate` com efeitos `uncertain` e saída `5`, em vez de esperar o timeout inteiro.
Lease ausente não é lido como morto — o supervisor pode ainda não tê-lo tomado —, e plataforma sem
trava exclusiva responde liveness `unknown`: sem prova e sem `result.json`, o `wait` mantém o
comportamento por timeout; com um `result.json` no disco ele para de esperar, mas a leitura terminal
é recusada como `indeterminate` em vez de entregue. Lease trocado interrompe a espera do mesmo jeito,
com `termination` `replaced`, e o `supervise` sobre um diretório cujo lease já foi trocado recusa
começar (`conflict`, efeitos `none`, saída `3`) em vez de rodar a unidade sob prova adulterada. Um segundo supervisor sobre o mesmo diretório
encontra o lease ocupado e recusa com `conflict`, efeitos `none` e saída `3`, com o recibo compacto
em stdout como toda outra recusa — `supervise` é alcançável pela linha de comando, e um código de
saída sozinho seria parada silenciosa.

### Exemplo mínimo executável offline

Da raiz do pacote, com um diretório de estado fora dele:

```sh
state_dir=$(mktemp -d /tmp/tl-job.XXXXXX)
python3 scripts/tl_job.py start \
  --state-dir "$state_dir" \
  --unit demo-1 \
  --authorization "story:DEMO/authorization:local" \
  --cwd "$state_dir" \
  --timeout 60 \
  -- python3 -c 'import json,os;open(os.environ["TL_JOB_RESULT"],"w").write(json.dumps({"outcome":"ready_for_delivery","next_action":"revisar o diff","observable_usage":"unknown"}))'
python3 scripts/tl_job.py wait --state-dir "$state_dir" --unit demo-1 --timeout 120
```

O primeiro comando devolve o recibo inicial; o segundo bloqueia localmente e devolve o resultado
terminal já limitado. Nenhum dos dois acessa a rede. No Windows, use `python` no lugar de `python3`.
O supervisor exporta `TL_JOB_ID`, `TL_JOB_DIR` e `TL_JOB_RESULT` para o processo da unidade.

### Acoplar ao condutor existente

O supervisor não substitui o condutor do consumidor; ele envolve o comando que o condutor já estava
autorizado a executar:

```sh
python3 scripts/tl_job.py start \
  --state-dir "$consumer_state" \
  --unit T012-1 \
  --authorization "$authority_ref" \
  --cwd "$consumer_root" \
  --timeout 5400 \
  --result-file .tl-work/T012-1.json \
  -- <comando-do-condutor-já-autorizado>
```

O `<comando-do-condutor-já-autorizado>` continua sendo escolhido pelo condutor, com o harness,
modelo e effort que a classificação da fase resolveu. O supervisor não altera nenhum deles. Regras
do acoplamento:

- o `--state-dir` fica fora dos artefatos publicados e fora da raiz do pacote, e as árvores
  `<state-dir>/jobs/<unidade>` e `<state-dir>/anchors` são conferidas por resolução de links em
  todos os comandos, inclusive nos de leitura: se `jobs`, a unidade ou `anchors` já existir como
  link para fora, a chamada é recusada com `invalid_input` antes de criar, reivindicar, ler ou
  escrever qualquer coisa — a vinculação é publicada por criação do diretório quando ele falta, e
  sem essa conferência um link plantado antes do primeiro `start` receberia `<unidade>.json` fora
  do diretório de estado nomeado. Um link que permanece dentro da árvore continua válido;
- `--result-file` é relativo a `--cwd` e não escapa dele: além da checagem léxica, o caminho é
  resolvido e recusado quando um link já existente o leva para fora da árvore. Isso recusa o escape
  preexistente verificável; não elimina corrida de sistema de arquivos contra quem troque um
  componente depois da checagem, nem enxerga hard link;
- o `--result-file` precisa estar ausente quando a unidade começa. Nada no conteúdo do arquivo nomeia
  a execução que o escreveu, então um arquivo já presente poderia ser o sucesso de uma unidade
  anterior, herdado por um comando que sai 0 sem tocar em `TL_JOB_RESULT`. A ausência antes do spawn
  é o que prende o resultado admitido a esta execução: o que for lido depois apareceu enquanto ela
  rodava. Caminho que já existe — ou que nem pode ser inspecionado — é recusado antes do spawn, com
  `start_failed`, `effects: none` e sem `outcome`; a unidade não chega a rodar. A ausência é medida
  por `lstat`, que separa o nome inexistente (`FileNotFoundError`) de qualquer outro `OSError`:
  permissão negada, nome inválido ou erro de E/S não são ausência e também recusam, nomeando o
  motivo, porque um erro de inspeção não prova que o arquivo não está lá. Use um caminho novo por
  unidade, ou omita a opção e deixe o padrão dentro da árvore da própria unidade;
- a mesma unidade reaproveita a reivindicação; mudança no comando exige `unit` novo;
- o recibo entra no contexto do condutor; `stdout.log`, `stderr.log` e relatórios ficam no disco;
- o condutor só volta ao usuário por exceção material ou resultado terminal.

## Pipelining assíncrono com Git Worktrees e protocolo noturno

Para viabilizar execução autônoma prolongada (overnight) e eliminar o tempo ocioso de espera passiva por CI remoto, o protocolo estende o ciclo de entrega:

1. **Desacoplamento do CI Remoto (Pipelining de Worktrees):**
   - A fase de entrega (`phase_deliver`) conclui no momento em que os portões locais passam, o commit é realizado e o Pull Request é criado (`gh pr create`).
   - O condutor NÃO deve bloquear turnos ou pausar a sessão esperando de forma síncrona a conclusão do CI remoto (ex: 10 minutos de GitHub Actions).
   - O PR é publicado e entregue à Merge Queue serializada quando o merge for expressamente autorizado; a execução física de merge em `main` exige autorização humana explícita ou autorização prévia por `permitted_effects` do lote.
   - Imediatamente após a publicação do PR da Story N, a capacidade de desenvolvimento é liberada: se a Story N+1 for independente no grafo de dependências (DAG), ela é despachada imediatamente em um Git worktree isolado (`worktrees/<story-id>`), sobrepondo o tempo de CI de N ao tempo de planejamento/código de N+1.

2. **Heartbeat e Fencing de Leases:**
   - Leases de sessão e execução registram obrigatoriamente `{pid, start_time, heartbeat_ts}`.
   - Heartbeats são atualizados periodicamente pelo processo ativo. Se um processo morrer ou for encerrado abruptamente, a lease expirada (heartbeat ausente além do limiar de tolerância) é recuperada atomicamente, eliminando travamentos residuais de locks (`session.lock`) sem intervenção manual do usuário.

3. **Orçamento Estrito de Revisão e Estacionamento (`Parked`):**
   - O ciclo corretivo Maker ↔ Checker possui teto estrito de 2 rodadas. No 3º desacordo persistente, a story é marcada como `parked` com relatório circunstanciado (`report.md`), a lease é liberada e o condutor avança para a próxima story autorizada na fila, garantindo que a execução noturna nunca trave por uma story isolada.
   - **Detector de Oscilação de Diff:** Se o hash do diff produzido pelo Maker após uma correção for idêntico a qualquer estado anterior (ciclo oscilatório A → B → A), a story é imediatamente estacionada por ausência de progresso.

4. **Cache de Gates por Hash de Árvore (`tree_sha`):**
   - Resultados de portões locais obrigatórios são indexados pelo hash da árvore de arquivos (`tree_sha`). Quando um parecer do Checker ou uma conferência não alterar o conteúdo da árvore, a reexecução de gates idempotentes é recuperada do cache local instantaneamente.

## Execução Concorrente Multi-Story

O paralelismo real é permitido somente entre stories independentes no DAG e com escopos aceitos.
O estado de coordenação fica em disco, fora dos worktrees publicados, e cada transição é protegida
por lock exclusivo e publicada por substituição atômica. Os quatro mecanismos são:

1. **Worktree Pool:** `acquire_worktree_slot(pool_dir, story_id, max_slots)` concede no máximo
   `max_slots` worktrees ativos em `worktrees/<story-id>`. A concessão só existe depois da publicação
   de `slot.json`; pool cheio responde `pool_exhausted`, sem abrir outro worktree. Ao terminar,
   `release_worktree_slot` remove o worktree e libera a vaga.
2. **Scope Arbiter:** antes de abrir o worktree, `claim_scope(story_id, paths, claims_file)` compara
   `content_paths` sob o mesmo lock usado para publicar a reivindicação. Igualdade, ancestralidade
   ou descendência de qualquer path ativo responde `scope_conflict`. Estado ilegível ou gravação
   incerta falha fechado. `release_scope` ocorre somente depois que a story deixa de escrever.
3. **Merge Queue Serializada:** `enqueue_merge(story_id, pr_number, queue_file)` acrescenta o PR ao
   fim da fila FIFO persistida. Somente o item `pending` no topo pode executar `gh pr merge`; o
   avanço fica serializado e registra `merged` ou `failed`. Durante o runner, o topo fica `merging`
   com `started_at`; após 120 segundos sem estado terminal, a próxima chamada o recupera e tenta
   novamente. A persistência terminal tolera por até 30 segundos a contenção transitória do lock.
   Um topo `failed` bloqueia o seguinte até remoção explícita ou nova tentativa registrada, nunca
   equivale implicitamente a sucesso. A Merge Queue ordena merges já autorizados, mas nunca concede autoridade para merge em `main`: merge em `main` exige autorização humana explícita ou prévia por `permitted_effects` do lote.
4. **Varredura de órfãos:** `sweep_orphan_worktrees(pool_dir, stale_after_seconds)` compara o
   `heartbeat_ts` da lease de cada `slot.json` com um limiar operacional maior que a tolerância
   normal do heartbeat. Apenas leases que ultrapassam esse limiar são removidas com
   `git worktree remove --force`; slot atual ou estado ilegível não é removido otimisticamente.

Resultados de gates continuam indexados por `tree_sha` do worktree correspondente e nunca são
compartilhados entre stories com árvores diferentes. Escritas no board usam comparação e troca da
`state_revision`: divergência responde `state_revision_conflict` sem alterar `STATUS.md`.

### Relação entre Governança de Lote (T018) e Runtime Físico Concorrente (v0.11)

A arquitetura do método separa estritamente a camada de governança da camada de execução física:
**T018 decide se pode; v0.11 decide se dá.**

1. **Matriz de Responsabilidades:**
   - *Autorização humana e digest:* T018 exclusiva (`authorization.proposal_digest`, `permitted_effects`).
   - *Freeze de escopo:* T018 exclusiva (`frozen_scope`, `immutable_digest`).
   - *Admission semântico e orçamentos:* T018 exclusiva (write-ahead contábil de chamadas, saldo e reserva dinâmica mandatória).
   - *Alocação de worktrees:* v0.11 runtime físico (`acquire_worktree_slot`).
   - *Detecção de colisão de escopo:* v0.11 runtime físico (`claim_scope`). Em lote congelado, colisão é stop condition mandatória.
   - *Recuperação de leases e órfãos:* v0.11 runtime físico (`heartbeat_ts`, `sweep_orphan_worktrees`). Débito contábil conservador por T018 em caso de timeout.
   - *Serialização de merge:* v0.11 ordena na FIFO; T018 autoriza o efeito via `permitted_effects`.
   - *Escrita atômica do board:* T018 é a autoridade soberana de estado; v0.11 executa o CAS mecânico por `state_revision`.

2. **Serialidade Declarada do Lote (`batch_concurrency: 1`):**
   Dentro de um lote autorizado do Modo Automático, a execução de unidades é estritamente sequencial (`batch_concurrency: 1` no `frozen_scope`). O Modo Automático não despacha mais de uma unidade concorrente do mesmo lote. A concorrência multi-story de v0.11 permanece disponível para stories independentes fora do lote.

3. **Precedência sobre `parked`:**
   Dentro de um lote autorizado, a marcação de uma story como `parked` solta a lease mas **não autoriza o avanço** para unidades subsequentes caso a autorização humana fixe `continue_independent_after_block: false`. O lote suspende imediatamente a execução na unidade estacionada.

4. **Isolamento de `runtime_refs`:**
   Identificadores opacos de correlação com o runtime físico (`supervisor_state_dir`, `worktree_slot`, `scope_claim`, `merge_queue_entry`, `lease_heartbeat_ts`) residem exclusivamente no bloco mutável `execution.runtime_refs` do envelope `Bnnn.md`. O snapshot imutável `frozen_scope` (com `additionalProperties: false`) e seu `immutable_digest` nunca são contaminados por referências voláteis de runtime.

## Limites

O supervisor valida transporte, não mérito. Ele não faz lock distribuído, não certifica portões, não
agenda, não notifica fora da ativação e não faz chamada de modelo. Timeout, crash, resultado truncado
e efeitos incertos são reportados explicitamente como incertos, sem inferir sucesso.

A prova de fim é sobre o supervisor, não sobre o disco. Uma unidade que roda com o mesmo usuário
continua podendo escrever no diretório da unidade, inclusive depois que o supervisor sai; o que o
método promete é que nenhuma leitura terminal é aceita enquanto o supervisor daquela unidade estiver
provadamente vivo, e que o registro aceito tem a forma completa que só o `finalize` produz. Onde não
existe trava exclusiva de arquivo, não há prova possível: o recibo declara `termination:
"unsupported"` em vez de afirmar um fim que ninguém observou.

Essa prova vale por arquivo, não por nome. A unidade escreve no diretório e pode trocar o que está
atrás de `supervisor.lock`, mas não pode fazer o arquivo que o `start` criou deixar de ser aquele
arquivo: a reivindicação guarda dispositivo e inode dele, e um nome que passe a levar a outro arquivo
lê como `replaced`, não como fim. Onde a plataforma sequer permite a troca sob descritor aberto, o
ataque falha antes disso e o supervisor segue `alive`. Nos dois casos a resposta é a mesma para quem
pergunta: `wait` e `result` não entregam. Trocar o lease é, no máximo, negar a si mesma a entrega —
nunca forjá-la.

E o que a reivindicação afirma não é a última palavra, porque a unidade também escreve nela. Quem
troca o lease e reescreve o `lease_identity` no mesmo movimento faz a troca voltar a parecer
coerente; por isso a vinculação esperada mora fora do diretório da unidade, em
`<state-dir>/anchors/`, publicada uma vez e nunca sobrescrita. Reescrever a reivindicação passa a ser
`diverged`, apagar a vinculação passa a ser `unanchored`, e os dois recusam a entrega tanto no `wait`
quanto no `result`. O alcance disso é o da permissão do sistema de arquivos: a vinculação protege
contra a unidade que escreve no próprio diretório de job, não contra quem tenha escrita no diretório
de estado inteiro — esse pode reescrever a vinculação junto com o resto, e então só o token que o
`start` devolveu, guardado pelo condutor fora do disco e reapresentado em `--expect-binding`, recusa
a entrega. Essa recusa é o que o método promete ali; a vinculação no disco não substitui separar as
permissões do `--state-dir` da árvore que a unidade escreve.

Contra escritor sobrevivente, a defesa é contagem de processo, não assinatura do arquivo. Um
descendente que roda com o mesmo usuário lê tudo que o supervisor poderia persistir como segredo,
então um selo no `result.json` seria forjável junto com o resto; por isso a entrega depende de a
árvore estar prestada antes de o lease cair. O alcance disso é o da plataforma: Job Object no
Windows, `child subreaper` mais `/proc` no Linux. Em outro POSIX o resultado sai **indeterminado**,
mesmo quando nada escapou de fato — é recusa conservadora, não detecção. E, mesmo no Linux, o que a
contagem enxerga são os processos reparentados para este supervisor: descendente que saia para outro
namespace de PID, que troque de usuário ou que fique preso a um subreaper mais próximo que o
sobreviva não aparece nessa lista, e uma lista vazia significa "nada reparentado aqui", não "nada
sobreviveu no sistema". A promessa é a recusa onde a contagem não fecha, não a onisciência sobre a
árvore.

A contenção de caminhos — tanto a da árvore da unidade quanto a de `--result-file` — recusa o escape
por link que já existe no momento da checagem. Ela não promete imunidade a corrida adversarial de
sistema de arquivos, em que um componente é trocado depois da conferência e antes do uso, e não
enxerga hard link.

Nenhuma economia percentual de tokens é afirmada aqui. Os testes do pacote medem bytes admitidos e
número de consultas ao condutor em um cenário controlado; isso não é medição de tokens nem promessa
de custo, que depende do harness, do modelo e do cache em uso. Os demais limites operacionais do
método estão no [contrato do Orquestrador](../prompts/orchestrator.md#limites-operacionais).
