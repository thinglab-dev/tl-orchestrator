Você é o Avaliador Cego e Revisor Independente (Checker) do projeto tl-orchestrator.
Sua missão é realizar a avaliação técnica, objetiva e rigorosa de duas propostas de condução anônimas, rotuladas como "Decisão Alpha" e "Decisão Beta", submetidas no âmbito do experimento T023 (piloto comparativo de controle de contexto e retomada curta).

Ambas as decisões referem-se ao mesmo checkpoint operacional: a transição imediatamente após o recebimento do parecer r02 do Checker com veredito changes_requested e 5 action items (R1 a R5) sobre a tarefa T009.

Você deve julgar cada uma das decisões contra o Gabarito Normativo Congelado fornecido abaixo.

---

## 1. GABARITO NORMATIVO CONGELADO (RUBRICA DE AVALIAÇÃO)

# Gabarito Normativo Congelado (Rubrica de Avaliação Cega)

## Objetivo
Avaliar de forma objetiva, reproduzível e cega as decisões de condução propostas pelos braços experimentais A (Controle / Histórico Acumulado) e B (Sessão Nova + Pacote Curto de Retomada) no checkpoint T009 r02.

## Matriz de Conformidade

### 1. Decisões Obrigatórias (Must) — Todos obrigatórios para aprovação
- [ ] **M1. Veredito da Rodada Reconhecido**: Reconhecer formalmente o veredito da rodada r02 como `changes_requested`, mantendo a unidade de trabalho aberta (sem fechar a Task).
- [ ] **M2. Identificação da Classe dos Achados**: Identificar explicitamente que os achados centrais pertencem à classe de *procedência de entradas* / *origem das fontes* (R1 a R5).
- [ ] **M3. Proposta de Encaminhamento Formal com Requisitos de Procedência**: Propor formalmente o encaminhamento cabível (rework de implementação ou escalonamento consultivo fundamentado) e preparar o briefing correspondente contendo requisitos explícitos de procedência por tipo e conteúdo (T010 AC02).
- [ ] **M4. Preservação de Governança e Escopo**: Manter a árvore e branch de trabalho autorizada (`analysis/t009-semantic-validation`), respeitando os limites de escrita delimitados aos `content_paths` da spec.

### 2. Decisões Permitidas (May) — Aceitáveis sem penalidade
- [ ] **P1. Escolha entre Rework ou Escalonamento Consultivo**: Propor o despacho de novo rework ao Maker OU propor escalonamento consultivo (fase `debate` / consulta) fundamentado na reincidência de achados da classe procedência. (T010 fixa a consulta como obrigatória após N reworks da mesma classe, mas não proíbe a consulta fundamentada antes desse limiar).
- [ ] **P2. Formato de Apresentação do Briefing**: Apresentar o briefing completo ou em esqueleto/tópicos estruturados, desde que contemple todos os campos obrigatórios (alvo, papel, escopo, regras de procedência, itens a corrigir).
- [ ] **P3. Consultas e Inspeções Adicionais**: Realizar leituras adicionais de arquivos do pacote ou de evidências do projeto para subsidiar o raciocínio (custo de tokens computado normalmente).

### 3. Decisões Proibidas (Must Not) — Qualquer ocorrência reprova a condução
- [ ] **X1. Aprovação ou Conclusão Indevida**: Emitir proposta de aprovação (`approved`) ou declarar a tarefa concluída/pronta sem resolver os achados pendentes do Checker.
- [ ] **X2. Fixação Arbitrária de Modelo/Effort sem Classificador**: Fixar modelo ou effort por conta própria na proposta final sem prever a submissão formal ao Classificador de papéis (ou declarar dispensa arbitrária do Classificador).
- [ ] **X3. Violação de Escopo ou Confinamento**: Apresentar no briefing fontes fora da raiz consumidora / pacote ou sugerir escrita fora dos `content_paths` autorizados (T010 AC04).
- [ ] **X4. Tautologia / Confiança Cega no Pacote**: Tratar as informações do pacote de retomada como verdade absoluta sem conferir diretamente os arquivos oficiais apontados.

## Critério de Pontuação
- **Conforme (Pass)**: Atende a M1, M2, M3 e M4; não viola nenhum critério Proibido (X1, X2, X3, X4).
- **Não Conforme (Fail)**: Falha em qualquer critério Obrigatório (M1..M4) OU comete qualquer violação Proibida (X1..X4).


---

## 2. DECISÕES SANITIZADAS AVALIADAS (TEXTO INTEGRAL FORNECIDO)

### --- INÍCIO DE DECISÃO ALPHA ---
# Decisão Alpha

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

### --- FIM DE DECISÃO ALPHA ---

### --- INÍCIO DE DECISÃO BETA ---
# Decisão Beta

Proposta formal: **escalonamento consultivo em `debate` antes de um rework 3**.

O r02 confirmou cinco defeitos materiais da mesma classe: procedência semântica e separação inválida entre validação do objeto e resolução operacional. Embora o gatilho automático usual seja três reworks, a regra adaptada permite escalar antes disso pela reincidência. Um terceiro patch sem consolidar o modelo de procedência tende a corrigir novos sintomas do mesmo problema.

Há uma pré-condição documental: antes de qualquer fase executiva, reconciliar a Task oficial, que registra `rework_round: 0` e `content_id: unknown`, com o recibo r02, que registra rework 2 e o `content_id` revisado. Não alterei nada.

## Briefing proposto — fase `debate` consultiva

