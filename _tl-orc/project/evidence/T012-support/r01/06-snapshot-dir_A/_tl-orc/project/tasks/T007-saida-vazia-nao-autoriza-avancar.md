id: T007
type: analysis
deliverable: none
standalone: true
method: native
status: draft
state_revision: 0
depends_on: []
blocked_by: []
origin: user (smoke de roteamento v0.5.0 no consumidor platform, Codex como Orquestrador, 2026-09-07)
decisions: []
spec_author: none
content_paths: []

## Finding
source: relatório do Orquestrador Codex `gpt-5.6-terra` (sessão 01a07d8a-f44f-7333-83b5-9a76cca086b4): Classificador Luna indisponível (codex aninhado não inicia no sandbox; erro literal) → `claude -p` aninhado devolveu saída vazia → avançou para Agy Flash
expected: "Um timeout isolado, saída vazia ou processo ainda vivo não comprovam" indisponibilidade; estado `unknown` exige conferir por meios disponíveis e, se continuar ambíguo, bloquear (perfis, Fallback e interrupção)
observed: o Orquestrador tratou a saída vazia como indisponibilidade e avançou na cadeia; o smoke completou a ordem mediante fallback proibido; o Orquestrador da atualização aceitou inicialmente o resultado como `operational_verified` (corrigido para `operational_pending`)
impact: prova de roteamento inválida no harness Codex; risco de contornar o perfil fixo do Classificador por falha ambígua
hypothesis: (a) a regra existe mas o Orquestrador Codex não a aplicou ao Classificador, só aos papéis de trabalho; (b) o briefing do smoke não explicitou o tratamento de saída vazia; (c) no sandbox do Codex, `claude -p` aninhado falha silenciosamente e não há meio de esclarecer, o que deveria terminar em bloqueio com ponto de retomada, não em avanço
next verification: reproduzir `claude -p` aninhado no sandbox do Codex capturando exit code e stderr; decidir se o contrato precisa dizer explicitamente que a cadeia fixa do Classificador segue a mesma tabela de estados; sonda: smoke Codex com instrução literal e observar bloqueio em vez de avanço
dedup: T003 (correção impossível → avançar) e T006 (resume) são distintos; este é sobre prova de indisponibilidade
