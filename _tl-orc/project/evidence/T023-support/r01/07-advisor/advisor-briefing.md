Você é o Advisor consultivo (modo Debater) do tl-orchestrator.
Sua missão é emitir parecer consultivo em prosa estruturada, desafiando criticamente premissas, riscos, objeções e regras operacionais da proposta experimental da Task T023 antes do congelamento experimental definitivo.
Conforme as instruções do modo Debater, entregue sua opinião em prosa técnica estruturada (NÃO utilize schema JSON de review nem emita 'verdict: approved/changes_requested').

## 1. Proposta Experimental em Debate (Task T023)
- **Objetivo**: Comparar empiricamente a continuidade operacional com histórico longo acumulado (Braço A) versus sessão nova com Pacote Curto de Retomada atuando estritamente como índice aberto de conferência não-tautológico (Braço B), no caso adaptado do checkpoint T009 r02.
- **Governança de Papéis**:
  - Advisor (você, família Google / Agy Gemini 3.1 Pro High): consultado uma vez antes do congelamento experimental.
  - Searcher: dispensado (sem consultas externas/locais não-triviais).
  - Planner: dispensado (planejamento da análise estabelecido).
  - Braços A e B: congelados simetricamente no mesmo tuple do Orquestrador (`codex / gpt-5.6-terra / high`).
  - Avaliador Cego: independente de OpenAI (`agy / gemini-3.1-pro-high / high`) avaliando decisões sanitizadas contra gabarito normativo congelado.
  - Checker independente: no fechamento formal da tarefa.

## 2. Resolução do Apontamento R5 (Orçamento Calibrado e Parada Ativa)
- **Diagnóstico da Rodada r01/r02**: O ensaio inicial de B consumiu 10 requisições para conferir os 12 hashes no disco, enquanto o script e manifesto registravam teto nominal de 4 requisições em B / 11 globais.
- **Medida Adotada para Congelamento**: O orçamento é formalmente pré-congelado na spec, no manifesto e no script em:
  - Teto Global: 16 requisições de IA e 3.505.000 tokens.
  - Sub-teto Braço B: até 10 requisições de IA (500.000 tokens).
  - Mecanismo Fail-Closed Ativo em `run_arms.py`: monitoramento de turnos/requisições após cada chamada; se B atingir 10 requisições sem emitir proposta conclusiva, o script aborta imediatamente com status fail-closed `sub_budget_exceeded`.
  - Medição contábil explícita de `cache_creation_input_tokens` e `cache_read_input_tokens` via parser nativo `scripts/tl_usage.py` sobre os rollouts JSONL.

## 3. Resolução do Apontamento R6 (Eliminação de Caminhos Privados Locais)
- **Diagnóstico da Rodada r02**: Presença de caminhos físicos locais `<local-user-home>/` em scripts, rollouts e resumos versionados.
- **Medida Adotada**: Todos os caminhos físicos foram anonimizados para `<repo-root>` ou referências relativas ao diretório raiz, mantendo a integridade reprodutível sem expor identificadores privados de máquina ou usuário.

## 4. Princípio de Não-Tautologia do Pacote Curto
- O Pacote Curto de Retomada (`short-resume-package.md`) contém hashes SHA-256 e apontadores de 12 arquivos normativos.
- O Braço B é instruído explicitamente a **não confiar cegamente** no pacote e inspecionar diretamente os arquivos reais no disco para validar seu estado antes de formular o plano de ação.

## 5. Questões Específicas para seu Parecer
Avalie estruturadamente:
1. **Suficiência e Robustez da Calibração Orçamentária (R5)**: O teto de 16 requisições totais com até 10 para o Braço B e parada fail-closed ativa no script fornece margem técnica segura para a conferência sem risco de sobre-execução descontrolada?
2. **Eficácia da Anonimização de Caminhos (R6)**: A substituição de caminhos absolutos locais por `<repo-root>` e relativos atende aos requisitos de reprodutibilidade e limpeza do repositório?
3. **Validade Metodológica da Não-Tautologia**: A conferência obrigatória dos 12 hashes no disco mitiga satisfatoriamente o risco de o modelo inventar fatos ou confiar em resumos prévios?
4. **Objeções, Riscos Residuais ou Recomendações**: Existe algum obstáculo impeditivo para procedermos ao congelamento mecânico e execução dos braços A e B?
