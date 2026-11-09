# Etapa 5 — Cronograma, equipes por semana e comparação de prazos

Especificação para o Claude Code. Continua o projeto `cronograma-obras` (etapas 2, 3 e 4 prontas).

## Objetivo

Com a rede de atividades (etapa 3) e as horas por função e as durações (etapa 4), o app:
1. gera o **cronograma com datas**, respeitando dependências, esperas e o prazo;
2. escolhe o **tamanho da equipe de cada atividade**;
3. calcula **quantas pessoas de cada função a empresa precisa ter contratadas em cada semana**, seguindo a regra de não demitir e recontratar;
4. encaixa as **atividades flexíveis** nas semanas com menos serviço;
5. **compara prazos diferentes** (ex.: 10, 11, 12 meses) e mostra qual custa menos, se terminar mais cedo com mais gente vale a pena.

## Regras definidas pelo usuário (engenheiro)

- **Não demitir e recontratar, por função**: o número de pessoas contratadas de cada função **só aumenta até um pico e depois só diminui**. Cada função entra uma vez e sai uma vez, aos poucos. Ex.: o eletricista pode sair quando a elétrica acabar, mas a obra nunca tem 5 numa semana, 3 na seguinte e 5 de novo. Quem está contratado é pago mesmo sem serviço.
- **Atividades rígidas** começam **até 5 dias úteis** depois de liberadas (todas as anteriores terminadas, com as esperas). Esse limite é um parâmetro da obra (padrão 5).
- **Atividades flexíveis** podem ser feitas em qualquer momento entre a liberação e o início das que dependem delas. O otimizador escolhe.
- Terminar antes é desejável: o rendimento de 90% da etapa 4 já dá folga, e a comparação de prazos mostra o ganho de terminar mais cedo.

## 1. Calendário

- **Data de início da obra**: parâmetro obrigatório da obra.
- **Dias úteis**: conforme "dias por semana" da etapa 4 (5 = segunda a sexta; 6 = com sábado).
- **Feriados**: nacionais fixos e móveis (Carnaval segunda e terça, Sexta-feira Santa, Corpus Christi), calculados pelo ano, mais uma lista editável de feriados locais por obra.
- **Jornada por semana**: usar as "mudanças de jornada" da etapa 4 (ex.: 44 h, depois 42 h a partir de uma data, depois 40 h). As horas de cada dia útil dependem da semana.
- As esperas da biblioteca (`+3d`, `+28d`) são **dias corridos**. A `duracao_fixa_dias` (cura, testes) também. Duração de atividade com equipe é em **dias úteis**.
- **Semana** = segunda a domingo. Os gráficos e a contagem de pessoas são por semana.

## 2. Opções de cada atividade (modos)

Para cada atividade **própria** com horas:
- tamanhos possíveis de equipe: de 1 até `equipe_max` profissionais da função principal (padrão 6);
- para cada tamanho, as outras funções acompanham na proporção das horas (mesma regra da etapa 4: arredondar para cima, mínimo 1);
- duração de cada modo pela fórmula da etapa 4, considerando as horas por dia do calendário. Se a jornada muda no meio da atividade, aceitar a aproximação de usar a jornada da semana de início;
- a equipe fica **constante** durante a atividade, e a atividade **não é interrompida** depois de começar.

**Terceirizadas**: um único modo, com a duração calculada na etapa 4 ou digitada pelo usuário. Não usam a equipe própria.

**Aguardar / duração fixa**: um modo, sem equipe.

**Indiretas**: não entram no cronograma como barras de serviço. O período delas (`periodo_de` / `periodo_ate`) é calculado depois, a partir das datas das atividades de referência.

O usuário pode **travar** o tamanho de equipe de uma atividade (ex.: "fundação sempre com 3 armadores"); aí ela tem um modo só.

## 3. O que o otimizador decide e as restrições

Variáveis:
- início de cada atividade (dia útil) e o modo (tamanho da equipe);
- contratados de cada função em cada semana `C[f][s]`, número inteiro ≥ 0.

