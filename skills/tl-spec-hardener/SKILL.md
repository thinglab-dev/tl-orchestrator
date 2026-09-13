---
name: tl-spec-hardener
description: Use quando o Planner for criar, decompor ou ratificar especificações e stories, impondo pre-mortem prévio, mapeamento estrito de código (arquivo:linha), fronteiras invioláveis e critérios de aceite falsificáveis antes de qualquer escrita de código pelo Maker.
metadata:
  target_roles:
    - planner
    - orchestrator
  triggers:
    - "planejamento, decomposição, spec, breakdown de story"
    - "fase plan, ratify, criação de tarefas"
---

# TL-Spec-Hardener: Planejamento Blindado para o Planner

Esta skill governa o papel do **Planner** no TL-Orchestrator.

A função do Planner **não é escrever código nem gerar listas vagas de desejos**. Sua missão é entregar uma **especificação cirúrgica, estanque e à prova de falhas** que guie o Maker sem ambiguidades e sem queima desnecessária de contexto.

---

## 1. O Pre-Mortem Obrigatório (Pensar na Falha Antes do Código)

Antes de decompor qualquer story em tarefas, o Planner DEVE executar mentalmente o exercício do **Pre-Mortem**:

> *"Imagine que esta story foi implementada, passou nos testes superficiais, foi entregue e quebrou feio em produção após 48 horas. Qual foi o motivo exato?"*

O Planner deve responder e mitigar na própria spec:
1. **Falha de Concorrência ou Volume:** O que acontece sob 100x mais carga ou com workers simultâneos?
2. **Falha de Reinicialização:** Se o processo morrer ou a máquina reiniciar no meio de uma gravação, o estado se corrompe?
3. **Falha de Dependência/Rede:** Se a API externa ou o banco ficarem offline por 10 minutos, o sistema trava ou se recupera?
4. **Violação de Fronteira:** Essa mudança quebra contratos com outras partes do sistema?

---

## 2. As 7 Seções Obrigatórias de uma Spec de Elite

Toda especificação gerada ou ratificada pelo Planner DEVE conter exatamente estas 7 seções estruturadas:

### 1. `## Status`
Declara o estado canônico no board (ex: `ready-for-dev`, `in-progress`).

### 2. `## Intent`
Explica o **porquê** da mudança em 2 a 4 frases concisas: o problema real que resolve e o valor técnico/econômico entregue.

### 3. `## Boundaries & Constraints`
* **Arquivos permitidos para escrita:** Lista explícita dos únicos arquivos/diretórios que o Maker pode alterar.
* **Arquivos expressamente proibidos:** Arquivos protegidos (`config.json`, segredos, outros módulos).
* **Restrições técnicas:** Não adicionar novas dependências externas sem aprovação, manter Go puro, etc.

### 4. `## Code Map`
Mapeamento cirúrgico dos pontos de partida no código com citações no formato `caminho/do/arquivo.ext:linha`. 
* Evita que o Maker gaste turnos varrendo o repositório no escuro.

### 5. `## Tasks & Acceptance`
Tarefas atômicas e sequenciais, onde cada tarefa possui:
* O que fazer exatamente.
* **Critérios de Aceite Falsificáveis:** Checklists `[ ]` com condições objetivas (nunca critérios subjetivos como "fazer rápido").

### 6. `## Verification`
Os comandos exatos que comprovam o sucesso offline:
* Comandos de build e teste (ex: `go test -race ./...`).
* Linters e checagens estáticas (ex: `gofmt -l .`).

### 7. `## O que pedir a revisao independente`
Instruções diretas para o Checker: onde focar a auditoria adversarial (os 2 ou 3 pontos mais arriscados da mudança).

---

## 3. Anti-Patterns Absolutos do Planner

* ❌ **NUNCA use critérios vagos:** Frases como "tratar erros adequadamente", "otimizar desempenho" ou "refatorar para ficar limpo" são PROIBIDAS. Use: "se HTTP status != 200, retornar ErrUpstream com backoff exponencial".
* ❌ **NUNCA deixe fronteiras de arquivos abertas:** "Alterar arquivos necessários" é inaceitável. O Maker precisa de limites fechados.
* ❌ **NUNCA crie tarefas gigantes de 500 linhas:** Se uma tarefa envolve tocar em 5 subsistemas ao mesmo tempo, ela deve ser quebrada em etapas menores.
* ❌ **NUNCA assuma que o caminho feliz é suficiente:** Se uma tarefa lida com entrada externa, deve haver um critério de aceite para entrada malformada ou vazia.

---

## 4. Checklist de Auto-Avaliação do Planner

Antes de liberar a spec para ratificação:

- [ ] Todas as 7 seções obrigatórias estão presentes?
- [ ] O Code Map cita locais exatos em `arquivo:linha`?
- [ ] Os arquivos autorizados estão explicitamente listados em Boundaries?
- [ ] Todos os critérios de aceite podem ser verificados por comandos ou testes automáticos?
- [ ] A seção do Checker aponta os riscos reais identificados no Pre-Mortem?
