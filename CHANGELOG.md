# Changelog

Todas as mudanças relevantes deste projeto serão documentadas aqui.

## [Unreleased]

## [0.8.0] - 2026-09-12

### Adicionado

- Protocolo de execução (`docs/EXECUTION_PROTOCOL.md`): envelope da unidade de execução, lista
  fechada do resultado devolvido, contexto separado por papel, retomada por checkpoint limitado
  validado contra a árvore e a cadeia Maker → portões → Checker → correção limitada → prova →
  entrega no condutor do consumidor. O condutor volta ao usuário por exceção material ou resultado
  terminal, não por turnos de progresso.
- Supervisor opcional de biblioteca padrão (`scripts/tl_job.py`) para despachar uma unidade **já
  autorizada** sem conversa de acompanhamento: `start` desacoplado (Windows sem janela e POSIX),
  `wait` local sem chamada de modelo, `status` que não lê logs e `result` limitado por lista de
  campos permitidos e teto de bytes. Ele apenas transporta: não escolhe modelo ou effort, não
  inventa comando, não certifica portões e não aprova entrega; seu exit zero não fecha uma unidade.
  A identidade da unidade é reivindicada uma vez — repetir o mesmo despacho reaproveita o resultado
  e um manifesto divergente é recusado em vez de reexecutar.
- Contenção da árvore do job no fim do prazo: em Windows, o filho nasce suspenso e só roda depois de
  atribuído a um Job Object com `KILL_ON_JOB_CLOSE`; em POSIX, ele lidera sessão/grupo próprios e o
  grupo recebe `SIGTERM`, carência e `SIGKILL` antes de o filho direto ser colhido, para nunca
  sinalizar um PID reciclado. Só a árvore deste despacho é tocada, nunca um processo localizado por
  nome. Falha de contenção antes da execução bloqueia o spawn; depois de efeitos já ocorridos o
  recibo declara `effects: uncertain`, e o campo `containment` informa o mecanismo realmente usado.
- Varredura não provada é indeterminada por definição: `containment.swept: "unproven"` — nenhuma
  árvore provada encerrada, mesmo sem erro registrado — passa a classificar o resultado como
  `effects: uncertain` com saída `5`, ainda que a unidade tenha saído com código zero e payload
  admitido. Só `job_object` e `process_group` contam como alcance provado. A opção escolhida foi
  classificar em vez de recusar antes de executar: o despacho acontece, o resultado é entregue ao
  condutor e fica marcado como indeterminado, porque recusar apagaria um resultado que talvez seja
  útil enquanto o que não se pode afirmar é apenas o fim da árvore.
- Reentrada do supervisor com limite refeito: o subcomando interno `supervise` recebe `--state-dir`
  e `--unit` em vez de um diretório de job arbitrário (`--job-dir` foi removido da linha de comando).
  Ele reaplica a verificação do diretório de estado e a derivação do diretório da unidade — link
  recusado por `realpath`, job obrigatoriamente contido na árvore de estado — e valida o manifesto
  inteiro antes de qualquer leitura ou execução: lista fechada de campos, tipos, schema, `unit`
  coincidente e caminhos dentro dos limites. Divergência responde `invalid_input` com efeitos `none`,
  sem executar argv e sem criar log fora da árvore.
- Falha interna do supervisor não deixa mais a unidade sem resposta: a árvore é encerrada pela mesma
  contenção em `finally`, o estado terminal sai como `crashed` com `effects: uncertain` quando a
  unidade pode ter rodado (nunca rebaixado a `none`), disco que impede gravar `result.json` responde
  saída `5` sem inventar arquivo, e a liveness do supervisor é provada por um lease exclusivo do
  sistema operacional — nunca por PID — de modo que `wait` devolve `indeterminate` ao encontrar
  supervisor encerrado sem resultado, em vez de esperar o prazo inteiro.
- Testes de comportamento offline (`tests/test_tl_job.py`) e portão de testes no workflow de
  validação: stdout grande fora do recibo, start concorrente executando a unidade uma única vez,
  fingerprint divergente recusado, Unicode e limites, timeout, comando inexistente, processo com
  falha, payload inválido, retomada sem duplicar efeito, caminhos inválidos e gravação final
  atômica. Inclui um ensaio sintético que compara bytes admitidos e número de consultas ao
  condutor; é ilustração de admissão, não medição de tokens. Inclui um caso com neto real que segue
  escrevendo depois do prazo: ele falha sem a contenção e passa com ela. O workflow de validação roda
  a suíte em Linux, exercitando o ramo POSIX dessa contenção.
- Casos dirigidos das duas regras acima: um líder POSIX que deixa neto vivo com batimento em arquivo
  e sai com zero (ramo de grupo de processo, exercitado pelo Linux do workflow e pulado no Windows)
  prova `swept: "unproven"` lido como `uncertain`/`5`; e a fronteira do `supervise` prova recusa com
  diretório de job alcançado por link, diretório de estado arbitrário, manifesto com campo extra, de
  outro schema, de outra unidade e com arquivo de resultado fora das árvores — cada recusa conferida
  junto com a ausência de argv executado e de log criado, e acompanhada do controle positivo em que
  a reivindicação real no próprio diretório continua rodando.

