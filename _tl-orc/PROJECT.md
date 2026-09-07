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
checker_independence: preferred

Na ausência de catálogo persistido aqui, o contrato já permitia aplicar o perfil publicado após
conferir as capacidades do harness e montar o catálogo permitido para a classificação. Esta seção
persiste esse catálogo e as preferências operacionais deste repositório (parecer favorável do
maintainer em 2026-09-07). Descoberta (a CLI conhece
o modelo), permissão (o par consta abaixo) e acesso (observado na chamada autorizada e registrado
em `Agent runs`) são coisas diferentes; nenhuma delas prova a outra.

### Cadeias (preferência operacional; fallbacks autorizados preservados)

| Papel | Cadeia |
| :--- | :--- |
| Classificador | Codex → Claude → Agy (perfil fixo publicado) |
| Planner | Claude → Codex → Agy |
| Maker | Agy → Codex → Claude |
| Checker report-only | Codex → Claude → Agy, respeitando a autoria efetiva |

Autoria efetiva: identifique todas as famílias que produziram o conteúdo revisado, incluindo
reworks, experimentos comparativos e correções próprias do Orquestrador. Sob `preferred`,
priorize famílias não autoras; se nenhuma estiver utilizável e a indisponibilidade estiver
comprovada, admita Checker da mesma família em sessão nova, registrando
`same_family_fresh_session`. Uma restrição específica `required`, como a deste piloto, impede
esse fallback. Experimentos comparativos continuam sujeitos às autorizações e à autoria efetiva
resultante.

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
| Maker | Agy | `gemini-3.8-flash-high` | high (no ID) | preferência do usuário |
| Maker | Codex | `gpt-5.6-terra` | medium, high, xhigh | |
| Maker | Claude | `sonnet` | medium, high | |
| Maker | Claude | `claude-opus-5` | high | |
| Checker | Codex | `gpt-6-astra` | high | acesso não comprovado até a primeira chamada |
| Checker | Codex | `gpt-6-astra` | xhigh | condicional: exige justificativa específica do Classificador sobre o risco da fase e a necessidade de esforço adicional, dentro do orçamento autorizado e registrada antes do despacho; no piloto inicial o pin `gpt-6-astra/high` prevalece |
| Checker | Codex | `gpt-5.6-terra` | high | referência atual |
| Checker | Claude | `sonnet` | high | |
| Checker | Claude | `claude-opus-5` | high | |
| Checker | Agy | `gemini-3.1-pro-high` | high (no ID) | |
| Searcher | Agy | `gemini-3.8-flash-medium` | medium (no ID) | sob demanda |

`max` e `ultra` não constam; aparecer na CLI não autoriza. Pares fora do catálogo são inválidos e
devem ser rejeitados. `null`/`null` é permitido somente quando não houver candidato autorizado e
adequado naquele harness para o papel solicitado; nunca como normalização de uma escolha inválida.

### Piloto de avaliação do Astra como Checker

- Pin do piloto: candidato do harness Codex para Checker fixado em `gpt-6-astra/high`. O
  Classificador continua sendo chamado, valida as restrições e dimensiona os fallbacks.
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
