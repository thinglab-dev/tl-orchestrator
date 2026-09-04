# Configuração do projeto consumidor

Este guia ajuda a descobrir o projeto real. Não é um arquivo obrigatório a preencher ou copiar: use as fontes que o consumidor já mantém, sem criar uma segunda configuração.

## Duas raízes

- **Raiz do pacote:** pasta instalada contendo [SKILL.md](../SKILL.md), contratos e schema. Referências do método partem desta distribuição.
- **Raiz consumidora:** projeto, workspace ou diretório indicado pelo usuário para o trabalho. Código, regras, stories e evidências pertencem a essa raiz ou ao sistema de tarefas que ela declarar.

O pacote pode estar instalado fora do projeto, em uma pasta de skills. Ferramentas executam no diretório exigido pelo portão consumidor, não na pasta da skill. Se o ambiente bloquear a leitura do pacote por outro agente, forneça o conteúdo necessário por um meio permitido; não suponha que caminhos absolutos da sua máquina funcionem para ele.

## Descoberta proporcional

| Informação | Fontes a procurar | Decisão que permite |
| :--- | :--- | :--- |
| Objetivo e modo | Pedido atual, story ou ticket | Analisar, planejar, implementar ou revisar |
| Regras e autoridade | Instruções de agentes, documentação de contribuição, decisões vigentes | Delimitar ações e responsáveis |
| Raiz e escopo | Workspace informado, manifestos e controle de versão se houver | Localizar a árvore e preservar trabalho anterior |
| Estado base | Diff/status ou versão/cópia de referência disponível | Comparar a mudança |
| Portões | CI, documentação de desenvolvimento, comandos dos manifestos | Definir verificações e diretório de execução |
| Dependências | Código, contratos, specs e backlog local | Decidir ordem e fronteiras |
| Evidência | Artefatos por tarefa, sistema de tickets ou relatórios existentes | Preservar resultados e pareceres |
| Agentes | Ferramentas disponíveis, configuração e ajuda atual | Escolher capacidade, permissões e independência |

Leia primeiro as fontes pertinentes; não faça um questionário se elas já respondem. Se não houver Git, use a comparação de arquivos/versões disponível. Se não houver portão automatizado, proponha uma verificação observável adequada à mudança e deixe explícito seu alcance. Não exija uma linguagem, banco, Makefile, CI ou arquivo de plataforma específico.

Pergunte apenas quando uma lacuna não resolvível afetar intenção, escopo, custo, autoridade ou efeito externo. Defina detalhes técnicos rotineiros conforme as convenções encontradas.

## Configuração por tarefa

O briefing ou a story pode registrar, no formato existente:

| Dado | Exemplo genérico |
| :--- | :--- |
| Raiz do pacote | Pasta da skill instalada, separada do projeto |
| Raiz consumidora | Workspace indicado pelo usuário |
| Intenção e modo | Planejar a mudança descrita no ticket; sem implementação |
| Escopo e ownership | Artefato do plano, autor único; produto e board protegidos |
| Estado base | Versão de referência e alterações preexistentes observadas |
| Portão | Comando declarado na documentação local, executado na raiz que ela indicar |
| Evidência | Relatório vinculado à tarefa com comandos, exits e limites |
| Efeitos externos | Somente os já autorizados pelo usuário |

Os valores são descobertos, não executados a partir desta tabela. Preferências pessoais e IDs de modelo ficam na configuração da sessão ou do consumidor, fora do pacote reutilizável.

## BMAD e outros métodos

O pacote funciona com uma story em Markdown, um ticket ou outro contrato verificável. Quando BMAD existir, leia sua instalação oficial e as políticas locais aplicáveis. Use os artefatos do projeto correto e customizações suportadas; não altere upstream para acomodar o método. Não invente instruções de instalação: consulte a documentação oficial atual se essa for uma tarefa autorizada.
