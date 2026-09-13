## Achados (leitura das fontes congeladas, sem alteração de disco)

**1. Integridade dos artefatos** — Recalculei os SHA-256 de `PROJECT.md`, `checker-dw-6-0a-01-r1.md`, `deferred-work.md` e `release_test.diff` e conferi contra `manifest.json`/`reference_manifest.json`/`resume.json`: todos batem byte a byte. Não há adulteração de conteúdo no pacote — o desvio abaixo é de **processo/autorização**, não de integridade de dados. Observação lateral: `release_test.diff` está **vazio** (0 bytes) — o pacote não contém a correção real do item ainda aberto.

**2. Colisão de identificador em `deferred-work.md`** — o arquivo tem *dois* itens sob o mesmo ID `DW-6.0A-01`:
- um já **riscado/RESOLVIDO** em 2026-09-08 (troca do literal por prefixo estável), com revisão externa própria já registrada ali mesmo;
- outro ainda **aberto**, sobre o oráculo desatualizado de `release_test.go:243` que precisa refletir a lista completa de subcomandos (`install|uninstall|mariadb-bootstrap|recover|update-selfcheck|update-reconcile|admin`), bloqueando `make check` do módulo `lynvia`.

O parecer `checker-dw-6-0a-01-r1.md` avalia especificamente a mudança de **prefixo** em `release_test.go:242` — ou seja, cobre o item **já resolvido**, não a condição de quitação do item **ainda aberto**. Isso já seria motivo de recusa por escopo, independente do problema de candidato abaixo.

**3. Candidato do Checker r1 é não autorizado — por dois critérios independentes:**
- **Catálogo geral do papel Checker** (tabela "Catálogo permitido", presente tanto no `_tl-orc/PROJECT.md` do método quanto refletido no PROJECT.md do consumidor): para harness Agy, Checker exige `gemini-3.1-pro-high` em effort `high`. `gemini-3.8-flash-medium`/`medium` **não consta** como par Checker em catálogo algum — está reservado a Classificador/Searcher. Regra explícita: *"Pares fora do catálogo são inválidos e devem ser rejeitados."*
- **Pin fixado pelo usuário em 2026-09-07** (seção "Escolhas fixadas pelo usuário", PROJECT.md do consumidor, que *"prevalece sobre o perfil"*): para este consumidor, Checker report-only deve ser **família Claude** (`sonnet` ou `claude-opus-5`, efforts medium/high), escolhido pelo Classificador, com a única restrição de família independente dos Makers efetivos (Agy Gemini e Codex GPT). Agy, por definição, não é família Claude — o pin foi descumprido mesmo abstraindo a questão de independência.

`resume.json` registra `effective_authors: ["openai"]` (Orquestrador deste consumidor atua na família OpenAI/GPT). Mesmo sob a lente de independência (`checker_independence: preferred`), Agy seria família distinta do autor — mas isso não supre a exigência mais específica do pin, que fixa Claude como família do Checker neste consumidor, sobrepondo-se ao raciocínio geral de independência.

**Conclusão formal:** o parecer `approved` de r1 não é uma **aprovação regular** — é uma **aprovação por candidato não autorizado** (fora do catálogo do papel Checker e em descumprimento do pin específico do consumidor), agravada por um desalinhamento de escopo (revisa o item já fechado, não o item pendente). O parecer deve ser **preservado como registro do desvio**, não descartado nem tratado como satisfazendo o portão de revisão externa do DW-6.0A-01 ainda aberto.

---

## Proposta de regularização (não executada — apenas proposta, modo somente leitura)

1. **Preservar** `checker-dw-6-0a-01-r1.md` integralmente no lugar, anotando no item aberto de `deferred-work.md` (via edição futura, fora deste modo) que r1 é inválido para fins de quitação: candidato fora de catálogo/pin e escopo divergente do item pendente.
2. **Resolver a duplicidade de ID** antes de qualquer nova revisão: renomear/anexar sufixo distinto (`DW-6.0A-01b`, por exemplo) ao item ainda aberto para eliminar a colisão de identificador em `deferred-work.md`.
3. **Obter o diff real** da correção do oráculo (lista completa de subcommands) — `release_test.diff` está vazio no checkpoint; sem ele não há objeto a revisar.
4. **Nova classificação em sessão auxiliar limpa**, com o Classificador restrito a emitir candidatos Checker apenas dentro do catálogo válido para o papel (effort `high`; famílias autorizadas) e respeitando o pin deste consumidor (família Claude).
5. **Nova revisão (r2)** despachada em sessão nova por candidato registrado e autorizado: Checker Claude (`sonnet` ou `claude-opus-5`, effort `high`, conforme o pin), cobrindo o diff real do item ainda aberto.
6. **Registrar a pendência** em `review_followups` do cabeçalho global do consumidor, citando r1 como parecer preservado (evidência do desvio), não como revisão válida.

---

## Briefing estruturado para a nova classificação/revisão

| Campo | Valor |
| :--- | :--- |
| Unidade | `DW-6.0A-01` (item **aberto** — oráculo de `release_test.go:243` desatualizado quanto à lista de subcomandos; distinguir do item já resolvido sob o mesmo ID) |
| Fase | `review` (pendente de diff real; classificação deve preceder despacho) |
| Diff a revisar | Ainda não fornecido — `release_test.diff` no pacote está vazio; é pré-requisito coletar a correção real antes do despacho |
| Condição de quitação (do próprio item) | Literal esperado em `release_test.go` atualizado para a usage real do CLI (ou oráculo derivado da flag, não hardcoded), com prova de que o teste ainda discrimina regressão de usage |
| Autoria efetiva | `openai` (Orquestrador/Codex GPT neste consumidor) — registrar family real do autor da correção quando o diff existir |
| Catálogo aplicável (Checker) | Pin do consumidor (2026-09-07): família **Claude**, `sonnet` ou `claude-opus-5`, effort medium/high, escolhido pelo Classificador; independência exigida apenas de Makers efetivos (Agy Gemini, Codex GPT) |
| Candidato descartado | Agy `gemini-3.8-flash-medium` — fora do catálogo do papel Checker (exige `gemini-3.1-pro-high`/`high` nesse harness) **e** fora do pin de família deste consumidor |
| Parecer r1 | Preservar como registro do desvio; não usar como base de aprovação do item aberto — escopo do parecer corresponde ao item já resolvido, não ao pendente |
| Ação recomendada | Desambiguar ID → coletar diff real → reclassificar (candidatos Checker restritos ao catálogo/pin) → despachar Checker Claude em sessão nova → só então avaliar quitação |

Nenhum arquivo foi alterado e nenhum agente foi despachado nesta sessão, conforme o aviso restritivo.
