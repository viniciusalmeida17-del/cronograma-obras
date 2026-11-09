# Etapa 5.1 — Rodada de correções

Especificação para o Claude Code. Projeto `cronograma-obras`, etapas 2 a 5 prontas.

O usuário (engenheiro) testou a etapa 5 com a planilha da Concorrência 2/2024 e encontrou problemas. Esta rodada corrige esses problemas e as pendências anotadas desde a etapa 2, antes de o app ser testado com outras planilhas. **Ainda não há etapa nova**: é tudo correção e melhoria do que existe.

Resultado do teste do usuário, para referência: o app disse que a obra só cabe em **28 meses** (o prazo da licitação é 12) e a ociosidade ficou em **61,7%**.

## Arquivos que acompanham esta especificação

| Arquivo | Onde colocar | O que mudou |
|---|---|---|
| `biblioteca_atividades.xlsx` | substituir `dados/biblioteca_atividades.xlsx` | Dependências início-início (item 3), EST-03 com 28 dias, coluna nova `tipo_producao`, TER-01 e SIN-01 terceirizadas, HID-03 = 2 dias e TES-01 = 5 dias. **Conferir que o arquivo novo tem 16 colunas** (a última é `total_com_bdi_teste`). |
| `funcoes.xlsx` | substituir `dados/funcoes.xlsx` | Funções reduzidas às da empresa e nova aba **Juntar funções** (item 6). |
| `produtividade_referencia.xlsx` | `dados/produtividade_referencia.xlsx` (novo) | Coeficientes SINAPI pesquisados para subcomposições pendentes (item 8). |

Sempre que mudar o significado de uma coluna, manter compatibilidade com obras já salvas (migração automática do banco, como nas etapas anteriores).

---

## 1. O prazo da licitação é obrigatório

Hoje o app conclui "só cabe em 28 meses". O usuário precisa do cronograma em **12 meses**, e para isso aceita aumentar equipes, frentes e máquinas.

1. O cenário do prazo da licitação é o **cenário principal** e tem que ser gerado.
2. Os itens 3, 4 e 5 (dependências início-início, concretagem por caminhões e equipes maiores) devem fazer o prazo caber na planilha de teste. **Meta: com os padrões desta especificação, a planilha de teste cabe em 12 meses.** Para o teste, usar durações digitadas para as terceirizadas sem horas, ex.: MET-01 40, QUA-03 15, SER-02 20, ESQ-01 5, EXA-01 5 e PEX-04 5 dias úteis. Se não couber, **não ajustar o teste para passar**: relatar ao usuário o diagnóstico (item 3 abaixo) e o que está limitando.
3. Se mesmo assim não couber, o app **não para em "impossível"**. Ele mostra um **diagnóstico**:
   - o menor prazo possível com os limites atuais;
   - as atividades do caminho crítico, cada uma com a duração, a equipe usada / equipe máxima e as máquinas usadas;
   - sugestões concretas, ordenadas pelo ganho de dias: "aumentar equipe máxima da EST-01 de 20 para 30 reduz 12 dias", "TER-01 com 6 caminhões reduz 25 dias", "digitar a duração da MET-01 (terceirizada)". Calcular cada sugestão de verdade (recalcular só o caminho crítico com aquele limite alterado);
   - botão para aplicar a sugestão e recalcular.
4. Os cenários de comparação são **só iguais ou menores** que o prazo da licitação (padrão: prazo, −1, −2 e −3 meses). Não gerar cenários maiores que o prazo: lucro só interessa dentro do prazo.

## 2. Receita (planilha) × custo real da empresa

Os valores da planilha são o que o **cliente paga** à empresa (receita). **Não são o custo da empresa.** A análise de lucro tem que comparar os dois.

### 2.1 Custos reais (novos parâmetros da obra, com padrão salvo para as próximas obras)
- **Mão de obra própria, por função**: salário mensal + percentual de encargos (padrão sugerido, editável: 80%). Custo por hora = salário × (1 + encargos) ÷ horas pagas no mês (horas por semana × 4,33). Enquanto o usuário não preencher, usar o custo horário das composições e mostrar o aviso **"custos de mão de obra de referência da licitação, não os reais"**.
- **Indiretos reais por mês**: lista editável (ex.: engenheiro, encarregado, técnico de segurança, vigia, aluguel de containers, banheiros, veículo). Valor inicial = os valores da planilha, com o mesmo aviso.
- **Terceirizados**: valor contratado por atividade (padrão = valor da planilha sem BDI, com aviso). É custo fixo, não muda com o prazo.