Restrições:
1. **Dependências**: início ≥ término da anterior + espera (convertida para o calendário).
2. **Rígidas**: início ≤ liberação + limite (padrão 5 dias úteis). A liberação é o maior término de anterior + espera.
3. **Capacidade**: em cada dia útil, a soma das pessoas da função f nas atividades próprias em andamento ≤ `C[f][semana do dia]`.
4. **Sobe e desce uma vez** (por função): existe uma semana de pico `p_f` tal que `C[f][s] ≤ C[f][s+1]` antes do pico e `C[f][s] ≥ C[f][s+1]` depois. Antes da primeira e depois da última atividade da função, `C` pode ser 0.
5. **Prazo**: término da LIM-01 ≤ data limite do cenário.
6. Opcional por obra: **máximo de pessoas por função** (ex.: canteiro comporta no máximo 25 pessoas, ou no máximo 4 carpinteiros).

Objetivo (minimizar, em reais):
- **mão de obra própria paga** = Σ funções Σ semanas `C[f][s]` × horas da semana × custo por hora da função. Inclui as horas paradas, que são o custo de não demitir;
- **indiretos por tempo**: ver item 5;
- desempate pequeno: terminar mais cedo.

Como as flexíveis não têm início fixo, o otimizador naturalmente as coloca onde a equipe contratada estaria parada. É o "encaixar nas semanas com menos serviço".

### Como resolver
- Sugestão: **OR-Tools CP-SAT**, com intervalos opcionais por modo (um modo ativo por atividade), restrição cumulativa por função contra a capacidade semanal variável e o perfil de sobe-e-desce codificado com variáveis booleanas "já passou do pico" que não voltam a falso.
- Tempo limite por cenário: parâmetro (padrão 60 s), com barra de progresso. Mostrar se a solução é ótima ou a melhor encontrada no tempo.
- Gerar antes uma **solução inicial** rápida (cada atividade o mais cedo possível, com a equipe padrão) e passá-la como dica ao solver. Se o solver não achar nada melhor, essa solução é exibida.
- **Atenção à instalação**: o computador do usuário usa Python 3.15. Antes de tudo, confirmar que `py -m pip install ortools` funciona nessa versão. Se não houver pacote para 3.15, configurar o projeto para rodar em Python 3.13 ou 3.14 (`py install 3.14` e um ambiente virtual), e atualizar o README com os comandos para o Windows.

### Quando não cabe no prazo
Se o cenário for impossível (nem com a equipe máxima a obra termina na data), informar: "não cabe em X meses", qual o menor prazo possível com equipe máxima e quais atividades formam o caminho crítico.

## 4. Custos por hora das funções

- Valor inicial: média, ponderada pelas horas, do **custo horário com encargos** das linhas de mão de obra das composições (ex.: Pedreiro R$ 24,43/h e Servente R$ 17,77/h, na planilha de teste).
- Tela para o usuário trocar pelos valores reais da empresa. Salvar por obra e lembrar o último valor usado como padrão para a próxima obra.

## 5. Indiretos que dependem do prazo (aproximação)

Para a comparação de prazos, só importa o que **muda** com a duração:
- Itens de indiretas com unidade `MÊS` (administração local, containers, banheiros, topografia):
  - se o período é a obra toda (`INICIO_OBRA` → `FIM_OBRA`): custo por mês = valor total sem BDI ÷ prazo da licitação em meses; custo no cenário = custo por mês × meses do cenário;
  - se o período é entre atividades (ex.: topografia de TER-01 a FUN-04): custo por mês = valor total ÷ quantidade (a quantidade é o número de meses previsto); custo no cenário = custo por mês × duração real do período.
- Itens `M2/MÊS` ou `M2XMÊS` (andaime, escoramento): mesmo raciocínio do período entre atividades, considerando previsto = prazo da licitação × (fração do período). Se ficar complicado, tratar como custo fixo e marcar "não varia com o prazo nesta versão".
- Itens `%` (taxa de mobilização) e o resto: custo fixo, não entram na comparação.

Isso é uma aproximação. A etapa 6 vai tratar medição e critério de pagamento das indiretas, que é uma pendência já registrada.

## 6. Cenários e comparação de prazos

- Cenário principal: prazo da licitação (ex.: 12 meses).
- O usuário escolhe outros prazos para comparar (padrão: prazo − 3, − 2, − 1 e o próprio prazo, em meses) e pode digitar qualquer um.
- Rodar o otimizador para cada cenário e mostrar uma tabela:

| Coluna | O que é |
|---|---|
| Prazo do cenário | meses e data limite |
| Término previsto | data da LIM-01 |
| Pico de pessoas | maior total semanal de próprios |
| Homem-semana pago | soma de `C` |
| Ociosidade | % das horas pagas sem serviço |
| Mão de obra própria | R$ |
| Indiretos por tempo | R$ |
| Total que varia com o prazo | R$ |
| Diferença para o prazo da licitação | R$ e % (positivo = economia) |
| Situação | ótimo / melhor encontrado / impossível |

- Destacar o cenário mais barato e permitir escolher qual vira o **cronograma da obra**, que é salvo.

## 7. Telas

1. **Parâmetros do cronograma**: data de início, feriados locais, limite das rígidas, custos por hora, máximo de pessoas (opcional), tempo limite do solver.
2. **Cenários**: escolher prazos, botão "calcular", tabela comparativa (item 6), escolher o cenário da obra.
3. **Gantt** do cenário escolhido:
   - barras por atividade, agrupadas por etapa, com cores por tipo (rígida, flexível, aguardar, terceirizada em outra cor);
   - ao passar o mouse: datas, equipe (ex.: "2 pedreiros + 1 servente"), duração e folga;
   - linhas do caminho crítico destacadas;
   - períodos das indiretas como faixas finas no topo;
   - **somente visualização** nesta etapa. Arrastar atividades fica para depois.
4. **Equipe por semana**:
   - gráfico de barras empilhadas, com pessoas contratadas por função em cada semana, e a parte ocupada vs parada destacada;
   - tabela semana × função com `C[f][s]`, e as semanas de entrada, pico e saída de cada função;
   - equipe indireta (etapa 4) como linha separada;
   - exportar a tabela para Excel.
5. **Resumo**: término, pico, ociosidade, custo de mão de obra própria e indiretos por tempo.

## 8. Banco de dados

Acrescentar:
- `obra_calendario`: data de início, dias por semana, feriados locais, limite das rígidas, custos por hora por função, máximo de pessoas.
- `cenarios`: obra, prazo, situação do solver, custos, pico, ociosidade, data e hora do cálculo, escolhido (sim/não).
- `cenario_atividades`: cenário, atividade, início, término, modo (equipe por função).
- `cenario_equipe_semana`: cenário, semana (data da segunda-feira), função, contratados, horas ocupadas.

## 9. Fora desta etapa

- Arrastar atividades no Gantt e recalcular (próxima etapa de ajuste manual).
- Fluxo de caixa, medições, curva S e critério de pagamento das indiretas (etapa 6).
- Correções pendentes do leitor de planilha.

## 10. Testes automáticos

Com **redes pequenas de teste**, criadas no próprio teste, com resultado conhecido:
- **Dependência e espera**: A (5 dias úteis) → B com `A+3d` começando numa segunda: B começa no primeiro dia útil depois de 3 dias corridos do término de A.
- **Feriado**: atividade de 5 dias úteis atravessando o Carnaval termina 2 dias úteis depois do normal.
- **Rígida**: B rígida liberada no dia 10 começa entre o dia 10 e o dia 15 (limite 5).
- **Flexível no vale**: duas atividades rígidas em sequência com 2 pedreiros e um vale de 1 pedreiro entre elas; uma flexível de 1 pedreiro com janela larga deve ser colocada no vale, sem aumentar o pico.
- **Sobe e desce**: em todas as soluções, para cada função, a série `C[f][s]` não tem "vale" (não diminui e depois aumenta).
- **Capacidade**: em todo dia útil, a ocupação ≤ contratados.
- **Terceirizada**: não aparece na equipe por semana.
- **Prazo impossível**: rede cujo caminho crítico mínimo é de 30 dias úteis, com prazo de 20, dá "impossível" e informa os 30 dias.
- **Jornada**: com 44 h, depois 40 h a partir de uma data, a mesma atividade dura mais quando começa depois da mudança.
- **Equipe travada**: atividade travada em 3 usa sempre 3.

Com a **planilha de teste**:
- o cenário de 12 meses termina dentro do prazo e respeita todas as restrições acima (verificar por código, não por números exatos);
- a tabela de comparação tem uma linha por prazo, e os prazos impossíveis aparecem como impossíveis;
- os períodos das indiretas são calculados (ex.: topografia de TER-01 a FUN-04).