### Alterado

- Janela de publicação da reivindicação deixa de recusar `start` concorrente legítimo: no Windows o
  nome recém-criado por `os.replace` pode negar a abertura por um instante, e essa recusa era lida
  como reivindicação ilegível, devolvendo `invalid_input` a quem deveria reaproveitar a unidade já
  em curso. Agora só a recusa de abertura sobre um nome que acabou de inspecionar bem é repetida,
  dentro de um orçamento fixo de um segundo aberto uma única vez por chamada; passado o orçamento,
  volta a mesma recusa `invalid_input` com o motivo original. Reivindicação estável ilegível — JSON
  inválido, não UTF-8, acima do teto, não objeto — e nome que sequer pode ser inspecionado seguem
  recusados de imediato, sem orçamento algum.
- Manifesto passa a 19 arquivos distribuídos, incluindo `docs/EXECUTION_PROTOCOL.md` e
  `scripts/tl_job.py`. O método continua utilizável sem Python, com os limites de automação
  declarados; o supervisor é opcional e exige apenas Python 3 já presente no ambiente.
- Afirmações sobre custo e cache no playbook passam a explicitar dependência do harness, do modelo
  e do cache em uso: as observações registradas são pontuais de um consumidor e não são taxa
  transferível. Nenhuma economia percentual de tokens é prometida sem medição no ambiente real.
- Reaproveitamento de portões e suítes: um resultado vale somente para a mesma revisão da árvore e
  a mesma definição do portão; falha exige primeiro o caso dirigido e só depois a suíte inteira.
- Fila sequencial considera apenas candidatas da allowlist autorizada pelo board declarado;
  ampliar a lista é decisão do usuário.
- `scripts/validate_repository.py` compara os caminhos exportados em forma POSIX, para que a
  validação estrutural produza o mesmo resultado em Windows e em Linux.
- A unidade padrão de topo passa a ser a story inteira (`<story>-<rodada>`) com sua cadeia
  autorizada; os recibos de Maker, portões e Checker ficam internos ao condutor. Job por papel
  (`<story>-<papel>-<rodada>`) vira opcional e quebrar a story em microjobs não autoriza turnos de
  acompanhamento. O limite real — encadear papéis exige condutor adaptado, ou vale uma unidade por
  vez — passa a ser declarado em vez de prometido.
- A leitura linha a linha do diff integral passa a ser atribuída ao Checker em todos os contratos
  (orquestrador, playbook, Maker, Checker). O condutor confere identidade e revisão, cobertura de
  caminhos e critérios, portões na árvore final, destino de cada achado aberto e uma amostra crítica
  dirigida, despachando um verificador quando quiser sondagem independente; o parecer integral não
  volta ao contexto dele. Aprovação continua exigindo prova real.
- Papel designado com spec ratificada não reabre onboarding, triagem de tarefa, planejamento nem
  Classificador do fluxo pai: a ativação passa direto ao trabalho, conforme a autoridade do
  consumidor. O bypass é de ativação, não de regra — portões, limites de escrita e revisão
  independente continuam valendo.
- `observable_usage` passa a significar consumo observado, em uma string curta: medida realmente
  observada, referência ao lugar onde a métrica existe, ou `unknown`. Número inventado, `0` de
  preenchimento e instrução de como conferir o resultado deixam de caber ali; o supervisor não
  coleta tokens, custo nem uso do harness.
- `--result-file` passa a ser recusado quando um link já existente dentro do diretório de trabalho
  resolve para fora dele: a checagem léxica anterior aceitava uma grafia contida que escrevia em
  outra árvore. O caminho aceito continua sendo o léxico, de modo que a identidade da unidade não
  muda. Isso recusa o escape preexistente verificável; não elimina corrida de sistema de arquivos
  contra quem troque um componente depois da checagem, nem enxerga hard link.
- O arquivo de resultado passa a precisar estar ausente quando a unidade começa, e é isso que prende
  o payload admitido à execução: nada no conteúdo do arquivo nomeia quem o escreveu, então um
  `--result-file` reutilizado deixava uma unidade nova sair com zero sem tocar em `TL_JOB_RESULT` e
  herdar o `delivered`/`ready_for_delivery` de uma anterior. Caminho que já existe — ou que nem pode
  ser inspecionado — é recusado antes do spawn, com `start_failed`, `effects: none`, sem `outcome` e
  sem argv executado; o que for lido depois disso apareceu enquanto esta unidade rodava. A
  alternativa de emitir um token de identidade no spawn foi descartada por exigir que o condutor o
  devolvesse no payload, mudando o contrato do papel sem ganho de garantia.
