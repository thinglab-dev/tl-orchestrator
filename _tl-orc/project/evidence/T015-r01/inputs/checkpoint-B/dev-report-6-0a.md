# Dev Report 6.0a (Estado da Rodada 1 — Pré-Rework)

## Escopo entregue

O processo agora declara o perfil de subsistemas em `Config.Profile`:

- o valor vazio continua sendo `bling`, preservando as cinco instalações e as
  validações do perfil legado;
- `mkauth-control-plane` exige somente banco, tenant e uma conexão real de
  kind `mkauth`; não cria conexão fictícia, não monta Bling/Lytex/webhook/opsview
  e registra apenas o slot lifecycle `mkauth-control-plane`;
- o slot ainda não abre listener nem liga handler. Ele participa de
  `Run`/`Shutdown`/`InFlight` para que 6.0b--d possam conectar seus handlers
  sem alterar o lifecycle declarado nesta story.

`Compose`, `Set` e `validateSufficient` passaram a comparar as instalações
contra o conjunto nomeado pelo perfil. A composição Bling conserva ordem e
drenagem atuais. Os endereços dos dois listeners existentes são validados
antes de abrir banco/listener; endereço ausente, malformado ou `:8080` é
recusado. Material do webhook continua obrigatório somente quando aquela
superfície é declarada pelo perfil Bling.

## Critérios de aceite

| AC | Entrada/ação | Esperado | Observado |
| --- | --- | --- | --- |
| AC01 | `LYNVIA_PROFILE=mkauth-control-plane` sem variáveis Bling; perfil zero-value Bling | Bling opcional só no perfil MK-Auth; legado preservado | `ConfigFromEnv` aceitou MK-Auth sem Bling; os cinco testes de wiring do perfil legado passaram. |
| AC02 | `NewFromConfig` com conexão `mkauth` e `Serve` cancelado | Slot lifecycle inicia/drena sem handler ou listener | Exatamente `mkauth-control-plane` foi instalado e drenou limpo; nenhum slot Bling foi montado. |
| AC03 | Conexão `mkauth` real no tenant de teste e depois conexão de outro tenant | Sem conexão fictícia; isolamento tenant/conexão mantido | A composição aceita a conexão do tenant e recusa a de outro tenant como inexistente para o tenant configurado. |
| AC04 | Perfil Bling com `WebhookListenAddr=:8080` e banco inalcançável | Recusar configuração antes de bootstrap/listener | Retornou `endereço webhookd usa default de produção`, sem tentar abrir o banco. |

## Comandos e evidências

Todos os comandos foram executados em
`/Users/albertiano/thinglab/platform/modules/lynvia`, com fixtures sintéticas e
sem rede externa.

| Comando | Exit | Resultado |
| --- | ---: | --- |
| `make bmad-sync MODULE=lynvia` (raiz Platform) | 0 | Política BMAD sincronizada antes do trabalho. |
| `GOCACHE=/tmp/lynvia-gocache TEST_DATABASE_URL="postgres://lyn:lyn@127.0.0.1:55741/lyn?sslmode=disable" go test -v ./cmd/lynvia/internal/process/ -count=1` | 0 | 20 testes verdes; inclui PostgreSQL real, migrations, conexão MK-Auth e lifecycle. |
| `GOCACHE=/tmp/lynvia-gocache go build ./...` | 0 | Build do módulo verde. |
| `GOCACHE=/tmp/lynvia-gocache go vet ./...` | 0 | Vet do módulo verde. |
| `make check` | 2 | Vermelho preexistente e alheio em `internal/connectorgate`; ver limite abaixo. |
| `GOCACHE=/tmp/lynvia-gocache TEST_DATABASE_URL="postgres://lyn:lyn@127.0.0.1:55741/lyn?sslmode=disable" go test ./internal/connectorgate -count=1 -run '^TestEntrypointDoAgenteExecutaComoSubprocesso$'` | 1 | Reproduziu o vermelho conhecido: usage atual inclui `mariadb-bootstrap|recover|update-selfcheck|update-reconcile|admin`, divergindo do oráculo. |
| `git diff --check` | 0 | Sem erro de whitespace. |

## Sondas contrafactuais

As duas mutações ocorreram na árvore real, tiveram o resultado observado e
foram restauradas antes dos comandos verdes finais.

| Sonda | Mutação | Vermelho observado | Restauração |
| --- | --- | --- | --- |
| M1 / AC01 | Removida a exigência de `BlingConnection` em `normalizeConfig` | `TestNewFromConfigBlingProfileRequiresBlingConnection` exit 1: o erro mudou para `conexão bling configurada não existe`, em vez de recusar a configuração incompleta. | Condição integral restaurada; mesmo teste exit 0. |
| M2 / AC04 | Removidas as chamadas a `validateListenAddr` | `TestNewFromConfigRejectsProductionDefaultAddressBeforeOpeningDatabase` exit 1: a montagem tentou abrir o banco `127.0.0.1:1`, em vez de recusar o endereço. | Chamadas restauradas; a suíte final do pacote ficou verde. |

## Limites e pendências para revisão

- Não foram compostos registry, ingress, bridge ou fleet: continuam pertencendo
  às stories 6.0b--d. O slot MK-Auth não expõe endpoint, servidor, certificado
  ou handler nesta entrega; portanto não há listener implícito nem material de
  chave pública/privada correspondente a essa função ainda vazia.
- `make check` não está verde somente pelo vermelho conhecido de
  `TestEntrypointDoAgenteExecutaComoSubprocesso` em `internal/connectorgate`.
  Nenhum arquivo daquele pacote foi alterado.
- Alteração produtiva: quatro arquivos, +191/-49 linhas (líquido +142).
  Com testes, são seis arquivos de código, +299/-50 linhas (líquido +249);
  não houve arquivo produtivo novo, migração, DDL, dado real ou efeito externo.