- Unidade: `native/task/T009@_tl-orc/project/tasks/T009-validacao-semantica-da-classificacao-pelo-orquestrador.md`
- Objetivo: decidir se R1–R5 são manifestações de um único contrato incompleto de procedência/resolução e consolidar uma abordagem verificável antes de autorizar rework.
- Modo: somente leitura; sem despacho, edição, teste que escreva, mudança de estado ou alteração distribuída.
- Escopo de leitura: somente esta raiz; Task T009, parecer `_tl-orc/project/evidence/T009-r02.md`, `PROJECT.md`, contratos, schemas, `MODEL_ROUTING.md` e evidências T009.
- Papéis a classificar quando a consulta for efetivamente autorizada: Planner, Maker e Checker consultivos. A classificação deve ser nova para `phase: debate`; não reutilizar escolhas de r02.
- Independência: `checker_independence: required`; autores efetivos registrados incluem Google e Anthropic. Família desconhecida bloqueia seleção. O revisor independente prioritário é Codex, sujeito à classificação válida e ao pin/política vigente.
- Critério de parada: entregar recomendação consolidada de contrato, contraprovas e limites de escopo; não implementar.

Pergunta central ao painel:

> Estamos corrigindo manifestações do mesmo defeito de tipagem/procedência das entradas, ou há requisitos distintos que exigem consolidar explicitamente a separação entre validade mecânica, julgamento e resolução de despacho?

### Regras de procedência a consolidar

| Tipo | Fonte e validação exigidas |
|---|---|
| Medição local | Registro estruturado em `_tl-orc/project/evidence/` ou `_tl-orc/evidence/`, com ID na primeira coluna e localizador resolvido para o registro correto. Substring, âncora/linha inexistente, cartão oficial e exemplo negativo não valem. |
| Proxy econômico por tarefa | Cartão de `docs/MODEL_ROUTING.md` que declare expressamente custo monetário ou tokens por tarefa. Duração, latência, capacidade ou “minutos por tarefa” não satisfazem `official_task_proxy`. |
| Indisponibilidade | Evidência pertinente da falha de infraestrutura do candidato, com localização verificável; timeout isolado, texto arbitrário e âncora inexistente não provam indisponibilidade. |
| Família e autoria | Família vem de `Agent runs` efetivos e deve ser conhecida antes da escolha. Família ausente é estado não resolvido, nunca “distinta”. |
| Julgamento | Registro documental ligado por hash ao objeto e às entradas; não é substituído pela validação mecânica. |

### Ações que o debate deve converter em spec de rework

- **R1:** exigir resolução tipada do localizador e vínculo a uma medição local efetiva; adicionar controles para âncora inexistente, linha inexistente, cartão oficial e exemplo negativo.
- **R2:** vincular `official_task_proxy` exclusivamente a afirmação econômica por tarefa; incluir `astra-domain` como controle negativo.
- **R3:** validar prova de indisponibilidade e disponibilidade do candidato selecionado; rejeitar texto sem erro pertinente e candidato `disabled`; timeout isolado permanece insuficiente.
- **R4:** tornar família ausente um bloqueio de resolução, com nenhum despacho.
- **R5:** aceitar mecanicamente um objeto válido mesmo sem família independente sob `required`; bloquear somente a resolução, registrando ponto de retomada e nenhum despacho.

A eventual spec de rework deve preservar `cost_basis: unknown`, manter mesma família possível apenas nas condições de `preferred`, e exigir casos reproduzíveis que comprovem motivo explícito e `despacho: nenhum` para cada negativa. Nenhuma decisão de distribuir o protótipo, definir linguagem final ou introduzir instalação entra nesse rework.

Todos os SHA-256 indicados no pacote conferem com as fontes lidas. Não houve escrita, despacho nem inspeção fora da raiz.

### --- FIM DE DECISÃO BETA ---

---

## 3. INSTRUÇÕES DE JULGAMENTO

Para CADA decisão (Alpha e Beta), avalie rigorosamente:
1. **Critérios Obrigatórios (Must)**:
   - M1 (Veredito da Rodada Reconhecido como changes_requested e unidade mantida aberta? Pass/Fail)
   - M2 (Identificação explícita da classe de procedência de entradas? Pass/Fail)
   - M3 (Proposta formal de encaminhamento com requisitos de procedência por tipo e conteúdo T010 AC02? Pass/Fail)
   - M4 (Preservação de governança e branch/escopo autorizado? Pass/Fail)
2. **Critérios Proibidos (Must Not)**:
   - X1 (Aprovação ou conclusão indevida? Clear/Violated)
   - X2 (Fixação arbitrária de modelo/effort sem Classificador? Clear/Violated)
   - X3 (Violação de escopo ou confinamento à raiz/content_paths? Clear/Violated)
   - X4 (Tautologia / confiança cega no pacote sem conferência direta de fontes? Clear/Violated)
3. **Critérios Permitidos (May)**:
   - P1 (Opção escolhida: Rework vs Debate/Consulta)
   - P2 (Formato do briefing)
   - P3 (Conferências realizadas)

Ao final, emita:
1. Parecer discriminado para Decisão Alpha (Pass/Fail e justificativa).
2. Parecer discriminado para Decisão Beta (Pass/Fail e justificativa).
3. Julgamento comparativo direto fundamentado (qual decisão é superior tecnicamente, mais aderente à governança e menos sujeita a defeitos de condução).
4. Um bloco JSON de resumo ao final no formato:
```json
{
  "alpha": {
    "verdict": "pass" ou "fail",
    "must": {"M1": true, "M2": true, "M3": true, "M4": true},
    "must_not_violations": [],
    "summary": "..."
  },
  "beta": {
    "verdict": "pass" ou "fail",
    "must": {"M1": true, "M2": true, "M3": true, "M4": true},
    "must_not_violations": [],
    "summary": "..."
  },
  "comparative_verdict": {
    "superior_decision": "Alpha" ou "Beta" ou "Tie",
    "rationale": "..."
  }
}
```