- A árvore da unidade (`<state-dir>/jobs` e `<state-dir>/jobs/<unidade>`) passa a ser conferida por
  resolução de links, e não só por normalização léxica, em **todos** os comandos — inclusive os de
  leitura (`status`, `wait`, `result`). Um diretório de estado válido cujo `jobs`, ou cuja unidade,
  já exista como link para fora é recusado com `invalid_input` antes de qualquer `mkdir`,
  reivindicação, leitura ou escrita, de modo que nenhum manifesto, status ou log é criado fora. O
  caminho devolvido continua sendo o léxico, e um link que permanece dentro da árvore segue
  funcionando sem perder idempotência. Isso recusa o escape preexistente verificável; não promete
  imunidade a corrida adversarial de sistema de arquivos que troque um componente depois da
  checagem.
- `<state-dir>/anchors` entra na mesma conferência por resolução de links da árvore da unidade, e
  pelo mesmo motivo: a vinculação mora ao lado de `jobs` e é publicada por criação do diretório
  quando ele falta, então um link plantado ali antes do primeiro `start` era adotado e recebia
  `<unidade>.json` fora do diretório de estado que o chamador nomeou. A conferência acontece na
  derivação do diretório do job, isto é, antes de qualquer `mkdir`, lease, manifesto ou vinculação, e
  em todos os comandos, inclusive os de leitura: o escape é recusado com `invalid_input`,
  `effects: none` e saída `2`, sem vinculação externa, sem reivindicação e sem argv executado. Um
  link de `anchors` que permanece dentro da árvore de estado continua funcionando. Vale aqui o mesmo
  limite: isso recusa o escape preexistente verificável, não corrida que troque um componente depois
  da checagem, e não enxerga hard link.
- `wait` valida `--timeout` antes do laço, como `start`: zero, negativo, não numérico, infinito,
  `NaN` ou acima do limite viram `invalid_input` de imediato, em vez de virar espera inútil ou
  retorno imediato disfarçado de prazo.
- O recibo bem-sucedido de `start` e `status` fica em identidade, estado e localizadores.
  `effects`, `authorization_fingerprint` e `manifest_fingerprint` saem dele: as impressões
  permanecem no manifesto privado e no confronto de identidade, e `effects` continua onde há motivo
  observável a declarar — resultado terminal, erro, conflito e `wait_timeout`.
- Unidade terminada nunca é reaberta: `supervise` recusa com `conflict` e `effects: none` quando já
  existe `result.json`, antes de reivindicar o lease e de executar argv. A checagem é a existência
  do arquivo terminal, não seu conteúdo, então resultado corrompido ou truncado também recusa a
  segunda execução, e nada no disco é tocado na recusa.
- Validação do manifesto passa a ser a mesma para todos os leitores: `load_claim` aplica o gate
  central usado por `supervise` em reentrada de `start`, `status`, `wait` e `result`. Manifesto
  ausente, com lista de campos divergente, tipo inválido ou impressão não computável responde
  `JobError` compacto em JSON, nunca traceback, sem reaproveitar resultado e sem executar.
- Campo lido do disco passa a ser validado e limitado antes de virar recibo: localizadores são
  cortados por bytes, estado gravado fora da lista fechada vira `unknown`, e `enforce_ceiling`
  respeita `--max-bytes` inclusive ao reduzir aos campos centrais, caindo para um recibo mínimo
  marcado como `clipped` em vez de estourar o teto. Estado ou caminho grande no disco não vaza para
  a saída.
- Sucesso terminal passa a exigir fim comprovado do supervisor, e não apenas um `result.json`
  presente. O diretório da unidade fica ao alcance dela e todo campo do registro terminal é
  recomputável a partir do `manifest.json`, então uma unidade podia plantar um resultado válido e
  seguir escrevendo enquanto `wait` e `result` já a davam por entregue. Agora `wait` só encerra o
  laço com o arquivo terminal **e** o supervisor daquela unidade fora da trava exclusiva, e `result`
  responde `indeterminate` com efeitos `uncertain` e saída `5` enquanto ele estiver vivo. Sem prova
  possível — plataforma sem trava exclusiva ou lease inexistente — o recibo declara `termination`
  (`unsupported`, `unproven`) em vez de afirmar um fim que ninguém observou.
- O registro terminal aceito passa a precisar da forma completa que o supervisor sempre grava
  (`schema`, `job_id`, `unit`, `state`, `effects`, `exit_code`, `started_at`, `finished_at`,
  `logs`, `containment`, `result_status` e as duas impressões). Um registro montado por outro
  escritor, mesmo com as impressões corretas, é indeterminado em vez de virar entrega da unidade.
- Prova de fim indisponível deixa de entregar resultado terminal. Plataforma sem trava exclusiva de
  arquivo respondia `termination: unsupported` e ainda assim podia devolver um registro plantado
  como entregue, com efeitos `known` e saída `0`. Agora `wait`, `result` e o relatório interno só
  entregam com prova `proven`; `unsupported` e `unproven` recusam com estado `indeterminate`,
  efeitos `uncertain`, saída `5` e o campo `termination` dizendo qual fim não pôde ser provado.
