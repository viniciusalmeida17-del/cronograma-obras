# Etapa 4 — Mão de obra e duração das atividades

Especificação para o Claude Code. Continua o projeto `cronograma-obras` (etapas 2 e 3 prontas).

## Objetivo

Para cada atividade da obra, calcular:
1. as **horas de trabalho por função** (pedreiro, servente, armador…), a partir das composições de custo que vêm junto da planilha;
2. as **horas de equipamento** (trator, retroescavadeira…);
3. se a atividade é feita pela **equipe própria** ou é **terceirizada**;
4. a **duração com a equipe padrão**.

E para a obra toda: total de horas por função, média de pessoas necessária no prazo da licitação e a equipe indireta fixa (engenheiro, encarregado…).

Nesta etapa **ainda não há datas** nem escolha do tamanho ideal das equipes. Isso é a etapa 5 (cronograma e otimização). Aqui só se calcula quanto trabalho cada atividade tem.

## Decisões do usuário (engenheiro) que valem para esta etapa

- **Jornada**: hoje 44 h/semana. Vai mudar para 42 h e depois 40 h (redução da jornada). A jornada tem que ser um parâmetro da obra, e já deve aceitar mudanças por data.
- **Produtividade**: usar os coeficientes das composições da própria planilha. Nem toda planilha traz composições, então é preciso ter alternativas (item 4).
- **Rendimento abaixo da tabela**: aplicar um fator para a obra terminar antes do previsto. Padrão: **90%**, ou seja, as horas da tabela são divididas por 0,90 (11% a mais de horas).
- **Terceirizados** entram só como custo e prazo, sem contar como funcionários próprios. Normalmente são parte da estrutura metálica, da elétrica e da hidráulica. Alguns serviços às vezes são próprios e às vezes terceirizados (ex.: assentamento de porcelanato), por isso o app precisa perguntar em cada obra.

## Arquivos que acompanham esta especificação

| Arquivo | Onde colocar | O que mudou |
|---|---|---|
| `biblioteca_atividades.xlsx` | substituir `dados/biblioteca_atividades.xlsx` | 4 colunas novas na aba Atividades: `execucao_padrao`, `equipe_padrao`, `equipe_max`, `duracao_fixa_dias` (explicadas na aba Legenda). O resto está igual à versão da etapa 3. |
| `funcoes.xlsx` | `dados/funcoes.xlsx` (novo) | Tabela que diz quais linhas das composições são mão de obra e de qual função. |

O carregador da biblioteca (etapa 3) precisa aceitar as colunas novas. Colunas vazias usam os padrões: `equipe_padrao` = 2, `equipe_max` = 6.

## 1. Ler as composições

O app procura composições em **todas as abas da pasta de trabalho**, menos a aba da planilha orçamentária já lida na etapa 2. Mostrar ao usuário em quais abas encontrou composições e quantas.

### Formato A — abas por disciplina (ex.: FUNDAÇÃO, ALVENARIA, ELÉTRICA)
- **Início do bloco**: linha em que a coluna B tem o número de um item da planilha (ex.: `7.2`) e a mesma linha tem os cabeçalhos `UNIDADE`, `CONSUMO`, `PREÇO`, `PREÇO TOTAL`. Localizar as colunas pelo texto do cabeçalho; código e descrição do insumo ficam nas duas colunas antes de `UNIDADE`.
- **Linhas do bloco**: código, descrição, unidade, coeficiente (consumo), preço, total.
- **Fim do bloco**: linha com `PREÇO TOTAL` na coluna de preço.
- Ignorar linhas vazias dentro do bloco.

### Formato B — aba CPU (composições próprias)
- Blocos que começam com a célula `Item:`. O código da composição (ex.: `COMP-07`) fica na célula à direita; o número do item da planilha fica duas linhas abaixo, na coluna B.
- Seções `MÃO-DE-OBRA`, `EQUIPAMENTO` e `MATERIAL / SERVIÇO`, cada uma com descrição, ref., código, unidade, quantidade, custo e total. O bloco termina na linha `TOTAL`.
- Usar o formato B **só para itens que não tiverem composição no formato A**. Na planilha de teste, as 65 composições próprias aparecem nos dois formatos, e o formato A tem prioridade.

