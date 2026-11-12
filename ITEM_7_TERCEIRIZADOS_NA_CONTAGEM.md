# Item 7 — Terceirizados na contagem de pessoas

Especificação para o Claude Code. Projeto `cronograma-obras`, Fase 2 do plano. Itens 1, 2, 3, 3.1 e 6 prontos (último commit `6e247cb`).

Hoje a equipe por semana mostra só a mão de obra **própria**. Os terceirizados também estão no canteiro, e o engenheiro precisa saber quantas pessoas há na obra no total, para dimensionar o canteiro e as áreas de vivência e para conferir o limite de pessoas. Esta rodada passa a contar os terceirizados **identificados pelo serviço**, ex.: "Eletricista (terceirizado): 3", "Telhado (terceirizado): 4".

**Não muda custo nem ociosidade.** O terceirizado é contrato fechado (por m² ou valor global): a contagem é informativa. A única regra nova do otimizador é o limite do canteiro (item 4).

## Arquivo que acompanha esta especificação

| Arquivo | Onde colocar | O que mudou |
|---|---|---|
| `biblioteca_atividades.xlsx` | substituir `dados/biblioteca_atividades.xlsx` | Duas colunas novas: `rotulo_terceirizado` e `pessoas_terceirizado` (item 1); aba Legenda atualizada. **O arquivo novo tem 21 colunas** (as duas últimas são as novas). O resto é igual ao do item 6. |

Ler as colunas pelo nome. Uma biblioteca sem as colunas novas continua valendo (colunas vazias). Manter a migração automática do banco. As obras salvas são de teste: não precisam ser migradas.

---

## 1. Quem é o terceirizado e quantas pessoas ele traz

Vale para toda atividade com execução **terceirizada** na obra: as que já vêm terceirizadas, as `perguntar` que o usuário escolheu terceirizar e as terceirizadas pelo "Procurar melhorias" do item 6.

### 1.1 Nome (`rotulo_terceirizado`)
- Aparece como `<nome> (terceirizado)`.
- Atividades com o **mesmo nome** são da mesma empresa e **somam** na semana (ex.: todas as ELE-* com "Eletricista", SER-01/02/03 com "Serralheria").
- Vazio na biblioteca: usar a função principal da atividade (ex.: "Pedreiro (terceirizado)"); se não houver, o nome da atividade.
- Editável por obra na tela de mão de obra da atividade, com "salvar também na biblioteca padrão" (cópia de segurança antes), como as trocas de função.

Já preenchido no arquivo:

| Nome | Atividades |
|---|---|
| Eletricista | ELE-01 a ELE-08, SPDA-01, TEL-01, INC-01 |
| Bombeiro | HID-01, HID-02, HID-04, HID-05 |
| Cerâmica | REV-03, PIS-02 |
| Serralheria | SER-01, SER-02, SER-03 |
| Terraplenagem, Estacas, Estrutura metálica, Telhado, Piso de PU, Exaustão, Esquadrias de alumínio, Marmoraria, Piso de borracha, Asfalto, Sinalização, Playground | TER-01, FUN-01, MET-01, COB-02, QUA-03, EXA-01, ESQ-01, ACA-01, PEX-04, PAV-02, SIN-01, URB-03 (nessa ordem) |

A IND-03 (topografia) é indireta: fica fora da contagem.

### 1.2 Quantidade de pessoas
Ordem de prioridade, por atividade:
1. **Digitado pelo usuário nesta obra** (campo novo "pessoas do terceirizado" na tela de mão de obra, ao lado da duração e da produção por dia).
2. **Com horas na composição**: a equipe do modo escolhido pelo otimizador (soma das pessoas de todas as funções). Se a duração foi digitada, pessoas = arredondar para cima(horas ÷ (dias úteis × horas por dia)). Guardar o detalhe por função para o tooltip (ex.: "2 eletricistas + 1 ajudante").
3. **Padrão de outras obras**: o último valor digitado para essa atividade em outra obra (mesmo mecanismo da produção por dia da etapa 5.1).
4. **Coluna `pessoas_terceirizado`** da biblioteca.
5. Nenhum: conta **0** e mostra o aviso "sem estimativa de pessoas: digite na mão de obra" na atividade e no resumo.

Mostrar sempre a origem do número (`digitado`, `composição`, `outras obras`, `biblioteca`, `sem estimativa`). O valor digitado numa obra vira o padrão das próximas (item 3 acima), e fica quando a obra é excluída, como os outros padrões.

Valores da coluna `pessoas_terceirizado` (estimativa de prática, para o engenheiro conferir):

| Atividade | Pessoas | Atividade | Pessoas |
|---|---|---|---|
| TER-01 Terraplenagem | 5 | SER-01/02/03 Serralheria | 3 cada |
| FUN-01 Estacas | 4 | ESQ-01 Esquadrias de alumínio | 2 |
| MET-01 Estrutura metálica | 6 | ACA-01 Marmoraria | 2 |
| COB-02 Telhado | 4 | PEX-04 Piso de borracha | 3 |
| QUA-03 Piso de PU | 4 | PAV-02 Asfalto | 8 |
| EXA-01 Exaustão | 2 | SIN-01 Sinalização | 3 |