- Manifesto presente e ilegível deixa de ser tratado como reivindicação concorrente incompleta.
  JSON inválido, texto que não é UTF-8, conteúdo acima do teto de bytes ou raiz que não é objeto
  são recusados de imediato como `invalid_input`, efeitos `none` e saída `2`, sem esperar a janela
  de reivindicação e sem traceback, igual para `start` em reentrada, `status`, `wait` e `result`.
  Só o manifesto ausente continua sendo esperado como reivindicação que ainda pode chegar.
- `supervise` sobre um lease ocupado passa a emitir o recibo compacto de `conflict` em stdout, com
  efeitos `none`, além da saída `3`. O caminho é alcançável pela linha de comando e respondia antes
  com código de saída nu, uma parada silenciosa para quem lê o recibo.
- Registro terminal sem prestação de contas completa sobre a árvore deixa de ser entrega. Faltando
  `containment`, a leitura da varredura respondia como se nada tivesse escapado e o recibo saía com
  efeitos `known` e saída `0`. Agora o registro precisa de contenção completa e tipada (`kind`,
  `established`, `unit_ran`, mais `swept` quando a árvore foi estabelecida) e do par exato de
  referências de log (`stdout` e `stderr`); qualquer registro parcial é `indeterminate` com efeitos
  `uncertain` e saída `5`. Ausência de campo nunca é lida como prova de que não houve sobrevivente.
- Reivindicação que não pode nem ser inspecionada deixa de ser tratada como ausente. Falha de `stat`
  no `manifest.json` por permissão ou erro de E/S virava espera pela janela de reivindicação e
  depois `conflict`, culpando uma concorrência que não existia. Só `FileNotFoundError` continua
  sendo ausência esperada; qualquer outro erro de sistema responde `invalid_input`, efeitos `none` e
  saída `2` de imediato, nomeando o motivo pelo qual o arquivo não pôde ser inspecionado.
- Varrer a árvore deixa de bastar para entregar: agora o supervisor presta contas dos descendentes
  que escaparam do alcance varrido, antes de soltar o lease. Um descendente que chamasse `setsid()`
  sobrevivia à varredura do grupo, esperava o lease cair e substituía o `result.json` por um registro
  completo e coerente — indistinguível, pelo conteúdo, da escrita da própria unidade, porque todo
  campo dele é recomputável a partir do `manifest.json`. No Linux o supervisor passa a se declarar
  `child subreaper` antes de a unidade existir, guarda a lista de filhos anterior a ela e, ao final,
  encerra e colhe o que foi reparentado para si; no Windows o Job Object já responde por isso e a
  saída antecipada (`breakaway`) nunca é concedida. O `containment` do registro ganha `accounted`
  (`job_object`, `subreaper_scan`, `unaccounted`) e `account_failed`; contas que não fecham fazem o
  resultado ser lido como `indeterminate`, efeitos `uncertain` e saída `5`, mesmo com fim provado e
  payload admitido. Fora do Linux, a contenção POSIX responde `unaccounted` por princípio: recusa
  conservadora, não detecção — e a lista vazia significa "nada reparentado aqui", não "nada
  sobreviveu no sistema". A defesa é contagem de processo, não selo no arquivo, porque um
  descendente do mesmo usuário leria qualquer segredo que o supervisor persistisse.
- Arquivo de resultado que não pode ser inspecionado passa a recusar de fato antes do spawn. A
  checagem usava `os.path.lexists`, que responde falso tanto para nome inexistente quanto para
  permissão negada ou erro de E/S, então a unidade rodava com o resultado não ligado à execução —
  justamente o contrário do que o método declarava. Agora a inspeção é por `lstat`: só
  `FileNotFoundError` é ausência, e qualquer outro `OSError` recusa com `start_failed`, efeitos
  `none`, sem `outcome` e sem argv executado, nomeando o motivo.
- `--max-bytes` inválido passa a caber no recibo. Declarado como `type=int`, o argparse saía com seu
  próprio despejo de uso antes de `main` chegar ao tratamento de erro, então um valor como `nope`
  devolvia texto ilimitado em stderr e nenhum JSON — furando a única promessa de tamanho que o recibo
  oferece, na opção que define esse tamanho. O valor passa a ser lido como texto e validado dentro da
  fronteira, como o `--timeout` de `wait`: não inteiro responde `invalid_input`, efeitos `none`, saída
  `2` e recibo recortado pelo teto padrão, antes de reivindicar diretório ou executar argv; número
  abaixo do mínimo continua sendo elevado ao mínimo.
- A prova de fim passa a ser ligada ao arquivo do lease, não ao nome dele. A unidade escreve no
  próprio diretório e podia pôr outro arquivo — sem trava alguma — atrás de `supervisor.lock`: a
  liveness respondia `gone`, a prova saía `proven` e um registro terminal forjado era entregue com
  efeitos `known` e saída `0` enquanto o supervisor continuava vivo e a unidade seguia escrevendo.
  Agora o `start` cria o arquivo do lease antes de tudo e grava na reivindicação o `lease_identity`
  (dispositivo e inode dele); todo leitor compara a identidade do descritor que abriu com a
  registrada e responde `replaced` quando o nome leva a outro arquivo — `wait` e `result` recusam
  com `indeterminate`, efeitos `uncertain`, saída `5` e `termination: "replaced"`, e `supervise`
  sobre um lease já trocado recusa com `conflict` sem executar argv. Reivindicação cujo
  `lease_identity` não descreve arquivo algum responde `unbound` e nunca `proven`; valor corrompido
  é recusado como `invalid_input`. O campo fica fora da impressão digital do manifesto, então a
  reutilização idempotente do `start` não muda. Onde a plataforma recusa a troca sob descritor
  aberto, o ataque falha antes disso e o supervisor segue `alive`; nos dois casos não há entrega.
