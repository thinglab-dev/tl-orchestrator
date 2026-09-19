format_version: 1
work_method: native

## Fontes autoritativas

| Tipo | Localização | Uso | Última conferência |
| :--- | :--- | :--- | :--- |
| Instruções do repositório fonte | `AGENTS.md`, `CONTRIBUTING.md` | política de contribuição e fechamento | 2026-09-07 |
| Contratos do método | `SKILL.md`, `prompts/`, `docs/`, `schemas/` | o próprio pacote, editado neste repositório | 2026-09-07 |

## Portões

| Portão | Diretório | Origem/condição |
| :--- | :--- | :--- |
| `python3 scripts/validate_repository.py` | raiz | CI do repositório |

## Modelo de trabalho

Este é o repositório fonte do método; não há instalação em `_tl-orc/package`. A área `global` em
`_tl-orc/project/` registra trabalho Native sobre o próprio método (achados, análises e correções),
conforme `docs/WORK_MODEL.md`. `_tl-orc/` aqui não é conteúdo de consumidor.

## Evidências

`_tl-orc/project/evidence/`.

## Perfil de despacho

routing_mode: classifier
checker_independence: required

Na ausência de catálogo persistido aqui, o contrato já permitia aplicar o perfil publicado após
conferir as capacidades do harness e montar o catálogo permitido para a classificação. Esta seção
persiste esse catálogo e as preferências operacionais deste repositório (parecer favorável do
maintainer em 2026-09-07). Descoberta (a CLI conhece
o modelo), permissão (o par consta abaixo) e acesso (observado na chamada autorizada e registrado
em `Agent runs`) são coisas diferentes; nenhuma delas prova a outra.

### Cadeias (preferência operacional; fallbacks autorizados preservados)

| Papel | Cadeia |
| :--- | :--- |
| Classificador | Agy → Codex → Claude (perfil fixo publicado) |
| Planner local | Codex → Claude → Agy; no modo remoto preferido, ChatGPT+RDC assume o planejamento |
| Maker | Codex → Agy → Claude |
| Checker report-only | Claude → Agy → Codex, sempre filtrada por checker_independence e autoria efetiva |

Autoria efetiva: identifique todas as famílias que produziram o conteúdo revisado, incluindo
reworks, experimentos comparativos e correções substantivas do Orquestrador. Neste repositório,
`checker_independence: required` é a preferência do maintainer: Checker da mesma família de qualquer
autor efetivo é inelegível, sem fallback degradado. Quota esgotada torna apenas aquele candidato
indisponível; não reduz a exigência de independência nem autoriza rebaixar a qualidade da revisão.

### Preferência do maintainer — ChatGPT + RDC

Quando houver acesso ao ChatGPT com Remote Desktop Commander e o preflight local confirmar
`command -v codex` e `codex --version` com sucesso, a condução preferida é:

- **Orchestrator + Planner:** ChatGPT + RDC;
- **Maker/Rework:** Codex;
- **Checker:** Claude quando elegível e disponível; Agy/Gemini é o fallback independente preferido;
- **Claude sem quota:** não trocar o Maker para Gemini se isso consumir a única família disponível
  para Checker; manter Codex como Maker e promover Gemini a Checker;
- **modo local:** permanece disponível por escolha do maintainer ou quando o preflight remoto falhar.

Operações mecânicas do ChatGPT/RDC — Git, worktrees, leitura, testes, CI, GitHub, processos e
montagem de contexto — não constituem autoria material. Planejamento, spec, decisão arquitetural ou
patch substantivo produzido pelo ChatGPT contam como família OpenAI. Como Codex também é OpenAI,
o fluxo remoto normal mantém um único lado de produção (`openai`) e reserva uma família distinta
para verificação. Se rework de outra família for incorporado, o Checker deve ser recalculado contra
o conjunto completo de autores antes da próxima revisão.

### Preferência de integração do maintainer

