# Etapa 2 — Leitor da planilha de licitação

Especificação para o Claude Code. Projeto: app de cronograma de obras a partir de planilha de licitação (versão PC).

## Objetivo

O usuário anexa a planilha orçamentária da licitação (.xlsx) e o app:
1. encontra a aba e as colunas certas;
2. lê os dados gerais da obra (nome, prazo, BDI);
3. separa grupos (títulos) e serviços (itens com preço);
4. confere se os totais batem com a planilha;
5. mostra tudo numa tela de conferência antes de seguir para as próximas etapas.

Nesta etapa o app **só lê e mostra**. Ainda não gera o cronograma.

## Tecnologia sugerida

- Backend em **Python** (`openpyxl` para ler Excel). As etapas seguintes vão usar otimização (OR-Tools), que funciona melhor em Python.
- Interface web local (abre no navegador do PC), para depois reaproveitar a mesma base no tablet.
- O Claude Code pode propor a estrutura do projeto; a regra é manter a leitura da planilha separada da interface (módulo próprio, com testes).

## 1. Escolha da aba

- Procurar uma aba chamada `PLANILHA` (sem diferenciar maiúsculas/minúsculas nem acentos).
- Se não achar, procurar em todas as abas a linha de cabeçalho (item 2) e sugerir a primeira que tiver.
- Sempre deixar o usuário trocar a aba numa lista.
- Ignorar as demais abas nesta etapa. No arquivo de teste existem `CRONOGRAMA` (cronograma físico-financeiro original), `CPU` (composições), `MEMORIA DE CALCULOS`, `BDI EDIFICAÇÕES` e abas por disciplina. **Não usar o CRONOGRAMA como base**: ele servirá só para comparação numa etapa futura.

## 2. Linha de cabeçalho e colunas

Procurar, nas primeiras ~30 linhas, a linha que contém ao mesmo tempo um texto de ITEM, de DESCRIÇÃO, de UNIDADE e de QUANTIDADE. Mapear as colunas pelo nome (não pela posição), aceitando variações:

| Campo | Textos aceitos no cabeçalho |
|---|---|
| item | ITEM |
| base | REF., REFERÊNCIA, FONTE, BASE |
| codigo | CODIGO, CÓDIGO, CÓD. |
| descricao | SERVIÇO, DESCRIÇÃO, DISCRIMINAÇÃO |
| unidade | UND, UNID, UNIDADE |
| quantidade | QUANT., QUANTIDADE, QTD |
| preco_unit | VALOR UNITÁRIO (sem "BDI") |
| preco_unit_bdi | VALOR UNITÁRIO (COM BDI) |
| total | CUSTO TOTAL, VALOR TOTAL (sem "BDI") |
| total_bdi | CUSTO TOTAL (COM BDI) |

- Comparar sem acento, sem diferenciar maiúsculas e ignorando quebras de linha (no arquivo de teste o cabeçalho tem `VALOR UNITÁRIO \n(COM BDI)`).
- Se faltar alguma coluna obrigatória (item, descricao, unidade, quantidade), mostrar uma tela para o usuário apontar a coluna manualmente.
- No arquivo de teste: cabeçalho na **linha 10**, colunas **B a K**.

## 3. Dados gerais da obra

Procurar acima do cabeçalho, pelos rótulos, e mostrar em campos **editáveis**:

| Dado | Como achar | Valor no arquivo de teste |
|---|---|---|
| Nome da obra | célula à direita de `OBRA:` | CONSTRUÇÃO DO CENTRO ESPORTIVO E PRAÇA DE LAZER… |
| Prazo | célula abaixo de `PRAZO EXECUÇÃO`; extrair o número e a unidade ("12 MESES" → 12 meses) | 12 meses |
| BDI | célula abaixo de `BDI SERVIÇO` (fração) | 0,2522 (25,22%) |
| Tipo de desoneração | célula abaixo de `TIPO` | DESONERADA |
| Referências de preço | lista abaixo de `REFERÊNCIAS` | SINAPI out/2023, SUDECAP jul/2023, SETOP ago/2023, DNIT jul/2023 |
| Totais da planilha | linha logo abaixo do cabeçalho, colunas de total | R$ 4.527.898,72 / R$ 5.669.771,17 com BDI |

Se não achar algum dado, deixar o campo vazio para o usuário preencher. O **prazo é obrigatório** para as próximas etapas.

## 4. Classificação das linhas

Para cada linha abaixo do cabeçalho:

- **Serviço**: tem `codigo` preenchido **e** `unidade` preenchida **e** `quantidade` > 0.
- **Grupo (título)**: tem `item` e `descricao`, mas não tem `codigo`.
- **Ignorar**: linhas vazias, linhas só com zeros, linhas de total soltas no fim (no teste, linhas 494–495 têm valores sem item nem descrição).

**Hierarquia**: definir o grupo pai pelo **prefixo do número do item**, não pela profundidade. Exemplos reais do arquivo de teste:
- `1.2.1` é serviço dentro do grupo `1.2` (SERVIÇOS PRELIMINARES), que está dentro de `1`.
- `4.2` é serviço direto do grupo `4` (FUNDAÇÃO), que não tem subgrupos.
- `9` e `9.1` são grupos, e `9.1.1` é um subgrupo (CONDUTORES…) com serviços `9.1.1.x`.

