## Avaliação formal — T009 r07

### 1. Conferência de alvo, procedência e autorização

**Alvo:** `content_id: 0de10d60149cf7c038a0954c6aec302c9fcd111e:938ddfb319408b79` (HEAD + SHA-256 agregado dos 85 arquivos de `content_paths`, branch `analysis/t009-semantic-validation`) casa exatamente com o verificado pelo Checker no primeiro item `rejected` do veredito. `spec_revision: 4197dea48f75cd14` casa com o digest da seção `## Spec` (`4197dea48f75c...860eb`) lida via `read_section.py`. Os quatro digests do `resume.json` (`PROJECT.md#frontmatter`, `T009-r07.md#Review record`, `T009-r07.md#Verdict`, `task-T009-spec.md#Spec`) conferem integralmente com o conteúdo retornado — nenhum desvio de procedência.

**Autorização:** o veredito é `approved`, com `independence: distinta de toda autoria efetiva (Google, Anthropic)`, `restrição: required`. A spec fixa explicitamente no *Verification profile* o pin `gpt-6-astra/high` como `required` *especificamente para esta revisão* — ou seja, o Checker rodou dentro da autorização vigente por exceção nominal da própria spec, não por desvio de política geral de independência de família.

### 2. Limitação residual (procedência por conteúdo) vs. defeito bloqueante

**Limitação aceita, não bloqueante** — classe "procedência por conteúdo": o AC02 do veredito é explícito ao dizer que a consolidação normativa fica em T010 e que *"esta aprovação não declara resolvida a classe procedência"*. O que ficou comprovado (camada mecânica AC02/AC03, `T009-mechanical-check.py:233,562,596,635,644,679,749`) é: resolução de localização, registro literal de ID, comparação de conteúdo, ordem de cadeias e derivação de proxies. O que **não** ficou coberto (e é reconhecido como tal, não escondido): comparação de valores de pins/autoria, fontes genéricas para outros campos, roles exigidos da política em vez da solicitação. Isso é exatamente o tipo de limitação que a spec previu desde o desenho (proposta revisada em `20260907T210033Z`: *"esta Task avalia o ganho sem antecipar mudança de arquitetura"*) — está declarada, delimitada e encaminhada, não é uma lacuna descoberta a posteriori nem promessa de rastreabilidade total (essa promessa foi retirada, conforme o resultado da revisão registra).

**Achado que exige registro, mas não é bloqueante:** AC06 — `python3 scripts/validate_repository.py` retornou exit 1 por `'No usable temporary directory found'` neste sandbox (falha de ambiente na criação de `TemporaryDirectory`, não do código). O Checker mitigou executando as sub-rotinas (`load_manifest`, `validate_json`, `validate_frontmatter`, `validate_links`, `validate_readme_manifest`) individualmente — todas verdes — e comparou byte a byte os 17 arquivos distribuídos e o manifesto contra a base, sem divergência. Isso é evidência suficiente de que o alvo não quebra o portão de exportação; o que falhou foi a orquestração do subprocesso de diretório temporário no sandbox do Checker, não uma regressão introduzida pela Task. **Não constatei, nesta leitura, exportação integral verde real** — isso deve ficar registrado como pendência de verificação de ambiente, não como AC06 incumprido.

Não há, nas sete rejeições do Checker (uma por critério, incluindo a checagem de árvore/content_id), nenhum item que aponte fabricação de evidência, promessa não cumprida, regressão de r01–r06 ou critério obrigatório da spec deixado sem prova. Portanto **não há motivo para exigir rework**: `approved` aqui não está sendo tratado como passe livre automático — foi conferido item a item contra AC01–AC06 e contra o alvo declarado.

### 3. Encaminhamento proposto

**Fechamento de T009 com registro de limitação**, dentro da autorização vigente (spec + pin `gpt-6-astra/high required` + veredito `approved` do Checker r07), condicionado a:
- registrar explicitamente no fechamento a ressalva de AC06 sobre a indisponibilidade de `TemporaryDirectory` neste sandbox (ambiente, não código) e a mitigação por sub-rotinas individuais;
- confirmar que a classe "procedência por conteúdo" (pins/autoria/fontes genéricas/roles da política) permanece **explicitamente aberta** e é herdada como escopo de entrada de T010, não como débito oculto de T009.

Nenhum impedimento fundamentado se sustenta a partir do que foi lido — não há target/spec divergente, não há prova fabricada, não há critério obrigatório sem evidência.

### 4. Minuta de fechamento

```
## Closure — T009 r07
Status: closed (approved, com limitação registrada)
content_id: 0de10d60149cf7c038a0954c6aec302c9fcd111e:938ddfb319408b79
spec_revision: 4197dea48f75cd14
Checker: T009-r07-checker-1 (codex/gpt-6-astra, high) — approved; 0 action_items; 7 rejected (1 por critério, incl. conferência de árvore/content_id)

Decisão: fechar T009 nesta revisão. AC01–AC06 satisfeitos no nível fixado pela spec.

Limitação residual aceita (não bloqueante): classe "procedência por conteúdo"
(comparação de valores de pins/autoria, fontes genéricas de outros campos,
roles exigidos da política vs. solicitação) permanece fora da camada mecânica
comprovada nesta Task. Encaminhada explicitamente para consolidação normativa
em T010 — não é débito oculto de T009, é escopo declarado desde a proposta
revisada de 20260907T210033Z.

Ressalva registrada: AC06 — `scripts/validate_repository.py` falhou por
indisponibilidade de TemporaryDirectory neste sandbox (falha de ambiente,
não de código). Mitigado por execução individual das sub-rotinas
(load_manifest, validate_json, validate_frontmatter, validate_links,
validate_readme_manifest — todas verdes) e comparação byte a byte dos
17 arquivos distribuídos/manifesto contra a base (sem divergência).
Exportação integral verde real não foi observada nesta rodada; deve ser
reconfirmada em ambiente com TemporaryDirectory disponível antes de
qualquer decisão de distribuição (fora do escopo desta Task).

Nenhum rework exigido. Nenhum despacho de agente realizado (sessão read-only).
```

Isso é uma leitura, não uma ação — nenhum arquivo foi alterado e nenhum agente foi despachado nesta sessão, conforme o aviso restritivo.