### 2.2 Receita que depende do prazo (pendência registrada)
Cada indireta da planilha recebe um **critério de pagamento**, escolhido por obra:
- `proporcional à execução` (padrão): a medição paga a indireta na proporção do avanço físico. A receita total é a mesma, mesmo se a obra terminar antes;
- `mensal`: paga um valor por mês enquanto a obra durar. Se terminar antes, recebe menos;
- `fixo`: valor único (ex.: taxa de mobilização).

### 2.3 Comparação de cenários (substitui a tabela da etapa 5)

| Coluna | O que é |
|---|---|
| Prazo / término | igual à etapa 5 |
| Pico de pessoas, homem-semana, ociosidade | igual à etapa 5 (ociosidade conforme o item 7) |
| Receita que varia com o prazo | indiretas com critério `mensal` |
| Custo real que varia com o prazo | mão de obra própria paga + indiretos reais por mês × duração |
| **Resultado** | receita variável − custo variável |
| Diferença para o cenário principal | R$ e % |

O otimizador continua minimizando o **custo real** (mão de obra própria paga + indiretos reais por tempo). Deixar claro na tela que é o resultado **da parte que varia com o prazo**, não o lucro total da obra. O lucro total depende de materiais e terceirizados, que entram na etapa de custos.

## 3. Dependências início-início (serviço progressivo)

Na obra real, a escavação de vala começa hoje, em 3 dias já se começa fôrma e armação, e em 5 dias já se concreta, por lotes. Hoje todas as dependências são término-início, o que alonga demais a obra.

### Formato novo da coluna `depende_de` (já usado na biblioteca nova)
`CÓDIGO[:TIPO][+ESPERA]`, separados por vírgula:
- `TIPO` = `TI` (término-início, padrão, pode omitir) ou `II` (início-início);
- `ESPERA` = `+Nd` (dias **corridos**, ex.: cura) ou `+Ndu` (dias **úteis**, andamento do serviço). Sem espera = 0.

Exemplos da biblioteca nova:
- `FUN-03` depende de `FUN-02:II+3du`: fôrma e armação começam 3 dias úteis depois do **início** da escavação;
- `FUN-04` depende de `FUN-03:II+5du`: a concretagem começa 5 dias úteis depois do início das fôrmas;
- `QUA-03` depende de `QUA-02+28d`: o piso de PU começa 28 dias corridos depois do **término** do piso de concreto (cura).

### Regra do II
Se B depende de `A:II+N`:
1. início de B ≥ início de A + N;
2. **término de B ≥ término de A + N**: B não pode acabar antes de A, porque precisa da última parte de A pronta.

### Herança (etapa 3)
Quando uma atividade sai da obra, as dependências herdadas mantêm o tipo do elo **de quem fica** e somam as esperas. Se os dois elos têm unidades diferentes (d e du), converter tudo para dias úteis pelo calendário, arredondando para cima.

### Cura e escoramento
A EST-03 agora tem **28 dias corridos** (tempo para tirar as escoras). Só a REV-01 (chapisco) depende dela. Todo o resto (alvenaria, instalações etc.) segue em paralelo. Conferir que nenhuma outra atividade fica esperando a cura sem necessidade.

### Validação
Aceitar também o formato antigo (`FUN-04+3d` = término-início com 3 dias corridos), para bibliotecas editadas pelo usuário.

## 4. Concretagem por caminhões

Atividades com `tipo_producao = concretagem` (FUN-04, EST-02, QUA-02) têm a duração limitada também pelo concreto que a obra consegue receber por dia:
- novos parâmetros da obra: **volume por caminhão** (padrão 8 m³, editável, ex.: 5 m³) e **caminhões por dia** (padrão 3);
- volume da atividade = soma das quantidades dos serviços dela com unidade M3;
- duração mínima = arredondar para cima(volume ÷ (volume por caminhão × caminhões por dia));
- duração final = maior entre a da mão de obra e a da concretagem.

Com o elo II das fôrmas, isso representa concretar em lotes à medida que as fôrmas ficam prontas.

## 5. Equipes maiores e frentes de trabalho

- `equipe_max` vazio passa a valer **20** (era 6). O usuário pode mudar por atividade.
- Para não pesar o otimizador, os tamanhos testados podem ser 1, 2, 3, 4, 5, 6, 8, 10, 12, 15 e 20, até o `equipe_max`.
- Funções diferentes trabalham ao mesmo tempo na mesma atividade (ex.: um grupo fazendo fôrma e outro armando), como já acontece pela proporção das horas.
- **Máquinas**: a quantidade de máquinas por equipamento (ajuste da etapa 4) também pode ser escolhida pelo otimizador, de 1 até um máximo por atividade (padrão 6). Em atividade **própria**, cada máquina traz 1 **Operador/Motorista**, que entra na equipe por semana como função própria. Em terceirizada, não conta.

## 6. Funções da empresa

