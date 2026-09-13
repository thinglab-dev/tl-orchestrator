id: T008
type: analysis
deliverable: none
standalone: true
method: native
status: draft
state_revision: 0
depends_on: []
blocked_by: []
origin: user (fresh load v0.5.0 no consumidor platform, Agy como Orquestrador, conversa c1591eb2-5894-4f18-b849-c9cb65aa127f, 2026-09-07)
decisions: []
spec_author: none
content_paths: []

## Finding
source: transcrição da ativação somente leitura no Agy `gemini-3.8-flash-medium`: executou `find $HOME -maxdepth 4 -name "_tl-orc"` e listou também o `_tl-orc` do repositório fonte, fora da raiz consumidora
expected: SKILL.md manda identificar a raiz do projeto consumidor pelo pedido, workspace e arquivos locais, e resolver links em relação ao pacote; nada autoriza varrer o diretório do usuário
observed: descoberta por varredura ampla, só leitura, sem efeito, mas com exposição de outro projeto; o menu apresentado ainda incluiu Debater sem decisão material pendente
impact: risco de confundir raiz consumidora com outro repositório e de vazar caminhos de terceiros nos relatórios; divergência do contrato de ativação
hypothesis: a redação de "Identifique separadamente a raiz do projeto consumidor" não proíbe explicitamente buscas fora do diretório de trabalho; o Agy interpreta "arquivos locais" de forma ampla
next verification: acrescentar ao SKILL.md que a descoberta se limita à raiz consumidora e seus subdiretórios; sonda de ativação em Agy sem comandos fora da raiz; conferir também a condição de oferta de Debater
dedup: sem unidade existente sobre descoberta; T001 (menu de fila) é sobre outra opção do menu
