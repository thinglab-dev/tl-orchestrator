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