A empresa trabalha com: **Servente, Pedreiro, Pedreiro de acabamento, Carpinteiro, Armador, Bombeiro, Eletricista e Pintor**, mais Operador/Motorista quando a máquina é própria.

A `funcoes.xlsx` nova já faz:
- qualquer **ajudante/auxiliar** (de armador, carpinteiro, eletricista, encanador, serralheiro), **jardineiro**, **rasteleiro** e **operador de betoneira** → Servente;
- **azulejista**, **ladrilhista**, **marmorista/graniteiro** e **gesseiro** → Pedreiro de acabamento;
- **calceteiro**, **assentador** e **impermeabilizador** → Pedreiro;
- **encanador** → Bombeiro;
- **telhadista** e **marceneiro** → Carpinteiro.

### Juntar funções (aba nova "Juntar funções")
- Carpinteiro → Pedreiro e Armador → Pedreiro, **ligado por padrão**. Na prática, boa parte desse serviço é feito por pedreiro.
- Na tela de parâmetros da obra: lista das funções com a opção "juntar com…", para ligar ou desligar por obra.
- Quando junta, as horas da função passam para a função de destino **antes** do cálculo de equipes e duração.

Reprocessar as obras salvas com a tabela nova (as funções antigas, como "Auxiliar de eletricista", deixam de existir).

## 7. Ociosidade

### 7.1 Medir direito
- Ociosidade = horas pagas sem serviço ÷ horas pagas, **sem contar feriados** (feriado fica numa coluna separada, "horas pagas em feriado").
- Mostrar **total** e **por função**, numa tabela e no gráfico de equipe por semana (parte parada hachurada, como já está).

### 7.2 Reduzir
Além do item 6, que já reduz bastante:
1. **Funções que podem sair e voltar** (pendência registrada): na tela de parâmetros, para cada função, a opção "pode sair e voltar (transferência para outra obra)". **Padrão ligado para Servente e Pedreiro**, desligado para as outras. Para essas funções, a regra de sobe-e-desce não se aplica, mas:
   - cada redução tem que durar pelo menos **2 semanas** (parâmetro), para evitar ficar trocando gente toda semana;
   - pequeno custo por pessoa que sai ou entra (parâmetro, padrão R$ 0), para o otimizador não ficar mexendo à toa.
2. **Terceirizadas podem ser divididas** (pendência registrada): uma atividade terceirizada pode ser feita em até **3 partes**, cada uma com no mínimo **5 dias úteis**, com intervalos entre elas. O contrato é por m² ou valor fechado, então não muda o custo. A soma das partes = duração da atividade. As dependências valem para a primeira parte (início) e a última (término).
3. O objetivo do otimizador continua sendo o custo real pago, que já penaliza a ociosidade. Acrescentar ao resumo do cenário: **"ociosidade por função"** e as **3 maiores causas**: as funções com mais horas paradas e as semanas em que isso acontece.

Meta da planilha de teste, como **referência para o teste manual** (não como teste automático): ociosidade bem abaixo dos 61,7% atuais.

## 8. Horas erradas: referências de produtividade

Hoje, quando uma subcomposição não está no arquivo, o app estima pelo custo. Isso gera absurdos quando a subcomposição é quase toda material (QUA-02 com ~4.500 h para 876 m² de piso).

### 8.1 Nova origem `referencia` (antes de `estimado`)
Ordem de busca de horas de uma subcomposição: composição no arquivo → **banco de coeficientes** → **referência** → estimado.

`dados/produtividade_referencia.xlsx` traz coeficientes SINAPI pesquisados (com fonte e data base) para subcomposições pendentes da planilha de teste: chapisco 87893, laje pré-moldada 101963, concreto em betoneira 94964 e 102475, lona 97113 e passeio 94991. As descrições de mão de obra passam pela `funcoes.xlsx` (ex.: operador de betoneira → Servente). O usuário pode acrescentar linhas.

### 8.2 Importar a tabela analítica do SINAPI (solução definitiva)
- Tela "Importar SINAPI": o usuário baixa no site da CAIXA a planilha de **composições analíticas** (o arquivo do estado e do mês que quiser) e anexa.
- O app identifica as colunas pelo cabeçalho (código da composição, tipo do item, código do item, descrição do item, unidade, coeficiente) e grava no banco de coeficientes as horas por unidade das linhas de mão de obra de cada composição (base `SINAPI`), expandindo composições auxiliares.
- Como o formato da CAIXA muda de tempos em tempos, a detecção de colunas tem que ser por texto do cabeçalho, com tela de mapeamento manual se não reconhecer, como no leitor de planilha.
- Depois de importar, reprocessar as obras abertas: as subcomposições SINAPI pendentes passam a ter origem `banco`.