Para mudanças produzidas pelo próprio maintainer neste repositório fonte, PR não é requisito
operacional por si só. Após gates aplicáveis, Checker independente quando exigido, CI no SHA exato e
respeito às proteções do GitHub, a preferência é integração **owner-direct** e release direta em
`main`. Use PR quando houver contribuição externa, necessidade deliberada de discussão/review,
branch protection que o exija ou mudança ampla/arriscada em que o PR agregue valor. Esta preferência
não autoriza contornar branch protection, Checker, CI, escopo congelado ou autoridade do usuário.

### Catálogo permitido (pares modelo/effort)

| Papel | Harness | Modelo | Efforts permitidos | Observação |
| :--- | :--- | :--- | :--- | :--- |
| Classificador | Codex | `gpt-5.6-luna` | medium | perfil fixo |
| Classificador | Claude | `sonnet` | medium | perfil fixo |
| Classificador | Agy | `gemini-3.8-flash-medium` | medium (no ID) | perfil fixo |
| Planner | Claude | `sonnet` | medium, high | |
| Planner | Claude | `claude-opus-5` | high | |
| Planner | Codex | `gpt-5.6-terra` | medium, high | |
| Planner | Agy | `gemini-3.1-pro-high` | high (no ID) | |
| Maker | Agy | `gemini-3.8-flash-high` | high (no ID) | preferência global padrão |
| Maker | Codex | `gpt-5.6-terra` | medium, high, xhigh | |
| Maker | Claude | `sonnet` | medium, high | |
| Maker | Claude | `claude-opus-5` | high | |
| Checker | Codex | `gpt-5.6-terra` | high | referência padrão prioritária |
| Checker | Codex | `gpt-5.6-terra` | xhigh | escalonamento sob tier heavy / risco elevado |
| Checker | Codex | `gpt-6-astra` | high | candidato experimental do piloto sob avaliação |
| Checker | Codex | `gpt-6-astra` | xhigh | condicional: exige justificativa específica do Classificador |
| Checker | Claude | `sonnet` | high | |
| Checker | Claude | `claude-opus-5` | high | |
| Checker | Agy | `gemini-3.1-pro-high` | high (no ID) | |
| Searcher | Agy | `gemini-3.8-flash-medium` | medium (no ID) | sob demanda |

`max` e `ultra` não constam; aparecer na CLI não autoriza. Pares fora do catálogo são inválidos e
devem ser rejeitados. `null`/`null` é permitido somente quando não houver candidato autorizado e
adequado naquele harness para o papel solicitado; nunca como normalização de uma escolha inválida.

### Piloto de avaliação do Astra como Checker

- Avaliação experimental: candidato de referência padrão do harness Codex para Checker é
  `gpt-5.6-terra/high`. `gpt-6-astra/high` permanece como candidato experimental classificável no
  catálogo para medição comparativa de desempenho, latência e consumo, sem pin rígido obrigatório
  que sobreponha a cadeia padrão `Codex → Claude → Agy`.
- Escopo: a revisão do piloto exige família distinta da autoria efetiva, registrada como restrição
  de entrada, embora a política geral seja `preferred`.
- Uma execução que caiu em fallback não conta como avaliação concluída do Astra; registra-se o
  motivo e o piloto continua na próxima Task elegível.
- Segunda chamada ao Terra só para dúvida concreta ou experimento autorizado, registrada como
  parecer consultivo sem valor de aprovação.
- Medidas por revisão, em `Agent runs` e no arquivo de comparação da Task: defeitos confirmados
  e hipóteses descartadas; aderência ao escopo e ao schema; tempo, chamadas e consumo observável
  conforme a CLI expuser, sem afirmar a unidade de contagem do plano; rodada extra por falha da
  própria revisão. Evidência de custo citada: `price-astra` e `astra-coding` com suas ressalvas
  (comparação Astra/Sol no Terminal-Bench; nada sobre Terra, quota ou revisão).
