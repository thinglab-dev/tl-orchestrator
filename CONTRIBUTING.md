# Contribuindo

Este arquivo orienta somente o repositório fonte; ele não faz parte do pacote distribuído.

## Antes de abrir um pull request

1. Parta de uma revisão identificada e trabalhe fora de `main`.
2. Mantenha a mudança delimitada. Features precisam de intenção aprovada; uma suspeita isolada
   não autoriza ampliar o método.
3. Não inclua conteúdo de consumidores (`_tl-orc/` de projetos consumidores, suas configurações,
   evidências e logs), caminhos privados, dados pessoais, segredos ou credenciais. Revise também
   metadados e autoria. O `_tl-orc/project/` deste repositório é a área Native do próprio método
   (achados, análises e correções sobre o pacote) e pode ser versionado; ele não faz parte da
   distribuição.
4. Se alterar a distribuição, atualize `distribution-manifest.json`, todas as listas e contagens do
   README e os links relativos do pacote.
5. Atualize `CHANGELOG.md` quando a mudança for relevante para uma release.
6. Execute `python3 scripts/validate_repository.py` e registre outras provas pertinentes.

Use o template do repositório para descrever baseline, intenção, compatibilidade, migração,
provas e sanitização. Relacione issues sem palavras que as fechem automaticamente, salvo decisão
explícita do maintainer.

O CI verifica consistência estrutural; ele não prova o comportamento do método. Merge, tag e
GitHub Release dependem de revisão e aprovação do maintainer.

## Fechamento e publicação

Preferência e autorização operacional registradas pelo maintainer em 2026-09-05:
ao implementar uma mudança autorizada trabalhando na raiz deste repositório fonte,
concluir também commit, push, PR, merge e, havendo mudança distribuível, GitHub Release
estável com changelog. Não esperar um novo pedido para cada etapa. Instruções mais
recentes ou um pedido limitado a análise, rascunho ou não publicação prevalecem.

1. Preserve alterações alheias e publique somente o escopo autorizado, sem evidências
   privadas ou arquivos de consumidores.
2. Exija as provas e a revisão aplicáveis ao método, CI aprovado, ausência de conflito
   e correspondência entre o commit revisado e o que será integrado. Não contorne
   proteções de branch nem revisões exigidas pelo GitHub.
3. Para mudanças distribuíveis, escolha a próxima versão SemVer livre, mova as notas
   de `Unreleased` para a versão datada e integre esses metadados antes da tag.
4. Publique a tag e a release no commit exato integrado à `main`; não mova tags já
   publicadas. Confira no GitHub o merge, a tag e a release, incluindo o estado do CI.
5. Informe versão, link e limitações de migração. Publicar não significa atualizar ou
   validar automaticamente instalações de consumidores.

Se faltar permissão, revisão, validação ou decisão material de compatibilidade, pare
e relate o bloqueio. Esta autorização não amplia `auto_pr`: contribuições originadas
em consumidores continuam limitadas a draft PR, sem merge ou release automáticos.
Não há um serviço de publicação em segundo plano; esta é a rotina de fechamento do
agente durante o trabalho autorizado neste repositório.
