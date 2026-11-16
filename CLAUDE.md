# Instruções para o Claude Code

App local (Flask + SQLite + OR-Tools CP-SAT) que lê a planilha orçamentária de uma obra e monta o cronograma com
equipes. O usuário é engenheiro civil. O README explica cada etapa e ajuste (uma seção por item); leia a seção
do item anterior antes de começar o próximo.

## Idioma

- Responder sempre em **português do Brasil**, de forma direta, com números e tabelas quando houver resultado.
- Código, nomes de funções, variáveis, mensagens da tela e testes em português, como o resto do projeto.

## Como cada item chega e o que entregar

1. A especificação vem como `ITEM_X_....md` (ou `ETAPA_...md`) na raiz do projeto; os arquivos novos de dados
   (`biblioteca_atividades.xlsx`, `funcoes.xlsx`, `produtividade_referencia.xlsx`) vão para `dados/`.
   Se o usuário disser que um arquivo está em `dados\` e ele não estiver, procure nos anexos da conversa; se não
   achar, pergunte antes de seguir. Confira o que o usuário pedir (ex.: número de colunas, aba nova).
2. Siga a especificação **inteira**, inclusive a seção de testes e a do relatório final.
3. Rode **todos** os testes, atualize o README (seção nova no fim, no mesmo estilo das anteriores, e corrija
   trechos antigos que ficaram desatualizados), faça o commit na `main` e envie (`git push -u origin main`).
4. Responda com o relatório pedido na especificação (antes × depois, tabelas) e o que mais o usuário precisa saber.

## Regras de trabalho

- **Não afrouxar testes.** Testes antigos que dependem de valores ou regras que a especificação mudou são
  reescritos para a regra nova, mantendo a intenção. Diga no relatório quais foram ajustados e por quê.
- Se um teste pedido na especificação não passar e o motivo for o dado ou a própria especificação, **não mude o
  teste para passar**: marque como falha esperada (`xfail(strict=True)` com o motivo) e explique ao engenheiro.
- As obras antigas do banco são dados de teste: não precisam de migração cuidadosa além das colunas novas
  (`MIGRACOES` em `armazenamento/banco.py`).
- Valores digitados pelo usuário em geral viram padrão das próximas obras (siga o padrão já existente).
- Confira as mudanças de tela no navegador (Playwright) antes do commit: sem erros no console, e o que a
  especificação pede aparece e funciona.

## Testes

```bash
python -m pytest -q -p no:cacheprovider
```

- A suíte inteira leva uns 5 minutos (alguns testes rodam o otimizador por vários segundos). Para iterar, rode
  só os arquivos afetados (`tests/test_item72.py`, etc.) e a suíte inteira antes do commit.
- Um arquivo de teste por item: `tests/test_item6.py`, `test_item7.py`, `test_item71.py`, `test_item72.py`...
- Planilha de teste: `tests/dados/Concorrencia_2_2024_PLANILHA_ORCAMENTARIA_EDITAVEL.XLSX`.
- Para montar uma obra completa (em testes ou em scripts de relatório):
  - `conftest.preparar_obra(banco, ARQUIVO_TESTE, biblioteca)` importa, liga e monta a rede;
  - `mao_de_obra.obra.analisar_obra(...)` calcula a mão de obra;
  - `test_etapa5_obra.resolver_pendencias(...)` responde as pendências como o usuário faria;
  - `cronograma.obra.salvar_parametros_cronograma(banco, obra, {"data_inicio": INICIO})` e
    `calcular_cenario(banco, obra, 12, biblioteca)` (12 meses, 60 s) para o cronograma.

## Relatórios antes × depois

- O "antes" deve ser o código do commit anterior: use `git worktree add <pasta temporária> <commit>` (copie a
  planilha de `tests/dados/` se faltar) e rode o mesmo script nas duas versões.
- Rode o otimizador **uma versão de cada vez**: em paralelo elas dividem a CPU e o resultado piora. Com 60 s o
  resultado varia um pouco entre rodadas (pico e ociosidade); diga isso quando a diferença for pequena.
- Scripts temporários ficam fora do repositório (pasta temporária da sessão).

## Tela

- HTML/JS puro em `web/static/` (sem build). Rodar o app: `python -m web.app` (porta 5000).
- Playwright do Node já instalado globalmente (`require(\`${npm root -g}/playwright\`)`); não instalar outro.
- Campos numéricos com decimais usam `step="any"` (com `min` e `step` desalinhados o navegador recusa o valor e o
  formulário não envia).

## Git

- Trabalhar na `main` (é o que o usuário usa). Commits com mensagem em português: título curto e lista do que mudou.
- Não colocar o nome do modelo em commits, código ou README.