O número do item deve ser lido como **texto** (nunca como número: `4.10` não pode virar `4.1`).

## 5. Limpeza dos dados

- Tirar espaços no início e no fim (no teste há `UN ` e descrições começando com espaço).
- Unidade em maiúsculas; tratar `M2/MÊS` e `M2XMÊS` como a mesma unidade.
- Arredondar valores em reais para 2 casas e quantidades para 4 (o Excel traz ruído como `0.6599999999999999`).
- Guardar o número da linha original do Excel em cada registro, para o usuário conferir.

## 6. Natureza do serviço (classificação preliminar)

Marcar automaticamente pela unidade, para as próximas etapas tratarem cada tipo de forma diferente. O usuário pode corrigir.

| Natureza | Regra | Exemplos no teste | Como vai ser tratado depois |
|---|---|---|---|
| producao | qualquer unidade física (M2, M3, M, KG, UN, CJ, T…) | alvenaria, concreto, piso | vira atividade com duração e equipe |
| tempo | MÊS, M2/MÊS, M2XMÊS | administração local, locação de container, andaime | custo distribuído ao longo do prazo, sem equipe de produção |
| transporte | unidade contendo `XKM` | transporte de entulho e de solo | acompanha o serviço de carga/escavação correspondente |
| taxa | % | mobilização e desmobilização (5%) | custo pontual (início/fim), calculado sobre o total |

Resultado esperado no teste: 359 produção, 9 tempo, 5 transporte, 1 taxa.

## 7. Validação dos totais

- Somar `total` e `total_bdi` de todos os serviços e comparar com os totais da planilha (item 3). Tolerância: R$ 1,00.
- Somar os serviços de cada grupo e comparar com o total do grupo, quando o grupo tiver total preenchido e maior que zero (no teste, alguns grupos têm 0 ou vazio no total; nesses casos, não comparar).
- Conferir `quantidade × preco_unit ≈ total` em cada serviço (tolerância de R$ 0,05) e listar as divergências.
- Mostrar um resumo: "374 serviços lidos — total R$ 4.527.898,72 (confere com a planilha)".

## 8. Tela de conferência

- Resumo no topo: obra, prazo, BDI, quantidade de serviços, totais, e um aviso verde/vermelho da validação.
- Árvore de grupos recolhível (grupo → subgrupo → serviços), com o total de cada grupo.
- Colunas dos serviços: item, base, código, descrição, unidade, quantidade, preço unitário, total, natureza.
- Filtros por grupo e por natureza; busca por texto.
- Lista de alertas (colunas não encontradas, totais que não batem, linhas estranhas) com o número da linha do Excel.
- Botão para confirmar e salvar a importação.

## 9. Saída (dados salvos)

Salvar a importação num banco local (SQLite é suficiente) ou arquivo JSON, com:

- **obra**: nome, prazo (valor e unidade), bdi, desoneração, referências, totais da planilha, nome do arquivo, data da importação.
- **grupos**: item, descrição, item do grupo pai, total da planilha.
- **servicos**: linha_excel, item, item do grupo, base, codigo, descricao, unidade, quantidade, preco_unit, preco_unit_bdi, total, total_bdi, natureza.

Campos que as próximas etapas vão acrescentar (já deixar previstos, vazios): `atividade_biblioteca` (ligação com a biblioteca de atividades), `etapa_obra` (para reforma por etapas) e `local` (ambiente).

## 10. Fora desta etapa

- Ligar os serviços à biblioteca de atividades (etapa 3).
- Produtividade e equipes (etapa 4). Observação: a aba `CPU` tem as composições, incluindo as 65 composições próprias (`COMP-xx`), que não existem no SINAPI. Ela deve ser a fonte dos coeficientes de mão de obra nessa etapa.
- Leitura da aba `CRONOGRAMA` para comparação (futuro).

## 11. Testes automáticos

Usar o arquivo `Concorrencia_2_2024_PLANILHA_ORCAMENTARIA_EDITAVEL.XLSX` como teste principal. O arquivo `itens_extraidos_teste.csv` (separado por `;`) traz a saída esperada dos 374 serviços. Verificar:

- aba `PLANILHA` escolhida; cabeçalho na linha 10;
- prazo = 12 meses; BDI = 0,2522;
- 374 serviços; total = 4.527.898,72; total com BDI = 5.669.771,17;
- `1.1.1` (COMP-65): unidade `%`, quantidade 0,05, natureza `taxa`;
- `4.2` (ED-29802) com grupo pai `4`;
- `4.10` lido como texto, diferente de `4.1`;
- `9.1` classificado como grupo (sem código);
- `1.2.2` com unidade `UN` (sem espaço);
- natureza: 359 produção, 9 tempo, 5 transporte, 1 taxa;
- cada linha do CSV de teste bate com o que o leitor extraiu.

Testar também com uma cópia do arquivo em que as colunas mudem de posição, para garantir que o mapeamento é feito pelo nome.
