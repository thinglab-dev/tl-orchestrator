# Evolução segura do método

Este contrato rege duas capacidades independentes de uma instalação com perfil local:

- conferir ou aplicar uma atualização publicada do pacote instalado;
- encaminhar melhorias locais do próprio método ao repositório de origem.

Nenhuma delas é um daemon, engine, heartbeat ou serviço residente. Elas só podem ocorrer durante
uma ativação do Orquestrador, depois da leitura e validação do estado real. Classificador,
Searcher, Planner, Maker e Checker designados diretamente não conduzem este fluxo.

## Políticas independentes e autoridade

`INSTALLATION.md` pode declarar, além de `update_check`:

```text
update_policy: <notify ou auto_safe>
contribution_mode: <ask ou auto_pr>
```

`update_policy` controla o que fazer com uma release estável sucessora; `contribution_mode`
controla o que fazer com um delta local autorizado do pacote. Um campo não concede autoridade ao
outro. Quando ausentes em um perfil anterior, interprete-os como `notify` e `ask`, respectivamente;
registre a migração somente numa atualização autorizada. `update_check: disabled` continua
impedindo a consulta de atualização, mesmo com `update_policy: auto_safe`; não impede examinar
localmente um delta já presente.

`auto_safe` e `auto_pr` são preferências, não autoridade autossuficiente. Qualquer efeito de
escrita exige uma autorização expressa, vigente e verificável que identifique:

- projeto consumidor e ator autorizado;
- destinos exatos de instalação ou repositório upstream;
- escopo de arquivos e efeitos permitidos;
- procedência da autorização e sua última confirmação.

Um valor `auto_pr` isolado, texto inferido, permissão técnica, credencial disponível ou
autorização de outro projeto/ator/destino não basta. Campo ausente, procedência ambígua,
autorização revogada ou escopo insuficiente resulta em parada antes do efeito. O método não
configura GitHub, forks, credenciais, destinos ou serviços de terceiros para criar essa
autoridade.

## Ordem na ativação

1. Valide origem, referência, commits, políticas, autorização, instalações concorrentes e
   precedência sem executar os valores lidos.
2. Compare os arquivos instalados com a baseline identificada pelos hashes verificados em
   `INSTALLATION.md`. Classifique arquivos alterados, ausentes e adicionais antes de encerrar por
   divergência.