### Números
Os coeficientes vêm em formatos misturados, às vezes na mesma aba: `1,2434000`, `4.789,18`, `1.6898`, `0.5` ou número do Excel. Regra: se o texto tem vírgula, os pontos são separadores de milhar e a vírgula é decimal; se não tem vírgula, o ponto é decimal.

Na planilha de teste, **os 374 serviços têm composição** no formato A.

## 2. Identificar mão de obra e equipamento

### Mão de obra
Uma linha da composição é mão de obra quando:
1. a descrição bate com uma linha da `funcoes.xlsx`: o **primeiro termo** precisa estar no **começo** da descrição (sem acento, maiúsculas), e os termos seguintes (separados por `&`) em qualquer parte; vale a primeira linha da tabela que servir; **e**
2. a unidade é `H`, `HORA`, `MÊS`, vazia ou um número (algumas composições SETOP trazem a quantidade repetida na coluna de unidade); **e**
3. não é equipamento (unidade `CHP`/`CHI` ou descrição começando com `CHP`/`CHI`).

O coeficiente é **horas por unidade do serviço**. Linhas de categoria `indireta` (engenheiro, encarregado, técnico, vigia) **só contam nas atividades indiretas** (item 7); em composições de serviço, ignorar.

Exemplo, item `7.2` (alvenaria, 391,64 m²): Pedreiro 0,99 h/m² e Servente 0,495 h/m².

### Equipamento
Linhas com unidade `CHP` ou `CHI`, ou descrição começando com `CHP`/`CHI`. Somar CHP + CHI (tempo em que a máquina fica na obra) por descrição do equipamento. Não entra na contagem de pessoas, mas limita a duração (item 6).

## 3. Composições dentro de composições

Muitas composições usam outras composições como insumo. Exemplo: a arquibancada (`5.1.14`) usa armação (`92761`, `92762`), massa única (`87529`), graute (`COMP-07`), chapisco (`87893`), alvenaria estrutural (`ED-48202`) etc. A mão de obra dessas partes não aparece na composição principal.

Regra:
1. Se o **código do insumo** é o código de algum item da planilha, que portanto tem composição no arquivo, **expandir**: horas da subcomposição × coeficiente do insumo. Repetir em profundidade, evitando laços.
2. Se não está no arquivo, procurar no **banco de coeficientes** (item 4).
3. Se não achar, registrar como **subcomposição pendente**, quando a descrição indicar um serviço e não um material: contém `EXECUÇÃO`, `ASSENTAMENTO`, `INSTALAÇÃO`, `APLICAÇÃO`, `APLICADO`, `LANÇAMENTO`, `ARMAÇÃO`, `ALVENARIA`, `CHAPISCO`, `EMBOÇO`, `MASSA`, `CONTRAPISO`, `LAJE`, `ARGAMASSA`, `GRAUTE`, `TRATAMENTO`, `CONCRETAGEM` ou `MONTAGEM`. Essa lista de palavras deve ficar num arquivo de configuração fácil de editar.

Exemplo esperado para `5.1.14` (por metro): Pedreiro ≈ 6,1654 h, Servente ≈ 3,4437 h, Armador ≈ 0,5027 h, vindos da expansão de 92761 (→ item 6.8), 92762 (→ 5.1.4), 87529 (→ 14.4) e COMP-07 (→ 6.12). Ficam pendentes pelo menos `ED-48202` (alvenaria estrutural), `87893` (chapisco) e `101963` (laje).

## 4. Quando falta a mão de obra (ordem de busca)

Para cada serviço, a origem das horas fica registrada:

1. `composicao`: linhas de mão de obra da própria composição, incluindo as expandidas do item 3.
2. `banco`: **banco de coeficientes** do app. Toda vez que uma planilha com composições é importada, o app guarda as horas por unidade e por função de cada código (base + código). Assim, uma planilha futura **sem composições** aproveita o que já foi lido em obras anteriores. Também guarda o que o usuário digitar à mão (origem 5).
3. `estimado`: estimativa grosseira para o que sobrou (serviço sem nenhuma mão de obra, ou subcomposição pendente):
   - razão = horas ÷ custo (R$ sem BDI) dos serviços **completos** da mesma atividade; se não houver, da mesma etapa da biblioteca; se não houver, da obra toda;
   - horas estimadas = custo da parte sem mão de obra (para subcomposição pendente, o total daquela linha da composição) × razão;
   - funções divididas na mesma proporção dos serviços completos usados na razão;
   - mostrar em **amarelo**, sempre, para o usuário revisar.