- A vinculação esperada entre lease e reivindicação passa a ser publicada fora do diretório que a
  unidade escreve. Ligar a prova ao arquivo do lease não bastava, porque o `lease_identity` mora no
  `manifest.json`: uma unidade viva podia trocar o `supervisor.lock` e reescrever a reivindicação
  apontando para o arquivo plantado, e o leitor voltava a achar tudo coerente, entregando um
  registro terminal forjado com efeitos `known` e saída `0` enquanto ela seguia escrevendo. Agora o
  `start` cria `<state-dir>/anchors/<unidade>.json` com `O_EXCL`, antes da reivindicação, guardando
  unidade, `lease_identity`, as duas impressões e um token derivado desses campos — recomputado por
  todo leitor, nunca acreditado. `wait` e `result` confrontam a reivindicação com essa vinculação
  antes de entregar: reivindicação contraditória responde `diverged`, vinculação ausente ou ilegível
  responde `unanchored`, e as duas recusam com `indeterminate`, efeitos `uncertain`, saída `5` e o
  `termination` correspondente, mesmo com `result.json` completo no disco. `supervise` recusa com
  `conflict` o diretório cuja vinculação não responde por ele, o reaproveitamento do `start` só é
  oferecido enquanto o estado for `bound`, e vinculação existente nunca é sobrescrita — um `start`
  sobre diretório de unidade apagado recusa com `conflict` em vez de emitir vinculação nova. O
  recibo de `start` devolve o token em `binding`, e `wait` e `result` aceitam `--expect-binding`,
  conferido pela forma (dezesseis hexadecimais minúsculos, `invalid_input` e saída `2` fora dela)
  antes de qualquer diretório ser procurado; token bem formado de outra execução recusa a entrega
  como `diverged`. O alcance declarado é a permissão do sistema de arquivos: a vinculação protege
  contra quem escreve no diretório da unidade, e contra quem escreve no diretório de estado inteiro
  só o token guardado fora do disco recusa.

### Migração

- A exportação e a instalação passam a criar também o subdiretório `scripts/`. Um perfil instalado
  com 17 arquivos continua consistente consigo mesmo; ao atualizar, copie os 19 caminhos do
  manifesto de uma única revisão e regrave `INSTALLATION.md` com 19 hashes. Pacote com 17 arquivos
  conferidos contra um manifesto de 19 bloqueia a instalação, como qualquer divergência.
