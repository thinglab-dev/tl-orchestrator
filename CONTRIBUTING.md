# Contribuindo

Este arquivo orienta somente o repositório fonte; ele não faz parte do pacote distribuído.

## Antes de abrir um pull request

1. Parta de uma revisão identificada e trabalhe fora de `main`.
2. Mantenha a mudança delimitada. Features precisam de intenção aprovada; uma suspeita isolada
   não autoriza ampliar o método.
3. Não inclua conteúdo de consumidores, `_tl-orc/`, configurações, evidências, logs, caminhos
   privados, dados pessoais, segredos ou credenciais. Revise também metadados e autoria.
4. Se alterar a distribuição, atualize `distribution-manifest.json`, todas as listas e contagens do
   README e os links relativos do pacote.
5. Atualize `CHANGELOG.md` quando a mudança for relevante para uma release.
6. Execute `python3 scripts/validate_repository.py` e registre outras provas pertinentes.

Use o template do repositório para descrever baseline, intenção, compatibilidade, migração,
provas e sanitização. Relacione issues sem palavras que as fechem automaticamente, salvo decisão
explícita do maintainer.

O CI verifica consistência estrutural; ele não prova o comportamento do método. Merge, tag e
GitHub Release dependem de revisão e aprovação do maintainer. Não há release automática.