4. `sem_mao_de_obra`: serviço que é só material ou só equipamento (ex.: fornecimento de luminária sem instalação, transporte). Fica com zero horas, sem estimativa. Critério: nenhuma linha de mão de obra e nenhuma subcomposição pendente.
5. `manual`: o usuário digita horas por unidade por função num serviço; isso substitui as outras origens e vai para o banco.

Itens de atividades **indiretas** e **terceirizadas sem horas** não precisam de estimativa.

**Futuro (não fazer agora):** importar a tabela analítica oficial do SINAPI para o banco de coeficientes, resolvendo a maioria das subcomposições pendentes.

## 5. Parâmetros da obra

Tela de parâmetros, com valores salvos por obra:

| Parâmetro | Padrão | Observação |
|---|---|---|
| Horas por semana | 44 | |
| Dias de trabalho por semana | 5 | 5 = segunda a sexta; 6 = com sábado. Horas por dia = horas por semana ÷ dias. |
| Mudanças de jornada | vazio | Lista de "a partir da data X, Y h/semana" (ex.: 42 h, depois 40 h). Guardar agora; a etapa 5 usa semana a semana. Nesta etapa, usar a jornada inicial. |
| Rendimento | 90% | Horas ajustadas = horas ÷ rendimento. Pode ser mudado por atividade. |
| Prazo da licitação | lido na etapa 2 | Só para comparação nesta etapa. |

## 6. Execução e duração por atividade

### Própria ou terceirizada
- Valor inicial vem da coluna `execucao_padrao` da biblioteca: `propria`, `terceirizada` ou `perguntar`.
- Na primeira vez que a obra passa por esta etapa, mostrar as atividades marcadas como `perguntar` (elétrica, hidráulica, porcelanato, revestimento cerâmico, playground…), agrupadas por etapa, com botão "aplicar à etapa inteira". O usuário precisa escolher todas antes de seguir.
- O usuário pode trocar qualquer atividade depois. Salvar por obra.
- **Terceirizada**: as horas continuam sendo calculadas (servem para a duração), mas **não entram na contagem de funcionários próprios**.

### Duração com a equipe padrão (dias úteis)
- **Função principal** = a função com mais horas ajustadas na atividade.
- Equipe: `equipe_padrao` (padrão 2) profissionais da função principal; cada outra função recebe `arredondar para cima(equipe_padrao × horas da função ÷ horas da função principal)`, com mínimo 1 se tiver horas.
- Duração = maior valor entre as funções de `horas ajustadas da função ÷ (pessoas da função × horas por dia)`.
- Equipamentos: duração mínima = horas de cada equipamento ÷ horas por dia (1 máquina de cada). A duração final é a maior entre a das pessoas e a dos equipamentos.
- Arredondar a duração final **para cima**, em dias úteis inteiros.
- Atividade com `duracao_fixa_dias` (cura, testes): usar o valor fixo, em **dias corridos**.
- **Terceirizada sem horas** (ex.: estrutura metálica, piso de PU, guarda-corpos, exaustão): o usuário **digita a duração** em dias úteis. É pendência obrigatória antes da etapa 5.
- O usuário pode mudar a `equipe_padrao` de uma atividade nesta obra e ver a duração recalculada.

Exemplo para testar a fórmula: uma atividade só com o item 7.2, rendimento 90%, 44 h em 5 dias (8,8 h/dia), equipe padrão 2:
- Pedreiro: 387,72 h ÷ 0,9 = 430,80 h; Servente: 193,86 ÷ 0,9 = 215,40 h;
- equipe: 2 pedreiros e arredondar para cima(2 × 215,40 ÷ 430,80) = 1 servente;
- duração = maior entre 430,80 ÷ (2 × 8,8) = 24,48 e 215,40 ÷ (1 × 8,8) = 24,48 → **25 dias úteis**.

## 7. Equipe indireta e resumo da obra

- **Equipe indireta**: das atividades indiretas, ler as linhas de mão de obra de categoria `indireta` com unidade `MÊS` (quantidade = pessoas por mês). Na planilha de teste (item `1.5.1`): Engenheiro 0,2; Encarregado 1; Técnico de segurança 1; Vigia 1. Mostrar como equipe fixa durante a obra. Não entram nas horas de produção.
- **Resumo por função** (só equipe própria): horas ajustadas totais e "média de pessoas no prazo da licitação" = horas ÷ (semanas do prazo × horas por semana), com semanas = meses × 4,33. É uma referência; o número real por semana sai na etapa 5.
- **Cobertura**: percentual do custo da obra (sem indiretas) cujas horas vieram de `composicao`, `banco`, `estimado` e `manual`, para o usuário saber o quanto confiar.