- Nenhuma ação é necessária para continuar usando o método sem o supervisor: ele é opcional e não
  é chamado por nenhum contrato existente. Quem quiser acoplá-lo segue o [protocolo de
  execução](docs/EXECUTION_PROTOCOL.md#acoplar-ao-condutor-existente); não há serviço, dependência
  ou credencial nova.
- Nenhuma promoção automática de `operational_verified` decorre desta versão: o smoke test
  operacional continua sendo prova separada do consumidor.

## [0.7.1] - 2026-09-11

### Adicionado

- Regra de admissão de saída de ferramenta: em sessão longa a quantidade de requisições pesa tanto
  quanto o recorte de um despejo isolado, porque cada ida e volta reenvia todo o contexto já
  admitido; agrupar chamadas de ferramenta independentes entre si na mesma requisição reduz turnos
  sem soltar o recorte já exigido do que é admitido no contexto.

## [0.7.0] - 2026-09-10

### Alterado

- Ordem padrão do Classificador: Agy Gemini 3.8 Flash medium → Codex Luna medium → Claude Sonnet
  medium, preservando os pares, a validação e as regras de fallback e de precedência local.
  As demais referências à cadeia remetem ao perfil publicado, e referências legadas à ordem do
  Classificador e ao Searcher no `README.md` e em `docs/PROJECT_CONFIGURATION.md` foram tratadas
  como harmonização documental de uma regra existente de inclusão do papel no schema e aos papéis
  da fase.

### Adicionado

- Próximos passos numerados no fechamento ou na devolução de uma decisão ao usuário, com ação e
  limites explícitos. Resposta numérica seleciona somente a opção do último menu válido, sem
  autorizações implícitas, execução por silêncio ou pausas adicionais em lotes já autorizados.

- Campos opcionais do registro conceitual de medição: `call_id` (dedup de registros repetidos da
  mesma chamada identificada, preservando chamadas distintas, retries e tentativas interrompidas),
  `usage_source`, `cache_io`, `machine_scope` (chave tipada estável entre versões, ausência não
  implica zero) e `capability_detection`; nenhum passa a obrigatório e nenhum registro anterior
  deixa de ser conforme.
- Parada honesta com checkpoint em disco ao atingir limite de rodadas/turnos sem concluir (playbook
  e contrato do Maker), complementando a regra existente de não repetir indefinidamente até obter
  verde; não é sucesso e não dispara novo loop automático.
- Critério do Checker para revisar registros de medição (conferir os cinco campos opcionais definidos
  em configuração de projeto quando presentes, como dedup por `call_id` de registros da mesma chamada,
  `usage_source`, `cache_io`, `machine_scope` e `capability_detection`, lendo qualquer campo ausente como
  desconhecido e não como desconformidade) e para tratar parada honesta com checkpoint como pendência,
  não aprovação implícita.
- Regra de admissão de saída de ferramenta no playbook, com reflexo nos contratos do Maker e do
  Searcher: o custo de uma leitura é seu tamanho multiplicado por quantas requisições ela
  sobrevive no contexto, então a decisão que importa é o que deixar entrar, não o que remover
  depois — remoção posterior no meio do histórico invalida o prefixo de cache dali para frente e
  cobra reescrita. Saída volumosa fica em artefato e o contexto recebe localizador com resumo,
  preferindo a forma de ferramenta que devolve localizador em vez de conteúdo; o recorte é sobre o
  que permanece no contexto, não sobre o que se verifica, e conferência do diff inteiro, leitura de
  fonte para prova crítica e revisão independente continuam exigidas. Saída não preservada é limite
  explícito, nunca recorte silencioso.
- Diretrizes de reuso condicionado de leituras na mesma sessão (com exceções para mudança de fonte,
  revisão, contexto, compactação, truncamento ou exigência contratual) e distinção operacional entre
  Searcher (levantamento factual) e Planner (arquitetura e especificação), preservando a leitura
  direta proporcional e a classificação com pin como restrição.

## [0.6.0] - 2026-09-08

### Corrigido

- Regras de condução do método para convergência, confinamento e limites probatórios: escalonamento
  consultivo após N rodadas de rework (padrão 3, configurável no perfil do consumidor) com achados
  centrais da mesma classe, classificando fase consultiva (`debate`) para diagnosticar
  manifestações do mesmo problema versus requisitos a consolidar antes de novo retrabalho; tabela
  normativa de procedência por tipo de informação e conteúdo que sustenta o valor no briefing
  (`story_id`, fase e papéis solicitados da solicitação ou spec com valor literal; catálogo, pins e
  cadeias de fontes de política conforme a precedência vigente — instrução atual do usuário
  registrada, configuração do consumidor em `PROJECT.md` ou perfil publicado na ausência de
  configuração local —, legitimando catálogo montado para a chamada quando cada entrada tem
  procedência verificável e rejeitando a entrada sem procedência, preservando projetos sem perfil
  persistido; autoria efetiva e famílias do registro de `Agent runs` efetivo; evidências de custo e
  capacidade de `docs/MODEL_ROUTING.md`; medição local com ID na primeira coluna; julgamento
  vinculado por hash com veredito explícito), fixando que localização que resolve não basta e
  rejeitando fonte incompatível com o tipo ou com o valor, além de rejeitar listas compostas na hora
  sem procedência por entrada ou fontes genéricas como "um arquivo existente", com entrega ao
  Classificador apenas de IDs com origem; limite declarado das provas mecânicas, em que conferência
  mecânica e vinculação por hash comprovam correspondência e integridade, não correção ou
  pertinência ao workload, mantendo adequação e alcance econômico como julgamento registrado; escopo
  de leitura dos papéis confinado à raiz consumidora e à raiz do pacote informadas, exigindo
  autorização explícita no briefing para qualquer outra fonte e declaração obrigatória de desvio no
  parecer ou relatório; Searcher classificado sob demanda recebendo modelo e effort da
  classificação da fase (papel auxiliar `searcher`, com a mesma estrutura dos demais papéis e tier
  que dimensiona a consulta) ou de pin explícito passado como restrição, cobrindo as buscas daquela
  fase sem reclassificar a cada consulta, cadeia por omissão do Searcher (Agy → Claude → Codex) no
  perfil publicado, e tornando explícito que a única exceção de inicialização com perfil fixo é a do
  próprio Classificador; admissão aditiva da propriedade opcional `searcher` em `roles` no schema de
  resultado de classificação (versão 2 mantida); e contrato do Classificador que passa a admitir o
  papel searcher com tier de consulta. Motivado pela análise em T009 e pela condução com retrabalhos
  sucessivos e leitura fora da raiz sem autorização.

### Alterado

- Compatibilidade unidirecional do schema de resultado de classificação — objetos com os papéis
  anteriores continuam válidos no schema desta revisão; objetos com `roles.searcher` são rejeitados
  por schemas anteriores; `schema_version` permanece 2 e a revisão efetiva do contrato e do schema é
  identificada pela release, prevista como menor (v0.6.0) por capacidade nova de classificação;
  consumidores devem atualizar o pacote antes de classificar com o papel searcher.

## [0.5.0] - 2026-09-07

### Adicionado

- Revisão posterior por outra família e registro `Agent runs`: sob `checker_independence: preferred`,
  revisão concluída com mesma família por indisponibilidade comprovada abre pendência no bloco
  `## RF-<unit_id>-rNN` na evidência da unidade, visível no cabeçalho global em `review_followups`,
  permitindo conclusão da Task sem flexibilizar `required`; identidade completa de unidade em quatro
  formas compatível com projetos com e sem módulos em Native e BMAD; ciclo de vida de pendências com
  estados `pending`, `superseded` (com substituta vinculada e mapeamento obrigatório de garantias em
  `reason`) e `closed` (somente por parecer aprovado de família distinta cobrindo o mesmo alvo);
  revisão posterior separada de autorização para novas alterações; menu de ativação com opção de
  revisão por outra família baseada em elegibilidade no catálogo; comprovação de disponibilidade
  pela chamada normal autorizada; e tabela uniforme `Agent runs` com identificador sequencial único
  por unidade, preservando tentativas descartadas e chamadas falhas.

## [0.4.1] - 2026-09-07

### Corrigido

- O contrato do Orquestrador, os perfis e o SKILL.md tornam explícito que o Orquestrador nunca
  escolhe modelo ou effort de Planner, Maker ou Checker por conta própria ou por sugestão: classifica
  em toda fase antes do primeiro despacho de cada papel; preferência de harness ou família é
  restrição de entrada do Classificador; só um modelo nomeado explicitamente pelo usuário ou pelo
  consumidor vira pin, e mesmo assim o Classificador é chamado. Motivado por uma condução em que o
  Checker foi fixado por suposição antes de classificar.

## [0.4.0] - 2026-09-06

### Adicionado

- Áreas de trabalho opcionais: projetos sem módulos continuam o modo padrão, com tudo em
  `_tl-orc/project/`; repositórios por módulo cadastram áreas em `## Work Areas` de `PROJECT.md`,
  com caminho documental completo por área, validação de duplicidade, sobreposição e conflito com
  a instalação, e `work_method` herdado do global para trabalho novo. Coordenação de escrita
  continua uma só por árvore, no `STATUS.md` global, que aponta a unidade corrente mesmo em módulo;
  `STATUS.md` de módulo guarda progresso local, e `## Areas` no global é projeção. Referências
  qualificadas `<area_id>:<id>` entre áreas, pertencimento (`deliverable`) distinto de procedência
  (`origin`), detecção de ciclos, registro de revisão vinculado à unidade qualificada, briefs na
  área responsável pela feature.
- Migration Findings: durante Import Context e Migrate Work, bugs confirmados e suspeitas
  encontrados na análise viram Tasks Native `fix` ou `analysis` em `draft` na fila da área
  responsável, com evidência mínima, deduplicação contra as fontes autoritativas, autoridade BMAD
  preservada, sem habilitar fila nem promover a `ready` sem spec, e bloqueio só da unidade cuja
  conclusão esteja impedida.

### Alterado

- SKILL.md: a opção **Atualizar tl-orchestrator** só entra no menu com release estável sucessora
  comprovada, alinhando a triagem à cláusula "sem oferecer alvo".
- Classificação: `story_id` aceita ID qualificado no modo multiárea; validação e reuso comparam a
  forma canônica, classificações anteriores são normalizadas apenas pelo próprio briefing de
  origem, e dois formatos nunca permitem reuso entre áreas. Schema inalterado.
- Contrato de evolução protege também os caminhos das áreas cadastradas, distinguindo snapshot de
  recuperação da atualização de backup documental.

### Migração

- Sem `## Work Areas`, nada muda: formatos de v0.3.0 continuam aceitos e produzidos, filas
  existentes preservam `scope`, `board` e permissões, e a atualização não reescreve documentos nem
  `QUEUE.md`. Cadastrar áreas é ato explícito do consumidor.

## [0.3.0] - 2026-09-06

### Adicionado

- Perfil **Native** em `docs/WORK_MODEL.md`: hierarquia `Project → Deliverable → Task` com
  Tasks standalone, tipos que sugerem a verificação inicial sem decidir modelo, effort ou método,
  documentos de trabalho em `_tl-orc/project/`, estado oficial em cada Task com `STATUS.md`
  derivado e cabeçalho de coordenação cooperativa presente também em projetos BMAD, recuperação
  sem confirmação humana para desatualizações esperadas, identificação verificável do conteúdo
  revisado (`content_id`) separada dos registros de controle, IDs sequenciais com recuperação
  serial e bloqueio em colisão real, conclusão de Deliverable por critérios de integração.
- Operação **Import Context**: `context/INDEX.md`, Feature Briefs por feature com estados
  `current`, `stale` e `retired`, separação entre `planned`, `implemented` e `confirmed`, registro
  `imports/IMPnnn.md` com correspondência bidirecional, regra de carregamento seletivo e
  envelhecimento sem gravação em ativação somente leitura. **Migrate Work** fica definido apenas
  como interface.
- Modo **Discuss** no menu de ativação, distinto de **Debater**: conversa sem despacho nem
  classificação.
- `PROJECT.md` aceita `work_method` e `task_types`; `QUEUE.md` aceita `permit_state_update` e
  `max_replans`, com `STATUS.md` como board no perfil Native.
- Manifesto passa a 17 arquivos distribuídos.

### Alterado

- O contrato do Planner exige prova conforme o perfil de verificação: sonda contrafactual
  obrigatória sempre que a garantia for comportamentalmente discriminável, qualquer que seja o
  tipo; verificação por fontes, premissas ou inspeção nos demais tipos. As provas comportamentais
  exigidas pelas garantias existentes são preservadas.
- O Checker recebe `spec_revision`, `content_id` e `content_paths`, confere nas fontes as
  afirmações de Feature Briefs relevantes à revisão e tem seu parecer preservado no registro de
  revisão fora do schema, que permanece na versão 1.
- O contrato de evolução exclui `_tl-orc/project/` de snapshot, mutação e migração de
  atualizações, inclusive `auto_safe`.

### Migração

- `story_id` continua o nome do campo no schema de classificação, versão 2, e aceita IDs de Task
  ou Deliverable do perfil Native; a transição para `work_id` fica planejada para uma versão 3.
- Perfis sem `work_method` preservam suas fontes e autoridade; a atualização não cria
  `_tl-orc/project/` nem migra unidades existentes.
- `INSTALLATION.md` passa a registrar 17 hashes.

### Corrigido

- O contrato do Planner exige sonda contrafactual, tarefas e estado auditado específicos por
  story, e prova de que o consumidor executa o plano com as próprias ferramentas (dependências
  no arquivo e formato que o engine lê; efeito retroativo de declarações novas sobre itens
  concluídos). Motivado por uma rodada em que 17 specs saíram com a mesma sonda de template e um
  grafo de dependências que o engine consumidor ignorava.

## [0.2.2] - 2026-09-05

### Corrigido

- Destaca, antes da triagem, uma release estável sucessora comprovada como atualização explícita,
  com alvo, notas, impacto conhecido e numeração dinâmica do menu, sem transformar `notify` em
  escrita nem substituir uma tarefa já solicitada.

## [0.2.1] - 2026-09-05

### Manutenção

- Registra a rotina de fechamento do repositório fonte com publicação de release após
  revisão e validação, sem ampliar permissões de contribuições de consumidores.

### Corrigido

- Atualizações que sincronizam arquivos agora também exigem migração do perfil e das integrações,
  fresh load e smoke test de roteamento antes de declarar adoção operacional completa.
- O Debater bloqueia todo despacho até validar a classificação `debate` de Planner, Maker e Checker,
  com pares modelo/effort explícitos; pins continuam restrições sem dispensar o Classificador.
- Evidências distinguem conteúdo `synchronized` de `operational_verified` ou
  `operational_pending`, sem transformar indisponibilidade em sucesso.

## [0.2.0] - 2026-09-05

### Adicionado

- Classificador de fase com schema v2, escolha de modelo e effort por harness, evidências de
  roteamento e fallback validado.
- Searcher somente leitura, sob demanda e fora do schema de classificação.
- Políticas independentes `update_policy: notify|auto_safe` e
  `contribution_mode: ask|auto_pr`, com autoridade por projeto, ator, destino, escopo e
  procedência.
- Fluxo opt-in para preparar e publicar draft pull requests sanitizados antes de uma atualização,
  sem merge automático nem alteração do consumidor.
- Atualização automática conservadora somente para release estável descendente, com portões de
  integridade, snapshot, recuperação, prova do Orquestrador e Checker independente.
- Manifesto explícito dos 16 arquivos distribuídos e CI documental do repositório.

### Migração

- Perfis anteriores que omitem `update_policy` e `contribution_mode` mantêm o comportamento
  conservador: `notify` e `ask`.
- `update_check: enabled|disabled` continua controlando se a consulta remota de atualização pode
  ocorrer; ele não concede autoridade de escrita.
- A release pública v0.1.5 tem 11 arquivos distribuídos. A atualização para 0.2.0 adiciona
  `prompts/classifier.md`, `prompts/searcher.md`, `schemas/classification-result.schema.json`,
  `docs/MODEL_ROUTING.md` e `docs/EVOLUTION.md`, atualiza o manifesto e exige novos hashes para os
  16 arquivos.

[0.2.1]: https://github.com/thinglab-dev/tl-orchestrator/compare/v0.2.0...v0.2.1
[0.2.2]: https://github.com/thinglab-dev/tl-orchestrator/compare/v0.2.1...v0.2.2
[0.3.0]: https://github.com/thinglab-dev/tl-orchestrator/compare/v0.2.2...v0.3.0
[0.4.0]: https://github.com/thinglab-dev/tl-orchestrator/compare/v0.3.0...v0.4.0
[0.2.0]: https://github.com/thinglab-dev/tl-orchestrator/compare/v0.1.5...v0.2.0