3. Se houver delta local do pacote, trate primeiro a seção [Contribuir melhorias](#contribuir-melhorias).
   Esse caminho é alcançável antes do retorno por hash divergente, mas a divergência continua
   impedindo `auto_safe` e impede atribuir à instalação os estados `atual` ou `atualização
   disponível`.
4. Somente sem bloqueio local, confira atualizações. `notify` relata o resultado. `auto_safe`
   segue seus portões estritos e, se algum falhar, regride para relato e decisão humana, nunca para
   sobrescrita.

Uma contribuição preparada ou publicada não remove o delta local, não valida os arquivos
instalados, não elimina conflito e não desbloqueia uma atualização. Alterações do consumidor fora
do pacote são distinguidas do delta do método e permanecem intocadas.

Uma atualização também separa sincronização de adoção operacional. `synchronized` prova somente
que pacote, registros e integrações vieram da revisão conferida. Quando a revisão muda roteamento
ou despacho, migre o perfil e as instruções consumidoras, faça fresh load da skill exata e execute
o smoke test limitado descrito no [guia](PROJECT_CONFIGURATION.md#migração-operacional-do-roteamento).
Somente essa evidência permite `operational_verified`; impossibilidade de testar fica
`operational_pending` e impede declarar adoção completa, sem desfazer uma sincronização válida.

## Contribuir melhorias

O delta é sempre calculado contra a baseline de origem cuja revisão e hashes foram verificados,
nunca contra uma cópia presumida limpa nem contra a futura release. Preserve o delta antes de
qualquer tentativa de atualização. Prepare-o fora do consumidor, em checkout fonte isolado da
origem canônica e em branch que não seja `main`; o projeto consumidor, `_tl-orc/config`, registros,
evidências, logs, credenciais e demais conteúdos privados nunca entram nesse checkout.

Use uma allowlist formada exclusivamente pelos caminhos do pacote publicados no
`distribution-manifest.json` da revisão fonte. Se uma revisão legada ainda não tiver o manifesto,
use exatamente os caminhos e hashes de `## Arquivos` cuja correspondência com a origem foi
comprovada; não infira a allowlist enumerando o diretório. Arquivo adicional, symlink inesperado,
origem não comprovada ou mudança fora da allowlist bloqueia. Antes de preservar, buscar duplicata ou publicar,
revise e sanitize tanto o conteúdo quanto os metadados: remova ou generalize segredos, dados
pessoais ou de cliente, URLs e nomes privados, caminhos locais, logs, autores indevidos e contexto
que não seja necessário para reproduzir ou explicar a mudança. Na dúvida sobre privacidade,
propriedade ou licença, pare para decisão humana.

Uma falha suspeita pode produzir somente evidência local sanitizada. Corrigir defeito exige
reprodução clara e escopo delimitado; uma feature nova exige intenção específica e previamente
aprovada. `auto_pr` nunca autoriza desenvolvimento arbitrário a partir de uma suspeita, sugestão
ou oportunidade inferida.

Com `contribution_mode: ask`, apresente o delta sanitizado e o plano, sem efeitos Git externos.
Com `contribution_mode: auto_pr` e autoridade completa para o projeto, ator, destino, escopo,
commit, push e criação de draft PR, o Orquestrador pode conduzir, nesta ordem:

1. conferir a baseline e preparar a mudança no checkout isolado;
2. executar os portões aplicáveis e obter Checker externo independente;
3. buscar issue, branch ou pull request equivalente no destino autorizado com termos sanitizados;
4. se não houver duplicata impeditiva, criar commit, enviar uma branch dedicada e abrir **draft
   pull request**, registrando cada efeito.

Se já existir trabalho equivalente, relate e não crie duplicata. Não modifique contribuição de
terceiro, não comente ou altere status sem autoridade específica e não reabra automaticamente uma
contribuição rejeitada ou fechada. Sem permissão comprovada de push, de usar o fork explicitamente
autorizado ou de criar o draft PR, pare; não crie nem configure um fork por conta própria. Nunca
faça merge automático.

O corpo do draft PR descreve baseline, problema ou intenção aprovada, mudança, provas, limites,
compatibilidade e sanitização. Não use palavras de fechamento automático de issue sem autoridade
específica. Publicar o PR não altera a instalação do consumidor.

## Atualização `auto_safe`

`auto_safe` considera somente uma GitHub Release que seja estável (não draft e não prerelease),
tenha tag resolvida para commit válido e cujo commit seja comprovadamente descendente do commit
instalado. Um avanço de `update_ref` sem release estável correspondente pode ser relatado, mas
nunca aplicado automaticamente.

Antes de escrever, todos estes portões devem passar:

- os arquivos atuais coincidem byte a byte com a baseline e seus hashes; não há arquivo ausente,
  adicional, delta local, symlink inesperado ou conteúdo fora do manifesto;
- o plano não toca `_tl-orc/project/`: os documentos de trabalho do
  [modelo nativo](WORK_MODEL.md) nunca são sobrescritos, excluídos ou migrados por uma
  atualização, embora possam ser lidos, validados, versionados e copiados para backup;
- o `SKILL.md` carregado, todas as cópias/links registrados, revisões e precedência foram
  conferidos, sem sombreamento, destino desconhecido ou conflito;
- a origem alvo foi obtida separadamente, todos os arquivos pertencem ao mesmo commit, o manifesto
  e os hashes de origem e cópia foram conferidos e nenhum conteúdo remoto foi executado;
- o plano identifica migrações operacionais e os estados `synchronized` e
  `operational_verified|operational_pending` que deverão ser registrados por harness;
- todas as release notes do intervalo foram lidas em ordem e não há migração, decisão pendente,
  mudança de garantia, política, permissão, preferência ou integração que exija escolha humana;
- existe autorização expressa e vigente para exatamente esse projeto, ator, destinos, escopo e
  fluxo de atualização.

Antes da mutação, crie um snapshot recuperável dos arquivos do pacote, registros e destinos que
serão alterados; registre base, hashes, local do snapshot e procedimento de recuperação, e prove
que o snapshot pode ser lido. Os registros sujeitos à mutação são `INSTALLATION.md`, `PROJECT.md`
e as integrações registradas; `_tl-orc/project/` fica fora da mutação e da recuperação por
snapshot, e nenhuma atualização o cria. Maker aplica uma única revisão, o Orquestrador repete a conferência
de arquivos, hashes, links, precedência e descoberta, e um Checker externo independente revisa a
árvore final. Se a mutação ou um portão posterior falhar, pare, preserve evidência e use o
snapshot para recuperar o estado anterior somente dentro da autoridade registrada; confira a
recuperação. Depois da cópia, conclua a migração e a prova operacional do guia. Falha de capacidade
deixa `operational_pending`, não sucesso inventado; falha da mutação recupera o snapshot. Não
continue uma mutação parcial nem apague o snapshot antes do aceite.

Qualquer delta, arquivo extra, conflito, migração pendente ou garantia alterada transforma a
operação em `notify`: apresente release, bloqueio e decisão necessária. Não afrouxe um portão,
não sobrescreva o delta e não trate a abertura de PR como resolução do conflito.

## Release do repositório

No repositório fonte, contribuições passam por revisão e CI. Uma release exige aprovação do
maintainer, CI verde e entrada correspondente no `CHANGELOG.md`; somente o maintainer autorizado
cria tag e GitHub Release. O projeto não fornece workflow de release com permissão de escrita.