## 8. Telas

1. **Parâmetros da obra** (item 5).
2. **Própria × terceirizada** (item 6), com as pendentes primeiro.
3. **Mão de obra por atividade**: lista das atividades com função principal, horas por função (bruto e ajustado), horas de equipamento, execução, equipe padrão (editável), duração e origem das horas (barra colorida por origem). Ao abrir uma atividade: os serviços com as horas e a origem de cada um, e as subcomposições pendentes com a opção de digitar horas por unidade.
4. **Resumo da obra**: equipe indireta, resumo por função, cobertura, e a lista de pendências obrigatórias (escolhas de execução sem resposta e durações de terceirizadas sem horas).

## 9. Banco de dados

Acrescentar:
- `obra_parametros`: horas por semana, dias por semana, rendimento, mudanças de jornada.
- `servico_mao_de_obra`: serviço, função, horas por unidade, origem.
- `servico_equipamento`: serviço, equipamento, horas por unidade.
- `subcomposicoes_pendentes`: serviço, código, descrição, coeficiente, total da linha, horas estimadas.
- `atividade_execucao`: obra, atividade, própria/terceirizada, rendimento específico (opcional), equipe padrão (opcional), duração manual (opcional).
- `atividade_resumo`: obra, atividade, função principal, horas por função (bruto e ajustado), duração calculada.
- `banco_coeficientes`: base, código, função, horas por unidade, obra de origem, data, origem (planilha ou manual). Não apagar quando a obra é apagada.

## 10. Fora desta etapa

- Datas, Gantt, tamanho ideal de cada equipe, regra de não demitir e encaixe das flexíveis (etapa 5).
- Custos no tempo e critério de pagamento das indiretas (etapa 6).
- Importação da tabela analítica do SINAPI.
- Correções pendentes do leitor de planilha.

## 11. Testes automáticos

Com a planilha de teste e os arquivos novos:

- carrega `funcoes.xlsx` (40 regras) e a biblioteca com as colunas novas;
- encontra composição no formato A para **os 374 serviços**; as abas ELÉTRICA, ALVENARIA, FUNDAÇÃO etc. aparecem na lista de abas com composições;
- leitura de números: `1,2434000` → 1,2434; `4.789,18` → 4789,18; `1.6898` → 1,6898;
- `7.2`: Pedreiro 0,99 h/m² e Servente 0,495 h/m²; horas brutas 387,72 e 193,86;
- `4.5`: Armador 0,151 e Servente 0,049 h/kg (o "AJUDANTE DE ARMADOR" vira Servente);
- `9.1.1.1`: Eletricista 0,029 e Auxiliar de eletricista 0,029 h/m;
- `5.1.14`: expansão das subcomposições com os valores do item 3 (tolerância 0,001) e pelo menos ED-48202, 87893 e 101963 como pendentes;
- `1.5.1`: equipe indireta Engenheiro 0,2, Encarregado 1, Técnico de segurança 1, Vigia 1. A linha "LOCAÇÃO VEÍCULO POPULAR… (ENGENHEIRO E ENCARREGADO)" **não** pode virar Engenheiro;
- nenhuma linha com "COM ENCARGOS" fica sem função reconhecida;
- fórmula de duração: o exemplo do item 6 dá 25 dias úteis;
- rendimento 100% → mesmo exemplo dá arredondar para cima(387,72 ÷ 17,6) = 23 dias úteis;
- EST-03 com 21 dias corridos fixos;
- terceirizada sem horas (MET-01) aparece como pendência obrigatória até receber duração manual;
- banco de coeficientes: depois de importar a planilha de teste, uma cópia da planilha **sem as abas de composição** traz `7.2` com origem `banco` e os mesmos 0,99 / 0,495;
- origem `estimado`: `4.11` (concreto usinado, cuja mão de obra está numa subcomposição de lançamento que não está no arquivo) recebe horas estimadas maiores que zero, marcadas como `estimado`;
- trocar uma atividade `perguntar` para terceirizada tira as horas dela do resumo por função, mas não muda a duração.