### 1.3 Terceirizada dividida em partes
Conta só nos dias em que alguma parte está em andamento (item 7.2 da etapa 5.1). Nos intervalos entre as partes, zero.

## 2. Contagem por semana

- Para cada nome de terceirizado e cada semana: o **maior** número de pessoas em algum dia útil da semana (soma das atividades com o mesmo nome em andamento naquele dia).
- **Total na obra por semana** = próprios contratados + soma dos terceirizados.
- Guardar no banco junto do cenário (tabela nova ou colunas novas, como preferir), para não recalcular ao abrir.

## 3. Telas

1. **Equipe por semana**
   - Gráfico: os terceirizados entram empilhados **acima** dos próprios, com cor e padrão diferentes (ex.: tracejado) e legenda `<nome> (terceirizado)`. Botão **Mostrar terceirizados** (ligado por padrão).
   - Linha com o **total na obra** por semana.
   - Tabela semana × função: linhas novas `<nome> (terceirizado)` depois das funções próprias, e a linha **Total na obra**.
   - Ao passar o mouse numa barra de terceirizado: atividades em andamento e pessoas de cada uma.
   - A exportação para Excel inclui as linhas novas.
2. **Resumo do cenário**: além do pico de próprios, **pico total na obra** (com a semana), **pico por terceirizado** e **homem-semana terceirizado**. Lista das atividades terceirizadas "sem estimativa de pessoas".
3. **Comparação de cenários**: coluna nova "Pico total na obra".
4. **Gantt**: no tooltip das barras terceirizadas, "Telhado (terceirizado): 4 pessoas (origem)".
5. **Mão de obra da atividade** (só terceirizadas): campos "nome do terceirizado" e "pessoas do terceirizado", com a origem; ao mudar, recalcular só a contagem (não precisa rodar o otimizador de novo, a não ser que o limite do canteiro esteja ligado).

## 4. Limite de pessoas no canteiro

O parâmetro "máximo de pessoas no canteiro" (`max_pessoas_total`) já existe e hoje vale só para os próprios.
- Opção nova nos parâmetros: **"contar terceirizados no limite do canteiro"**, **ligada por padrão**.
- Ligada: em cada dia útil, próprios contratados na semana + terceirizados em andamento no dia ≤ máximo. Terceirizadas com horas podem ter equipe escolhida pelo otimizador, então o modo entra na conta.
- O diagnóstico de prazo (etapa 5.1) passa a sugerir também "aumentar o máximo do canteiro de X para Y reduz N dias" quando esse limite estiver no caminho crítico.
- Com o máximo vazio, nada muda no otimizador.

## 5. Testes automáticos

Novos, além de manter todos os atuais:
- **Biblioteca**: 21 colunas lidas pelo nome; biblioteca sem as colunas novas carrega.
- **Nome**: ELE-02 e ELE-04 terceirizadas com "Eletricista" somam no mesmo dia; atividade sem nome usa a função principal; sem função, o nome da atividade.
- **Pessoas, prioridade**: digitado > composição > outras obras > biblioteca > sem estimativa (0 com aviso), cada um com a origem certa.
- **Composição com duração digitada**: 176 h, 10 dias úteis, 8,8 h/dia → 2 pessoas.
- **Padrão de outras obras**: digitar 5 em MET-01 numa obra → numa obra nova MET-01 vem com 5, origem `outras obras`; excluir a primeira obra não apaga o padrão.
- **Contagem semanal**: duas atividades do mesmo terceirizado em dias diferentes da mesma semana → vale o maior dia, não a soma da semana.
- **Partes**: terceirizada em 2 partes com intervalo → zero nas semanas do intervalo.
- **Total na obra** = próprios + terceirizados em cada semana; pico total e semana certos.
- **Custo e ociosidade** iguais aos de antes desta rodada para a mesma obra (a contagem não entra no custo).
- **Limite do canteiro**: rede pequena com máximo 10, 8 próprios e um terceirizado de 4 → com a opção ligada, a terceirizada não fica em paralelo com o pico dos próprios; desligada, fica. Sem máximo, resultado igual ao de antes.
- **Diagnóstico**: com o limite do canteiro segurando o prazo, aparece a sugestão de aumentar o máximo com o ganho em dias.
- **Exportação**: Excel da equipe por semana tem as linhas dos terceirizados e o total.
- **Planilha de teste** continua cabendo em 12 meses com os padrões (máximo do canteiro vazio).

## 6. Ao terminar

Rode a planilha de teste com os padrões e informe ao usuário: pico de próprios, pico total na obra (com a semana), os 3 terceirizados com mais pessoas e as atividades sem estimativa de pessoas.

Rode todos os testes, atualize o README, faça o commit e envie para o GitHub.
