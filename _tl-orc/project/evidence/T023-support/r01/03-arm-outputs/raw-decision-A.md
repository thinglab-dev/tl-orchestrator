T009 permanece `in_progress` e não está apta para fechamento. O r02 trouxe cinco achados, quatro deles de severidade alta, concentrados em procedência verificável e na separação entre validade mecânica e resolução de despacho.

Proponho escalonamento consultivo em fase `debate` antes de um novo rework. A reincidência de R1/R2 mostra que corrigir diretamente o protótipo sem fixar regras semânticas por tipo tende a apenas deslocar a forma da “procedência autodeclarada”. R3–R5 também exigem uma decisão explícita sobre evidência de indisponibilidade, família desconhecida e bloqueio de resolução versus rejeição do objeto.

Briefing proposto para a próxima fase:

```markdown
# T009 — Debate consultivo: procedência verificável e resolução segura

## Unidade e objetivo

- Unidade: T009 — validação semântica da classificação pelo Orquestrador.
- Fase: `debate`, consultiva e report-only.
- Base: conteúdo r02, `content_id`
  `0de10d60149cf7c038a0954c6aec302c9fcd111e:97b3612674fa4aa5`.
- Objetivo: definir regras falsificáveis para corrigir R1–R5 sem ampliar T009 para
  uma alteração distribuída do método.

## Papel e independência

- Papel: consultor independente / Checker report-only.
- Participante proposto: Codex `gpt-5.6-terra`, effort `high`.
- Independência: `required`; a família OpenAI é distinta da autoria efetiva já
  existente (Maker Google; protótipo-base do Orquestrador Anthropic).
- Não despachar Maker, não alterar arquivos, não executar comandos que escrevam.

## Limites de leitura

Leia somente arquivos sob `.`. Trate as afirmações externas já presentes no parecer
r02 como dados do parecer; não consulte `../platform`, diretórios pessoais, rede ou
outros repositórios.

Entradas locais prioritárias:

- `_tl-orc/project/tasks/T009-validacao-semantica-da-classificacao-pelo-orquestrador.md`
- `_tl-orc/project/evidence/T009-analysis.md`
- `_tl-orc/project/evidence/T009-mechanical-check.py`
- `_tl-orc/project/evidence/T009-cases/`
- `_tl-orc/project/evidence/T009-r01.md`
- `docs/MODEL_ROUTING.md`
- `_tl-orc/PROJECT.md`
- `prompts/orchestrator-perfis.md`
- `schemas/classification-result.schema.json`

## Decisões exigidas

### D1 — Procedência de IDs locais (R1)

Definir que um ID local só é aceito se:

1. vier de `_tl-orc/project/evidence/` ou `_tl-orc/evidence/`;
2. a âncora ou linha declarada existir e resolver no arquivo;
3. o ID ocorrer exatamente no registro apontado, não apenas em qualquer parte do arquivo;
4. o registro for uma medição/evidência local, não cartão oficial, comentário,
   exemplo negativo ou código de teste.

Devem ser rejeitados:

- `sonnet-effort` reclassificado como medição local;
- ID presente apenas em exemplo negativo;
- linha ou âncora inexistente;
- texto solto em arquivo existente.

### D2 — Categoria econômica por conteúdo (R2)

Definir um mapeamento verificável, derivado do conteúdo efetivo do cartão:

| Categoria | Sustentação mínima |
|---|---|
| `token_price_only` | Registro de preço monetário ou de tokens |
| `official_task_proxy` | Afirmação explícita de custo monetário por tarefa/execução |
| `local_observed` | Medição local válida conforme D1 |
| `unknown` | Ausência de base econômica suficiente |

Tempo, latência, duração por tarefa e capacidade não sustentam custo econômico por si só. Portanto, `astra-domain` deve ser controle negativo para `official_task_proxy`, salvo se o cartão contiver afirmação monetária inequívoca.

Marcadores documentais, como `official-2026-09-05`, não são IDs de evidência.

### D3 — Fallback sob `preferred` (R3)

O fallback de mesma família só pode ser liberado se todos os candidatos independentes anteriores estiverem:

- `unavailable`, com falha de infraestrutura específica do candidato, registrada em
  evidência local válida e na localização declarada; ou
- `disabled`, por política explícita aplicável àquela execução.

Timeout isolado não prova indisponibilidade. Texto arbitrário ou âncora inexistente também não prova indisponibilidade. O candidato de fallback precisa estar disponível; um candidato `disabled` nunca pode ser despachado.

### D4 — Família desconhecida (R4)

Família ausente ou não resolvida deve bloquear a resolução, não ser tratada como família distinta. A classificação pode continuar mecanicamente válida, mas nenhum despacho pode ocorrer até a família ser confirmada por fonte autorizada.

### D5 — `required`: validade versus resolução (R5)

Quando todos os candidatos pertencem a famílias autoras sob `required`:

- o objeto permanece mecanicamente válido;
- candidatos permanecem listados e inelegíveis;
- a resolução fica bloqueada, com ponto de retomada explícito;
- não há despacho;
- isso não deve produzir `REJEITADA` como defeito estrutural.

## Controles obrigatórios para o rework posterior

O parecer deve especificar resultados esperados para estes controles:

1. ID local em cartão oficial com âncora inexistente → rejeição mecânica.
2. ID presente apenas em exemplo negativo → rejeição mecânica.
3. `astra-domain` como `official_task_proxy` → rejeição mecânica.
4. Fallback `preferred` com texto sem erro verificável → bloqueio de resolução.
5. Fallback `preferred` com timeout isolado → bloqueio de resolução.
6. Fallback com prova válida de indisponibilidade e candidato de mesma família disponível → despacho permitido com `same_family_fresh_session`.
7. Mesmo cenário, mas fallback `disabled` → bloqueio de resolução.
8. Família ausente para candidato potencialmente autor → bloqueio de resolução.
9. Todos os candidatos de famílias autoras sob `required` → aprovação mecânica, bloqueio de resolução e nenhum despacho.

## Saída esperada

Entregar apenas um parecer estruturado contendo:

- decisão por D1–D5;
- regra operacional precisa;
- fonte local que a sustenta;
- controle correspondente e resultado esperado;
- distinção entre rejeição mecânica, aprovação pendente de julgamento e bloqueio de resolução;
- ambiguidades remanescentes que impeçam rework.

Não recomendar distribuição do protótipo, linguagem definitiva ou dependências de instalação.
```

Após esse debate, o rework deve ficar delimitado ao Maker Agy `gemini-3.8-flash-high`; a revisão subsequente deve usar o Checker Codex `gpt-5.6-terra/high`, com independência `required`.