### 8.3 Proteção contra estimativa absurda
Na origem `estimado`, se as horas estimadas de um serviço passarem de 3 vezes as horas por unidade da média dos serviços completos da mesma atividade, limitar a esse valor e marcar em **vermelho**: "estimativa limitada, revisar".

### 8.4 Terceirizadas sem horas
Para atividades terceirizadas, o campo de duração manual ganha um auxílio: o usuário pode digitar a **produção por dia** (ex.: "piso de PU: 150 m² por dia") e o app calcula a duração pela quantidade. O valor fica salvo por atividade como padrão para as próximas obras. Vale o mesmo para a terraplenagem (m³ por dia).

## 9. Gantt melhor

- Botões de escala **Dia / Semana / Mês** (padrão Semana), com cabeçalho de datas adequado a cada escala (dias com dia da semana; semanas com a data da segunda-feira; meses com nome e ano).
- Grupos por etapa que **abrem e fecham**, com uma barra-resumo da etapa quando fechada.
- Linha vertical de **hoje** e da **data limite** do cenário.
- Botão para **mostrar/ocultar setas de dependência**, com elos II desenhados diferente dos TI.
- Caminho crítico destacado, com botão para mostrar só o caminho crítico.
- Barras de terceirizadas divididas em partes (item 7.2) desenhadas como segmentos ligados.
- Rolagem horizontal sincronizada com a lista de atividades; nomes das atividades sempre visíveis à esquerda.
- Pode usar uma biblioteca pronta (frappe-gantt, vis-timeline ou similar), desde que funcione **sem internet** (arquivos dentro do projeto).

## 10. Leitor de planilha (pendência registrada)

Algumas planilhas não têm as colunas **sem BDI**, só com BDI, e hoje o leitor acusa vários erros.
- `preco_unit` e `total` (sem BDI) passam a ser **opcionais**.
- Se faltarem e o BDI for conhecido, calcular: sem BDI = com BDI ÷ (1 + BDI), marcado como `calculado`.
- Validação de totais feita só com as colunas que existem. Um único aviso: "planilha sem preços sem BDI; valores sem BDI calculados pelo BDI de X%".
- Teste: cópia da planilha de teste sem as colunas sem BDI → nenhum erro, 374 serviços, total com BDI R$ 5.669.771,17.

## 11. Outros ajustes

- **Data de início** da obra sem valor padrão: é obrigatória antes de calcular, para não gerar cronogramas com datas passadas por engano.
- Atividades `aguardar` (cura) continuam começando assim que liberadas.
- Atualizar o README com o que mudou.

## 12. Testes automáticos

Novos, além de manter todos os atuais:
- **II**: A (10 dias úteis) e B com `A:II+3du` (10 dias úteis) → B começa 3 dias úteis depois de A e termina no mínimo 3 dias úteis depois de A.
- **II impede término antes**: A (20 dias úteis), B com `A:II+2du` e duração 5 → B termina ≥ término de A + 2 dias úteis.
- **Formato antigo** `FUN-04+3d` continua aceito como TI.
- **Herança** com tipos: tirar FUN-03 de uma cópia → FUN-04 depende de `FUN-02:II+8du`.
- **Concretagem**: 120 m³, 8 m³ por caminhão, 3 por dia → duração mínima 5 dias úteis.
- **Equipe máxima** vazia = 20.
- **Funções**: "AJUDANTE DE ARMADOR" → Servente; "AZULEJISTA OU LADRILHISTA" → Pedreiro de acabamento; "ENCANADOR OU BOMBEIRO HIDRÁULICO" → Bombeiro; com "juntar" ligado, as horas de Carpinteiro e Armador da FUN-03 aparecem como Pedreiro.
- **Referência**: na `5.1.14`, o chapisco 87893 passa a ter origem `referencia` (Pedreiro 0,1394 e Servente 0,0465 h/m² × 5,26 m²/m).
- **Limite de estimativa** aplicado e marcado.
- **Sair e voltar**: com Servente transferível, uma rede com vale de 4 semanas reduz Servente no vale; com mínimo de 2 semanas, um vale de 1 semana não reduz.
- **Terceirizada dividida**: atividade de 15 dias úteis dividida em até 3 partes de no mínimo 5; dependências respeitadas no início e no fim.
- **Ociosidade** sem feriados e por função.
- **Planilha de teste cabe em 12 meses** com os padrões e as durações de terceirizadas do item 1 (ver a meta no item 1).
- **Diagnóstico**: rede impossível mostra o caminho crítico e pelo menos uma sugestão com o ganho em dias calculado.
- **Cenários** nunca maiores que o prazo da licitação.
- **Planilha sem colunas sem BDI** (item 10).
