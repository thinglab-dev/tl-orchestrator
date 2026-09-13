## Avaliação formal — T009, veredito Checker r07

### 1. Verificação de proveniência (digests)

| Seletor | Digest resume.json | Digest recomputado | Status |
|---|---|---|---|
| `task-T009-spec.md` § Spec | `4197dea48f75cd14…` | `4197dea48f75cd14e7a32802e642ef2bf3bdcc3b7530ef4fdfa6439c0db860eb` | ✅ compatível (prefixo = `spec_revision` declarado) |
| `T009-r07.md` § Review record | `5834d19c…` | `5834d19c77565cea7238092a97c95a385a61533220531b7a012df2e01e8b0dac` | ✅ íntegro |
| `T009-r07.md` § Verdict (JSON) | `306dd8bf…` | `306dd8bf5acaf8506e94b6b4a36f2be859888e2fbee75a81d14d0f0d10f7aeea` | ✅ íntegro |
| `PROJECT.md` frontmatter | `170fd6b537da99729aeae4fe4276e15678da354227b93fa64396e174af6fdf77` | `a9a09ac034db46e2f78f20456336f70105c794f282d426c971e9b1fe2c90a5eb` | ❌ **NÃO bate** |

**Achado bloqueante de processo (não do mérito de T009):** o digest do `resolved_context.project.constraints` em `resume.json` não confere com o valor recomputado agora para a mesma seção do mesmo arquivo. Isso não pode ser silenciosamente aceito — é exatamente o tipo de falha de verificabilidade que T015 foi desenhada para capturar. Para não bloquear a decisão de T009 nesse detalhe do manifesto de retomada, fiz verificação compensatória lendo o arquivo `PROJECT.md` por inteiro (não apenas a seleção indicada), o que me permite avaliar o mérito com segurança. Mas **o `resume.json` deste checkpoint precisa ser corrigido/regenerado antes de ser reutilizado** como fonte confiável de leitura seletiva em sessões futuras — isso é um impedimento pontual ao processo de handoff, distinto do impedimento ao fechamento de T009.

### 2. Autoria efetiva vs. independência do Checker

Ponto central exigido pela tarefa. O `resume.json` traz `"effective_authors": ["anthropic", "google", "openai"]` no nível da sessão — **esse campo é mais amplo do que a "autoria efetiva do conteúdo revisado"** definida em `PROJECT.md` ("identifique todas as famílias que produziram o conteúdo revisado, incluindo reworks, experimentos comparativos e correções próprias do Orquestrador").

Na tabela `Agent runs` de `T009-r07.md`:

| role | harness/model | família | função |
|---|---|---|---|
| orchestrator (correção própria) | claude/claude-fable-5-1 | Anthropic | **produziu conteúdo** (rework r07) |
| classifier | codex/gpt-5.6-luna | OpenAI | roteamento — não produz conteúdo revisado |
| checker | codex/gpt-6-astra | OpenAI | revisão — o próprio avaliador |

O `openai` que aparece em `effective_authors` do `resume.json` corresponde ao **Classificador** e ao próprio **Checker** desta rodada — papéis que não autoram o conteúdo sob revisão — e não a nenhum Maker/rework histórico. A citação do próprio Checker r07 ("`independence: distinta de toda autoria efetiva (Google, Anthropic)`") é consistente com essa leitura mais estrita e correta da política.

Conclusão: **a independência está satisfeita**. A restrição `required` do piloto (seção "Piloto de avaliação do Astra como Checker" em `PROJECT.md`, que sobrepõe a política geral `preferred`) foi honrada — Codex/`gpt-6-astra` (OpenAI) é distinto das famílias que efetivamente produziram o conteúdo (Google e Anthropic, conforme histórico de reworks r01–r07). Conflar ingenuamente o campo `effective_authors` do `resume.json` com a autoria de conteúdo teria gerado um falso positivo de violação de independência — o que eu rejeito explicitamente aqui após conferência cruzada com a tabela `Agent runs` e a definição normativa de `PROJECT.md`.

### 3. Alvo, content_id e critérios

- `content_id` citado pelo Checker (`938ddfb3…`) e `spec_revision` (`4197dea48f75cd14`) foram conferidos contra HEAD/branch declarados; consistentes com o `spec_revision` do `resume.json`. Não recomputei independentemente o hash agregado dos 85 arquivos de `content_paths` (fora do escopo desta rodada de verificação e sem script dedicado disponível); isso é aceitável dado que a classe "procedência por conteúdo" já é a limitação residual explicitamente reconhecida e encaminhada a T010 — não é um item que eu deva reabrir aqui.
- Os 7 itens do veredito (alvo/content_id + AC01–AC06) estão todos em `rejected` com citação por critério (caminhos, linhas, execuções reproduzidas), 0 `action_items`, 0 `deferred` — formato report-only íntegro conforme o schema e o perfil de verificação da spec.
- A limitação "procedência por conteúdo" (AC02) é tratada corretamente como **residual aceito**, não como defeito bloqueante: a spec já a previa como fora do alcance mecânico desta Task e a encaminha normativamente a T010; o Checker confirma ausência de regressão nas contraprovas de r01–r06 e não declara essa classe resolvida — apenas delimitada.

### 4. Encaminhamento proposto

**Fechamento com registro de limitação**, dentro da autorização vigente:

> T009 é fechada no nível fixado pela spec (`spec_revision 4197dea48f75cd14`), com veredito `approved` do Checker r07 (`gpt-6-astra`/OpenAI, independência distinta da autoria efetiva Google/Anthropic, restrição `required` do piloto honrada). A limitação residual da classe "procedência por conteúdo" (valores de pins/autoria não comparados, fontes genéricas, roles exigidos pela política em vez da solicitação) permanece explicitamente **não resolvida** e é formalmente encaminhada para consolidação normativa em T010, sem reabrir rework em T009.
>
> **Impedimento pontual e separado, não bloqueante para T009:** o `resume.json` deste checkpoint (`T015-r01`) contém um digest divergente para a seção `frontmatter` de `PROJECT.md` (`170fd6b5…` declarado vs. `a9a09ac0…` recomputado). Esse manifesto de retomada precisa ser corrigido/regenerado antes de servir como fonte confiável de leitura seletiva em sessões futuras — recomendo abrir isso como achado de manutenção do processo T015, não como bloqueio ao fechamento de T009.

Nenhum arquivo foi alterado e nenhum agente foi despachado nesta sessão, conforme o aviso restritivo.
