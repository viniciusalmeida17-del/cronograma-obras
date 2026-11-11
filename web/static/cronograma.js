"use strict";

const obraId = obraDaUrl();
const est = { p: null, cmp: null, cen: null, cenId: null, aba: null, timer: null,
  gantt: { escala: "semana", setas: false, soCritico: false, fechadas: new Set() } };
const fmt1 = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
const fmt2 = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });
const SITUACAO = {
  otimo: "ótimo", melhor_encontrado: "melhor encontrado", impossivel: "impossível", sem_solucao: "sem solução no tempo",
};
const ORIGEM_CUSTO = {
  salario: "salário desta obra", obra: "custo/h desta obra", salario_padrao: "salário da última obra",
  ultimo_usado: "custo/h da última obra", composicoes: "composições (referência)",
  composicoes_pedreiro: "custo do pedreiro (referência)", faltando: "falta informar",
};
// paleta categórica fixa (ordem nunca muda); a 8ª posição é "Outras"
const SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6"];
const COR_OUTRAS = "#898781";
const COR_TIPO = { rigida: "#2a78d6", flexivel: "#1baf7a", aguardar: "#898781", terceirizada: "#eb6834" };
const ROTULO_BARRA = { rigida: "rígida", flexivel: "flexível", aguardar: "aguardar / duração fixa", terceirizada: "terceirizada" };
const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
const SEMANA = ["D", "S", "T", "Q", "Q", "S", "S"];
const PX_DIA = { dia: 22, semana: 5, mes: 1.6 };

const dataBR = (iso) => (iso ? iso.slice(8, 10) + "/" + iso.slice(5, 7) + "/" + iso.slice(0, 4) : "—");
const dt = (iso) => new Date(iso + "T00:00");
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const dias = (a, b) => Math.round((dt(b) - dt(a)) / 86400000);
const somaDias = (a, n) => { const d = dt(a); d.setDate(d.getDate() + n); return iso(d); };
const dica = document.createElement("div");
dica.className = "dica";
dica.hidden = true;
document.body.appendChild(dica);

function mostrarDica(e, html) {
  dica.innerHTML = html;
  dica.hidden = false;
  const x = Math.min(e.clientX + 14, window.innerWidth - dica.offsetWidth - 8);
  const y = e.clientY + 14 + dica.offsetHeight > window.innerHeight ? e.clientY - dica.offsetHeight - 10 : e.clientY + 14;
  dica.style.left = x + "px";
  dica.style.top = y + "px";
}
const esconderDica = () => { dica.hidden = true; };

// ------------------------------------------------------------------ carga

async function carregar() {
  if (!obraId) { mensagem($("#msg-geral"), "Abra esta tela a partir da mão de obra (falta ?obra=).", "erro"); return; }
  try {
    est.p = await api(`/api/obras/${obraId}/cronograma/parametros`);
    est.cmp = await api(`/api/obras/${obraId}/cenarios`);
  } catch (err) { mensagem($("#msg-geral"), err.message, "erro"); return; }
  $("#tela").hidden = false;
  desenharTopo();
  desenharParametros();
  desenharCenarios();
  const escolhido = est.cmp.cenarios.find((c) => c.escolhido);
  await escolherVisualizado(escolhido ? escolhido.id : (est.cmp.cenarios.find((c) => c.termino) || {}).id);
  if (!est.aba) est.aba = !est.p.data_inicio ? "parametros" : est.cmp.cenarios.length ? (escolhido ? "gantt" : "cenarios") : "cenarios";
  mostrarAba(est.aba);
  acompanhar();
}

function desenharTopo() {
  const p = est.p;
  $("#nome-obra").textContent = `Obra nº ${p.obra.numero} · ${p.obra.nome || ""}`;
  $("#link-mao-de-obra").href = `/mao-de-obra?obra=${obraId}`;
  const faltaCusto = Object.entries(p.custos).filter(([, v]) => !v.custo_hora).map(([f]) => f);
  const problemas = [];
  if (p.pendencias_etapa4.length) problemas.push(`${p.pendencias_etapa4.length} pendência(s) da mão de obra`);
  if (!p.data_inicio) problemas.push("falta a data de início");
  if (faltaCusto.length) problemas.push("falta o salário de " + faltaCusto.join(", "));
  $("#faixa").className = "faixa " + (problemas.length ? "aviso" : "ok");
  $("#faixa").textContent = problemas.length
    ? "⚠ Antes de calcular: " + problemas.join("; ") + "."
    : `✔ Pronto para calcular. Prazo da licitação (cenário principal): ${p.prazo_licitacao ? fmt2.format(p.prazo_licitacao) + " meses" : "—"}.`;
  $("#avisos-custos").innerHTML = (p.avisos || []).map((a) => `<li>⚠ ${esc(a)}</li>`).join("");
}

function mostrarAba(nome) {
  est.aba = nome;
  $$(".aba").forEach((s) => { s.hidden = s.id !== `aba-${nome}`; });
  $$("#abas button").forEach((b) => b.classList.toggle("ativa", b.dataset.aba === nome));
  esconderDica();
}
$("#abas").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) mostrarAba(b.dataset.aba); });

// ------------------------------------------------------------------ 1. parâmetros

function linhaFeriado(f = {}) {
  const div = document.createElement("div");
  div.className = "mudanca";
  div.innerHTML = `<input type="date" name="feriado_data" value="${esc(f.data || "")}">
    <input type="text" name="feriado_nome" placeholder="nome (ex.: aniversário da cidade)" value="${esc(f.nome || "")}">
    <button type="button" class="secundario pequeno" title="Tirar">✕</button>`;
  $("button", div).addEventListener("click", () => div.remove());
  $("#lista-feriados").appendChild(div);
}

function opcoesPeriodo(valor, padrao) {
  const lista = [padrao, ...(est.p.codigos_sequencia || [])];
  if (valor && !lista.includes(valor)) lista.push(valor);
  return lista.map((v) => `<option value="${esc(v)}" ${v === (valor || padrao) ? "selected" : ""}>${v === "INICIO_OBRA" ? "início da obra" : v === "FIM_OBRA" ? "fim da obra" : esc(v)}</option>`).join("");
}

function linhaIndireto(i = {}) {
  const tr = document.createElement("tr");
  tr.className = "linha-indireto";
  tr.innerHTML = `<td><input type="text" name="ind_desc" value="${esc(i.descricao || "")}" placeholder="ex.: engenheiro, vigia, veículo"></td>
    <td class="num"><input type="number" name="ind_valor" min="0" step="0.01" value="${i.valor_mes ?? ""}"></td>
    <td><select name="ind_de">${opcoesPeriodo(i.de, "INICIO_OBRA")}</select></td>
    <td><select name="ind_ate">${opcoesPeriodo(i.ate, "FIM_OBRA")}</select></td>
    <td><button type="button" class="secundario pequeno" title="Tirar">✕</button></td>`;
  $("button", tr).addEventListener("click", () => { tr.remove(); est.indiretosMudados = true; });
  $("#tabela-indiretos-reais").appendChild(tr);
}

function desenharParametros() {
  const p = est.p;
  const f = $("#form-parametros");
  f.data_inicio.value = p.data_inicio || "";
  f.limite_rigidas.value = p.limite_rigidas;
  f.tempo_limite.value = p.tempo_limite;
  f.max_pessoas_total.value = p.max_pessoas_total ?? "";
  f.maquinas_max.value = p.maquinas_max ?? 6;
  f.dividir_terceirizadas.checked = !!p.dividir_terceirizadas;
  f.encargos.value = p.encargos;
  f.min_semanas_reducao.value = p.min_semanas_reducao ?? 2;
  f.custo_troca.value = p.custo_troca ?? 0;
  f.custo_troca_horas.value = p.custo_troca_horas ?? 8;
  f.custo_troca_tipo.value = p.custo_troca_tipo || "horas";
  mostrarCustoTroca();
  $("#info-dias").textContent = p.dias_semana === 6 ? "6 (com sábado)" : "5 (segunda a sexta)";
  $("#info-jornada").textContent = `${fmt1.format(p.horas_semana)} h/semana` + (p.mudancas_jornada || [])
    .map((m) => `, ${fmt1.format(m.horas_semana)} h a partir de ${dataBR(m.a_partir_de)}`).join("");
  $("#lista-feriados").innerHTML = "";
  (p.feriados_locais || []).forEach(linhaFeriado);
  const entradas = p.entradas || {};
  $("#tabela-custos").innerHTML = p.funcoes.map((fn) => {
    const c = p.custos[fn] || {};
    const sal = (p.salarios || {})[fn] ?? "";
    return `<tr><td>${esc(fn)}</td>
      <td class="num"><input type="number" name="salario" data-funcao="${esc(fn)}" min="0" step="10" value="${sal}" placeholder="${c.salario ? fmt2.format(c.salario) : "—"}"></td>
      <td class="num ${c.referencia ? "referencia-valor" : ""}">${c.custo_hora ? reais(c.custo_hora) : "—"}</td>
      <td class="discreto">${ORIGEM_CUSTO[c.origem] || ""}</td>
      <td class="num discreto">${c.composicoes ? reais(c.composicoes) : "—"}</td>
      <td><select name="entradas" data-funcao="${esc(fn)}">${OPCOES_ENTRADAS.map(([v, t]) => `<option value="${v}" ${Number(entradas[fn] ?? 1) === v ? "selected" : ""}>${t}</option>`).join("")}</select></td>
      <td class="num"><input type="number" name="maximo" data-funcao="${esc(fn)}" min="1" step="1" value="${p.max_por_funcao[fn] ?? ""}" placeholder="—"></td></tr>`;
  }).join("") || `<tr><td colspan="7" class="discreto">Nenhuma atividade própria com horas.</td></tr>`;
  $("#tabela-indiretos-reais").innerHTML = "";
  (p.indiretos_reais || []).forEach(linhaIndireto);
  est.indiretosMudados = false;
  $("#info-indiretos").innerHTML = p.indiretos_referencia
    ? "⚠ Valores iniciais = os da planilha (sem BDI), não os reais. Troque pelos valores da empresa (engenheiro, encarregado, técnico de segurança, vigia, containers, banheiros, veículo...)."
    : "Valores digitados (ficam como padrão para a próxima obra).";
  $("#tabela-terceirizados").innerHTML = (p.terceirizados || []).map((t) => `<tr><td><b>${esc(t.codigo)}</b> ${esc(t.nome || "")}</td>
      <td class="num">${reais(t.planilha)}</td>
      <td class="num"><input type="number" name="terceirizado" data-codigo="${esc(t.codigo)}" min="0" step="0.01" value="${t.contratado ?? ""}" placeholder="${fmt2.format(t.planilha || 0)}"></td></tr>`).join("")
    || `<tr><td colspan="3" class="discreto">Nenhuma atividade terceirizada.</td></tr>`;
  $("#tabela-criterios").innerHTML = (p.criterios || []).map((c) => `<tr><td>${esc(c.descricao.slice(0, 90))}</td><td>${esc(c.unidade || "")}</td>
      <td class="num">${reais(c.total)}</td>
      <td><select name="criterio" data-item="${esc(c.item)}">${["proporcional", "mensal", "fixo"].map((v) => `<option value="${v}" ${c.criterio === v ? "selected" : ""}>${{ proporcional: "proporcional à execução", mensal: "mensal", fixo: "fixo" }[v]}</option>`).join("")}</select></td></tr>`).join("");
  $("#tabela-travas tbody").innerHTML = p.atividades_proprias.map((a) => `<tr>
      <td><b>${esc(a.codigo)}</b> ${esc(a.nome || "")}</td><td>${a.execucao === "terceirizada" ? "terceirizada" : "própria"}</td>
      <td>${esc(a.funcao_principal || "—")}</td><td class="num">${a.equipe_padrao}</td>
      <td class="num">${a.funcao_principal ? `<input type="number" data-limite="equipe_max" data-codigo="${esc(a.codigo)}" min="1" max="200" step="1" value="${a.equipe_max}">` : "—"}</td>
      <td>${a.funcao_principal && a.execucao !== "terceirizada" ? `<select data-trava="${esc(a.codigo)}"><option value="">— otimizador escolhe</option>
        ${Array.from({ length: a.equipe_max }, (_, i) => i + 1).map((n) => `<option value="${n}" ${a.travada === n ? "selected" : ""}>${n} ${esc((a.funcao_principal || "").toLowerCase())}</option>`).join("")}
      </select>` : "—"}</td>
      <td class="num">${a.tem_equipamento ? `<input type="number" data-limite="maquinas_max" data-codigo="${esc(a.codigo)}" min="1" max="50" step="1" value="${a.maquinas_max ?? ""}" placeholder="${p.maquinas_max ?? 6}">` : "—"}</td></tr>`).join("");
  const fc = $("#form-calcular");
  fc.prazos.value = (p.prazos || []).map((x) => fmt2.format(x)).join("; ");
  fc.tempo_limite.value = p.tempo_limite;
}

const OPCOES_ENTRADAS = [[1, "uma entrada"], [2, "até 2 entradas"], [3, "até 3 entradas"], [4, "até 4 entradas"], [0, "livre"]];
const textoEntradas = (n) => (n === 0 ? "livre" : n === 1 ? "uma" : `até ${n}`);

function mostrarCustoTroca() {
  const f = $("#form-parametros");
  const horas = f.custo_troca_tipo.value === "horas";
  f.custo_troca_horas.hidden = !horas;
  f.custo_troca.hidden = horas;
}
$("#form-parametros [name=custo_troca_tipo]").addEventListener("change", mostrarCustoTroca);

$("#btn-add-feriado").addEventListener("click", () => linhaFeriado());
$("#btn-add-indireto").addEventListener("click", () => { linhaIndireto(); est.indiretosMudados = true; });
$("#tabela-indiretos-reais").addEventListener("input", () => { est.indiretosMudados = true; });
$("#btn-indiretos-planilha").addEventListener("click", async () => {
  try {
    est.p = await api(`/api/obras/${obraId}/cronograma/parametros`, { json: { indiretos_reais: "planilha" } });
    desenharTopo();
    desenharParametros();
    mensagem($("#msg-parametros"), "Indiretos voltaram aos valores da planilha.", "ok");
  } catch (err) { mensagem($("#msg-parametros"), err.message, "erro"); }
});

$("#form-parametros").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  const salarios = {};
  $$("input[name=salario]", f).forEach((i) => { if (i.value) salarios[i.dataset.funcao] = i.value; });
  const maximos = {};
  $$("input[name=maximo]", f).forEach((i) => { if (i.value) maximos[i.dataset.funcao] = i.value; });
  const terc = {};
  $$("input[name=terceirizado]", f).forEach((i) => { if (i.value) terc[i.dataset.codigo] = i.value; });
  const criterios = {};
  $$("select[name=criterio]", f).forEach((s) => { criterios[s.dataset.item] = s.value; });
  const feriados = $$("#lista-feriados .mudanca").map((d) => ({ data: $("[name=feriado_data]", d).value, nome: $("[name=feriado_nome]", d).value }))
    .filter((x) => x.data);
  const corpo = {
    data_inicio: f.data_inicio.value, limite_rigidas: f.limite_rigidas.value, tempo_limite: f.tempo_limite.value,
    max_pessoas_total: f.max_pessoas_total.value, feriados_locais: feriados, max_por_funcao: maximos,
    maquinas_max: f.maquinas_max.value, dividir_terceirizadas: f.dividir_terceirizadas.checked,
    encargos: f.encargos.value, min_semanas_reducao: f.min_semanas_reducao.value, custo_troca: f.custo_troca.value,
    salarios, terceirizados: terc, criterios,
    custo_troca_tipo: f.custo_troca_tipo.value, custo_troca_horas: f.custo_troca_horas.value,
    entradas: Object.fromEntries($$("select[name=entradas]", f).map((s) => [s.dataset.funcao, Number(s.value)])),
  };
  if (est.indiretosMudados) {
    corpo.indiretos_reais = $$("#tabela-indiretos-reais tr").map((tr) => ({
      descricao: $("[name=ind_desc]", tr).value, valor_mes: $("[name=ind_valor]", tr).value,
      de: $("[name=ind_de]", tr).value, ate: $("[name=ind_ate]", tr).value,
    })).filter((x) => x.descricao);
  }
  try {
    est.p = await api(`/api/obras/${obraId}/cronograma/parametros`, { json: corpo });
    desenharTopo();
    desenharParametros();
    mensagem($("#msg-parametros"), "Parâmetros salvos. Recalcule os cenários para aplicar.", "ok");
  } catch (err) { mensagem($("#msg-parametros"), err.message, "erro"); }
});

$("#tabela-travas").addEventListener("change", async (e) => {
  const s = e.target.closest("select[data-trava]");
  const lim = e.target.closest("input[data-limite]");
  try {
    if (s) {
      est.p = await api(`/api/obras/${obraId}/cronograma/travar`, { json: { atividade: s.dataset.trava, pessoas: s.value || null } });
      mensagem($("#msg-travas"), `${s.dataset.trava}: ${s.value ? "equipe travada em " + s.value : "otimizador escolhe a equipe"}. Recalcule os cenários.`, "ok");
    } else if (lim) {
      est.p = await api(`/api/obras/${obraId}/cronograma/limites`, { json: { atividade: lim.dataset.codigo, [lim.dataset.limite]: lim.value } });
      mensagem($("#msg-travas"), `${lim.dataset.codigo}: limite salvo. Recalcule os cenários.`, "ok");
    } else return;
    desenharParametros();
  } catch (err) { mensagem($("#msg-travas"), err.message, "erro"); }
});

// ------------------------------------------------------------------ 2. cenários

function desenharCenarios() {
  const cmp = est.cmp;
  $("#tabela-cenarios tbody").innerHTML = cmp.cenarios.map((c) => {
    const ok = c.situacao === "otimo" || c.situacao === "melhor_encontrado";
    const prazo = `<b>${fmt2.format(c.prazo_meses)} meses</b>${c.principal ? ' <span class="selo confirmado">principal</span>' : ""}<br><small class="discreto">até ${dataBR(c.data_limite)}</small>`;
    if (!ok) {
      const mp = c.menor_prazo || {};
      return `<tr class="impossivel"><td>${prazo}</td>
        <td colspan="7">${c.situacao === "impossivel" ? `<b>Não cabe em ${fmt2.format(c.prazo_meses)} meses.</b>` : esc(c.mensagem || "")}
          ${mp.dias_uteis ? ` Menor prazo com os limites atuais: <b>${mp.dias_uteis} dias úteis</b> (${fmt2.format(mp.meses)} meses, término ${dataBR(mp.termino)}).` : ""}
          ${c.diagnostico ? `<button type="button" class="secundario pequeno" data-diag="${c.id}">Ver diagnóstico e sugestões</button>` : ""}</td>
        <td><span class="selo ambiguo">${SITUACAO[c.situacao]}</span></td></tr>`;
    }
    const dif = c.diferenca === null || c.principal ? (c.principal ? "—" : "—") : `${reais(c.diferenca)}<br><small>${fmt2.format(c.diferenca_pct || 0)}%</small>`;
    return `<tr class="${c.melhor_resultado ? "mais-barato" : ""} ${c.escolhido ? "escolhido" : ""}">
      <td>${prazo}<br>término ${dataBR(c.termino)}</td>
      <td class="num">${c.pico}</td><td class="num">${fmt1.format(c.homem_semana)}</td>
      <td class="num">${fmt1.format(c.ociosidade)}%</td>
      <td class="num">${reais(c.receita_variavel || 0)}</td><td class="num">${reais(c.custo_total)}</td>
      <td class="num"><b>${reais(c.resultado)}</b></td>
      <td class="num ${c.diferenca > 0 ? "economia" : ""}">${dif}</td>
      <td><span class="selo ${c.situacao === "otimo" ? "confirmado" : "memoria"}">${SITUACAO[c.situacao]}</span>
        ${c.melhor_resultado ? '<span class="selo confirmado">melhor resultado</span>' : ""}
        <small class="discreto">${fmt1.format(c.segundos || 0)} s</small>
        <div class="botoes-cenario">${c.escolhido ? "<b>✔ cronograma da obra</b>" : `<button type="button" class="secundario pequeno" data-escolher="${c.id}">Usar este</button>`}
        <button type="button" class="secundario pequeno" data-ver="${c.id}">Ver</button></div></td></tr>`;
  }).join("") || `<tr><td colspan="9" class="discreto">Nenhum cenário calculado ainda.</td></tr>`;
  const opcoes = cmp.cenarios.filter((c) => c.termino)
    .map((c) => `<option value="${c.id}">${fmt2.format(c.prazo_meses)} meses${c.escolhido ? " (cronograma da obra)" : ""}</option>`).join("");
  $$(".sel-cenario").forEach((s) => { s.innerHTML = opcoes || "<option value=''>— nenhum cenário —</option>"; if (est.cenId) s.value = est.cenId; });
  const principal = cmp.cenarios.find((c) => c.principal);
  if (principal && principal.diagnostico) desenharDiagnostico(principal);
  else if (!$("#diagnostico").dataset.aberto) $("#diagnostico").innerHTML = "";
}

function desenharDiagnostico(c) {
  const d = c.diagnostico;
  $("#diagnostico").dataset.aberto = c.id;
  $("#diagnostico").innerHTML = `<div class="diagnostico"><h3>Diagnóstico: ${fmt2.format(c.prazo_meses)} meses${c.principal ? " (prazo da licitação)" : ""}</h3>
    <p>Menor prazo possível com os limites atuais: <b>${d.menor_prazo.dias_uteis} dias úteis</b> (término ${dataBR(d.menor_prazo.termino)});
      o prazo tem ${d.dias_uteis_limite} dias úteis. Faltam <b>${d.faltam_dias_uteis}</b> dias úteis.</p>
    <h4>Sugestões (ganho calculado de verdade, recalculando o caminho crítico)</h4>
    ${d.sugestoes.length ? `<ol class="sugestoes">${d.sugestoes.map((s, i) => `<li>${esc(s.texto)}
      <button type="button" class="secundario pequeno" data-sugestao="${c.id}:${i}">Aplicar e recalcular</button></li>`).join("")}</ol>`
      : "<p class='discreto'>Nenhuma sugestão automática reduz o prazo: veja as durações digitadas e as esperas do caminho crítico.</p>"}
    <h4>Caminho crítico</h4>
    <div class="rolagem"><table class="simples"><thead><tr><th>Atividade</th><th>Execução</th><th>Datas</th><th class="num">Duração</th>
      <th>Equipe usada / máxima</th><th>Máquinas usadas / máximo</th><th>Limita</th></tr></thead><tbody>
      ${d.caminho_critico.map((a) => `<tr><td><b>${esc(a.codigo)}</b> ${esc(a.nome || "")}</td><td>${a.execucao === "terceirizada" ? "terceirizada" : "própria"}</td>
        <td class="nowrap">${dataBR(a.inicio)} a ${dataBR(a.termino)}</td>
        <td class="num">${a.duracao} ${a.unidade === "corridos" ? "d corridos" : "du"}</td>
        <td>${a.equipe_max ? `${a.equipe_principal ?? "—"} / ${a.equipe_max}` : "—"}${a.travada ? " (travada)" : ""}</td>
        <td>${a.maquinas_max ? `${Math.max(...Object.values(a.maquinas), 0)} / ${a.maquinas_max}` : "—"}</td>
        <td>${{ mao_de_obra: "mão de obra", equipamento: "máquinas", concretagem: "concretagem", fixa: "duração fixa/digitada" }[a.limitante] || ""}</td></tr>`).join("")}
    </tbody></table></div></div>`;
}

$("#tabela-cenarios").addEventListener("click", async (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  try {
    if (b.dataset.escolher) {
      est.cmp = await api(`/api/obras/${obraId}/cenarios/${b.dataset.escolher}/escolher`, { method: "POST" });
      await escolherVisualizado(Number(b.dataset.escolher));
      desenharCenarios();
      mensagem($("#msg-cenarios"), "Cenário salvo como cronograma da obra.", "ok");
    } else if (b.dataset.ver) {
      await escolherVisualizado(Number(b.dataset.ver));
      mostrarAba("gantt");
    } else if (b.dataset.diag) {
      desenharDiagnostico(est.cmp.cenarios.find((c) => c.id === Number(b.dataset.diag)));
      $("#diagnostico").scrollIntoView({ behavior: "smooth" });
    }
  } catch (err) { mensagem($("#msg-cenarios"), err.message, "erro"); }
});

$("#diagnostico").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-sugestao]");
  if (!b) return;
  const [cid, i] = b.dataset.sugestao.split(":").map(Number);
  const c = est.cmp.cenarios.find((x) => x.id === cid);
  const s = c.diagnostico.sugestoes[i];
  try {
    est.p = await api(`/api/obras/${obraId}/cronograma/sugestao`, { json: { acao: s.acao } });
    desenharParametros();
    mensagem($("#msg-cenarios"), `Aplicado: ${s.texto}. Recalculando…`, "ok");
    await calcular();
  } catch (err) { mensagem($("#msg-cenarios"), err.message, "erro"); }
});

async function calcular() {
  const f = $("#form-calcular");
  const prazos = f.prazos.value.split(/[;\s]+/).map((x) => x.trim().replace(",", ".")).filter(Boolean);
  try {
    const st = await api(`/api/obras/${obraId}/cronograma/calcular`, { json: { prazos, tempo_limite: f.tempo_limite.value } });
    mostrarProgresso(st);
    acompanhar();
  } catch (err) { mensagem($("#msg-cenarios"), err.message, "erro"); }
}
$("#form-calcular").addEventListener("submit", (e) => { e.preventDefault(); mensagem($("#msg-cenarios"), "", ""); calcular(); });
$("#btn-parar").addEventListener("click", () => api(`/api/obras/${obraId}/cronograma/parar`, { method: "POST" }).catch(() => {}));

function mostrarProgresso(st) {
  const melhorias = st.tipo === "melhorias";
  $("#progresso").hidden = !st.rodando || melhorias;
  $("#btn-parar").hidden = !st.rodando;
  $("#btn-calcular").disabled = !!st.rodando;
  $("#btn-melhorias").disabled = !!st.rodando;
  $("#progresso-melhorias").hidden = !(st.rodando && melhorias);
  if (!st.rodando) return;
  if (melhorias) {
    $("#progresso-melhorias").textContent = `Testando a alternativa ${st.cenario + 1} de ${st.n} (até ${st.tempo_limite} s cada)…`;
    return;
  }
  $("#progresso-barra").style.width = Math.round(100 * (st.progresso || 0)) + "%";
  $("#progresso-texto").textContent = `Cenário ${st.cenario + 1} de ${st.n}` + (st.prazo ? ` (${fmt2.format(st.prazo)} meses)` : "")
    + ` · ${st.solucoes || 0} solução(ões) encontrada(s)` + (st.melhor ? ` · melhor custo ${reais(st.melhor)}` : "")
    + ` · até ${st.tempo_limite} s por cenário`;
}

async function acompanhar() {
  clearTimeout(est.timer);
  let st;
  try { st = await api(`/api/obras/${obraId}/cronograma/calculo`); } catch { return; }
  mostrarProgresso(st);
  if (st.rodando) { est.timer = setTimeout(acompanhar, 1000); return; }
  if (st.erro) mensagem($(st.tipo === "melhorias" ? "#msg-melhorias" : "#msg-cenarios"), st.erro, "erro");
  if (st.tipo === "melhorias") {
    if (est.cenId) await escolherVisualizado(est.cenId);
    if (!st.erro) mensagem($("#msg-melhorias"), "Busca de melhorias concluída.", "ok");
    return;
  }
  const antes = JSON.stringify(est.cmp);
  est.cmp = await api(`/api/obras/${obraId}/cenarios`);
  if (antes !== JSON.stringify(est.cmp)) {
    desenharCenarios();
    const escolhido = est.cmp.cenarios.find((c) => c.escolhido) || est.cmp.cenarios.find((c) => c.melhor_resultado);
    if (escolhido) await escolherVisualizado(escolhido.id);
  }
}

// ------------------------------------------------------------------ cenário visualizado

async function escolherVisualizado(id) {
  est.cenId = id || null;
  est.cen = null;
  if (id) {
    try { est.cen = await api(`/api/obras/${obraId}/cenarios/${id}`); } catch (err) { mensagem($("#msg-geral"), err.message, "erro"); }
  }
  $$(".sel-cenario").forEach((s) => { if (id) s.value = id; });
  desenharGantt();
  desenharEquipe();
  desenharResumo();
}
document.addEventListener("change", (e) => {
  if (e.target.matches(".sel-cenario") && e.target.value) escolherVisualizado(Number(e.target.value));
});

const SEM_CENARIO = '<p class="discreto">Calcule os cenários e escolha um para ver aqui.</p>';

// ------------------------------------------------------------------ 3. Gantt

function corBarra(a) {
  if (a.execucao === "terceirizada") return ["terceirizada", COR_TIPO.terceirizada];
  if (a.unidade === "corridos" || a.tipo === "aguardar") return ["aguardar", COR_TIPO.aguardar];
  return [a.tipo, COR_TIPO[a.tipo] || COR_TIPO.rigida];
}

function regua(inicio, fim, px, escala) {
  const partes = [];
  if (escala === "dia") {
    for (let d = inicio; d <= fim; d = somaDias(d, 1)) {
      const w = dt(d).getDay();
      partes.push(`<span class="g-cel ${w === 0 || w === 6 ? "fds" : ""}" style="left:${dias(inicio, d) * px}px;width:${px}px">${SEMANA[w]}<br>${d.slice(8, 10)}</span>`);
    }
  } else if (escala === "semana") {
    let d = dt(inicio);
    d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
    for (let s = iso(d); s <= fim; s = somaDias(s, 7)) {
      partes.push(`<span class="g-cel" style="left:${Math.max(0, dias(inicio, s)) * px}px;width:${7 * px}px">${s.slice(8, 10)}/${s.slice(5, 7)}</span>`);
    }
  } else {
    const d0 = dt(inicio);
    for (let m = new Date(d0.getFullYear(), d0.getMonth(), 1); iso(m) <= fim; m.setMonth(m.getMonth() + 1)) {
      const ini = iso(m) < inicio ? inicio : iso(m);
      const prox = new Date(m.getFullYear(), m.getMonth() + 1, 1);
      partes.push(`<span class="g-cel" style="left:${dias(inicio, ini) * px}px;width:${dias(ini, iso(prox)) * px}px">${MESES[m.getMonth()]}/${String(m.getFullYear()).slice(2)}</span>`);
    }
  }
  return partes.join("");
}

function desenharGantt() {
  const c = est.cen;
  const g = $("#gantt");
  const G = est.gantt;
  $$("#escala-gantt button").forEach((b) => b.classList.toggle("ativo", b.dataset.escala === G.escala));
  $("#legenda-gantt").innerHTML = Object.entries(ROTULO_BARRA).map(([k, r]) => `<span><i class="quadrado" style="background:${COR_TIPO[k]}"></i>${r}</span>`).join("")
    + '<span><i class="quadrado critica"></i>caminho crítico</span><span><i class="linha-hoje"></i>hoje</span><span><i class="linha-limite"></i>data limite</span>'
    + (G.setas ? '<span><i class="seta-ti"></i>término-início</span><span><i class="seta-ii"></i>início-início</span>' : "");
  if (!c) { g.innerHTML = SEM_CENARIO; return; }
  const inicio = est.p.data_inicio || c.atividades.reduce((m, a) => (a.inicio < m ? a.inicio : m), c.termino);
  const fim = [c.termino, c.data_limite].sort()[1];
  const px = PX_DIA[G.escala];
  const largura = Math.ceil((dias(inicio, fim) + 1) * px);
  const x = (d) => dias(inicio, d) * px;
  const larg = (a, b) => Math.max(3, (dias(a, b) + 1) * px);
  const linhas = [];
  linhas.push(`<div class="g-linha g-regua"><div class="g-rotulo">Atividade</div><div class="g-trilho" style="width:${largura}px">${regua(inicio, fim, px, G.escala)}</div></div>`);
  for (const p of c.periodos_indiretas || []) {
    if (!p.inicio || !p.termino || G.soCritico) continue;
    linhas.push(`<div class="g-linha g-indireta"><div class="g-rotulo" title="${esc(p.nome)}"><b>${esc(p.codigo)}</b> ${esc(p.nome || "")}</div>
      <div class="g-trilho" style="width:${largura}px"><span class="g-faixa" style="left:${x(p.inicio)}px;width:${larg(p.inicio, p.termino)}px"
        data-dica="${esc(`<b>${p.codigo}</b> ${p.nome || ""}<br>${dataBR(p.inicio)} a ${dataBR(p.termino)}<br>de ${p.de} até ${p.ate}`)}"></span></div></div>`);
  }
  const porEtapa = new Map();
  [...c.atividades].sort((a, b) => a.ordem - b.ordem).forEach((a) => {
    if (G.soCritico && !a.critica) return;
    const k = a.etapa || "—";
    if (!porEtapa.has(k)) porEtapa.set(k, []);
    porEtapa.get(k).push(a);
  });
  const visiveis = [];
  for (const [etapa, ativs] of porEtapa) {
    const fechada = G.fechadas.has(etapa);
    const ini = ativs.reduce((m, a) => (a.inicio < m ? a.inicio : m), ativs[0].inicio);
    const ter = ativs.reduce((m, a) => (a.termino > m ? a.termino : m), ativs[0].termino);
    linhas.push(`<div class="g-linha g-etapa" data-etapa="${esc(etapa)}"><div class="g-rotulo"><span class="seta-grupo">${fechada ? "▸" : "▾"}</span> ${esc(etapa)} <small class="discreto">(${ativs.length})</small></div>
      <div class="g-trilho" style="width:${largura}px">${fechada ? `<span class="g-resumo" style="left:${x(ini)}px;width:${larg(ini, ter)}px"
        data-dica="${esc(`<b>${etapa}</b><br>${dataBR(ini)} a ${dataBR(ter)}<br>${ativs.length} atividade(s)`)}"></span>` : ""}</div></div>`);
    if (fechada) continue;
    for (const a of ativs.sort((p, q) => (p.inicio < q.inicio ? -1 : p.inicio > q.inicio ? 1 : p.ordem - q.ordem))) {
      const [tipo, cor] = corBarra(a);
      const equipe = Object.entries(a.equipe || {}).sort((p, q) => q[1] - p[1]).map(([f, n]) => `${n} ${f.toLowerCase()}`).join(" + ");
      const maq = Object.entries(a.maquinas || {}).map(([e, n]) => `${n}× ${e.slice(0, 40)}`).join("; ");
      const texto = `<b>${esc(a.codigo)}</b> ${esc(a.nome || "")}<br>${dataBR(a.inicio)} a ${dataBR(a.termino)}<br>`
        + `Duração: ${a.duracao} dias ${a.unidade === "corridos" ? "corridos" : "úteis"} · ${ROTULO_BARRA[tipo]}`
        + (equipe ? `<br>Equipe: ${esc(equipe)}` : a.execucao === "terceirizada" ? "<br>Equipe terceirizada" : "")
        + (maq ? `<br>Máquinas: ${esc(maq)}` : "")
        + (a.partes ? `<br>Em ${a.partes.length} partes: ${a.partes.map((p) => `${dataBR(p.inicio)}–${dataBR(p.termino)}`).join(", ")}` : "")
        + `<br>Folga: ${a.folga} dia(s) útil(eis)` + (a.critica ? "<br><b>Caminho crítico</b>" : "");
      const barras = a.partes
        ? `<span class="g-ligacao" style="left:${x(a.inicio)}px;width:${larg(a.inicio, a.termino)}px"></span>`
          + a.partes.map((p) => `<span class="g-barra ${a.critica ? "critica" : ""}" style="left:${x(p.inicio)}px;width:${larg(p.inicio, p.termino)}px;background:${cor}" data-dica="${esc(texto)}"></span>`).join("")
        : `<span class="g-barra ${a.critica ? "critica" : ""}" style="left:${x(a.inicio)}px;width:${larg(a.inicio, a.termino)}px;background:${cor}" data-dica="${esc(texto)}"></span>`;
      linhas.push(`<div class="g-linha ${a.critica ? "g-critica" : ""}" data-ativ="${esc(a.codigo)}"><div class="g-rotulo" title="${esc(a.nome || "")}"><b>${esc(a.codigo)}</b> ${esc(a.nome || "")}</div>
        <div class="g-trilho" style="width:${largura}px">${barras}</div></div>`);
      visiveis.push(a);
    }
  }
  const hoje = iso(new Date());
  const marcas = [];
  if (hoje >= inicio && hoje <= fim) marcas.push(`<span class="g-vertical hoje" style="left:${260 + x(hoje)}px" title="hoje ${dataBR(hoje)}"></span>`);
  marcas.push(`<span class="g-vertical limite" style="left:${260 + x(c.data_limite) + px}px" title="data limite ${dataBR(c.data_limite)}"></span>`);
  g.innerHTML = `<div class="g-conteudo" style="width:${260 + largura}px">${linhas.join("")}${marcas.join("")}<svg class="g-setas"></svg></div>`;
  if (G.setas) desenharSetas(visiveis, inicio, px);
}

function desenharSetas(visiveis, inicio, px) {
  const cont = $("#gantt .g-conteudo");
  const svg = $("#gantt .g-setas");
  const pos = {};
  $$("#gantt [data-ativ]").forEach((linha) => { pos[linha.dataset.ativ] = linha.offsetTop + linha.offsetHeight / 2; });
  svg.setAttribute("width", cont.scrollWidth);
  svg.setAttribute("height", cont.scrollHeight);
  const x = (d) => 260 + dias(inicio, d) * px;
  const caminhos = [];
  for (const b of visiveis) {
    for (const d of b.dependencias || []) {
      const a = visiveis.find((v) => v.codigo === d.depende_de);
      if (!a || pos[a.codigo] === undefined || pos[b.codigo] === undefined) continue;
      const ii = d.tipo === "II";
      const x1 = ii ? x(a.inicio) : x(a.termino) + px;
      const y1 = pos[a.codigo];
      const x2 = x(b.inicio);
      const y2 = pos[b.codigo];
      const meio = Math.max(x1 + 6, Math.min(x2 - 6, x1 + 12));
      caminhos.push(`<path d="M${x1},${y1} H${meio} V${y2} H${x2 - 2}" class="${ii ? "seta-ii" : "seta-ti"}" marker-end="url(#ponta)"><title>${esc(b.codigo)} depende de ${esc(a.codigo)}${ii ? ":II" : ""}${d.espera ? `+${d.espera}${d.unidade}` : ""}</title></path>`);
    }
  }
  svg.innerHTML = `<defs><marker id="ponta" viewBox="0 0 6 6" refX="5" refY="3" markerWidth="6" markerHeight="6" orient="auto"><path d="M0,0 L6,3 L0,6 z" fill="#52514e"/></marker></defs>${caminhos.join("")}`;
}

$("#escala-gantt").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-escala]");
  if (!b) return;
  est.gantt.escala = b.dataset.escala;
  desenharGantt();
});
$("#ver-setas").addEventListener("change", (e) => { est.gantt.setas = e.target.checked; desenharGantt(); });
$("#so-critico").addEventListener("change", (e) => { est.gantt.soCritico = e.target.checked; desenharGantt(); });
$("#btn-abrir-grupos").addEventListener("click", () => {
  const etapas = [...new Set((est.cen?.atividades || []).map((a) => a.etapa || "—"))];
  if (est.gantt.fechadas.size) est.gantt.fechadas.clear(); else etapas.forEach((e) => est.gantt.fechadas.add(e));
  desenharGantt();
});
$("#gantt").addEventListener("click", (e) => {
  const linha = e.target.closest(".g-etapa");
  if (!linha || !e.target.closest(".g-rotulo")) return;
  const k = linha.dataset.etapa;
  est.gantt.fechadas.has(k) ? est.gantt.fechadas.delete(k) : est.gantt.fechadas.add(k);
  desenharGantt();
});

function ligarDicas(raiz) {
  raiz.addEventListener("mousemove", (e) => {
    const alvo = e.target.closest("[data-dica]");
    if (alvo) mostrarDica(e, alvo.dataset.dica); else esconderDica();
  });
  raiz.addEventListener("mouseleave", esconderDica);
}
ligarDicas($("#gantt"));
ligarDicas($("#grafico-equipe"));

// ------------------------------------------------------------------ 4. Equipe por semana

function seriesDoGrafico(c) {
  const ordem = [...c.funcoes].sort((a, b) => b.contratados.reduce((t, v) => t + v, 0) - a.contratados.reduce((t, v) => t + v, 0));
  const nomes = new Set(ordem.slice(0, SERIES.length).map((f) => f.funcao));
  // cor segue a função (ordem de entrada na obra), nunca a posição no ranking
  const cores = {};
  let k = 0;
  c.funcoes.forEach((f) => { if (nomes.has(f.funcao)) cores[f.funcao] = SERIES[k++] || COR_OUTRAS; });
  const series = c.funcoes.filter((f) => nomes.has(f.funcao)).map((f) => ({ ...f, cor: cores[f.funcao] }));
  const resto = c.funcoes.filter((f) => !nomes.has(f.funcao));
  if (resto.length) {
    const n = c.semanas.length;
    const somar = (campo) => Array.from({ length: n }, (_, i) => resto.reduce((t, f) => t + (f[campo][i] || 0), 0));
    series.push({ funcao: `Outras (${resto.length})`, cor: COR_OUTRAS, contratados: somar("contratados"),
      horas_ocupadas: somar("horas_ocupadas"), horas_pagas: somar("horas_pagas"), horas_feriado: somar("horas_feriado") });
  }
  return series;
}

function desenharEquipe() {
  const c = est.cen;
  const alvo = $("#grafico-equipe");
  $("#link-excel").href = c ? `/api/obras/${obraId}/cenarios/${c.id}/excel` : "#";
  if (!c || !c.semanas.length) {
    alvo.innerHTML = SEM_CENARIO;
    ["#tabela-equipe", "#tabela-ociosidade", "#legenda-equipe"].forEach((s) => { $(s).innerHTML = ""; });
    return;
  }
  const series = seriesDoGrafico(c);
  $("#legenda-equipe").innerHTML = series.map((s) => `<span><i class="quadrado" style="background:${s.cor}"></i>${esc(s.funcao)}</span>`).join("")
    + '<span><i class="quadrado parado"></i>parte hachurada = contratado parado (sem contar feriados)</span>';
  const n = c.semanas.length;
  const maxY = Math.max(1, ...c.total_semana);
  const passoY = maxY > 40 ? 10 : maxY > 16 ? 5 : maxY > 8 ? 2 : 1;
  const topoY = Math.ceil(maxY / passoY) * passoY;
  const bw = Math.max(6, Math.min(22, 1000 / n));
  const esq = 34, alto = 260, base = alto - 24, larg = esq + n * bw + 10;
  const y = (v) => base - (v / topoY) * (base - 10);
  let svg = `<svg width="${larg}" height="${alto}" role="img" aria-label="Pessoas contratadas por semana">
    <defs><pattern id="hachura" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
      <rect width="5" height="5" fill="#fcfcfb" fill-opacity="0.55"/><line x1="0" y1="0" x2="0" y2="5" stroke="#fcfcfb" stroke-width="2"/></pattern></defs>`;
  for (let v = 0; v <= topoY; v += passoY) {
    svg += `<line x1="${esq}" x2="${larg - 6}" y1="${y(v)}" y2="${y(v)}" class="grade${v === 0 ? " base" : ""}"/>
      <text x="${esq - 6}" y="${y(v) + 4}" class="eixo" text-anchor="end">${v}</text>`;
  }
  const passoX = Math.ceil(60 / bw);
  for (let i = 0; i < n; i++) {
    const x0 = esq + i * bw + 1;
    let acc = 0;
    const partes = [];
    for (const s of series) {
      const q = s.contratados[i];
      if (!q) continue;
      const util = (s.horas_pagas[i] || 0) - (s.horas_feriado?.[i] || 0);
      const ocup = util > 0 ? Math.min(1, s.horas_ocupadas[i] / util) : 0;
      const y1 = y(acc), y2 = y(acc + q);
      svg += `<rect x="${x0}" y="${y2}" width="${bw - 2}" height="${Math.max(0, y1 - y2 - 1)}" fill="${s.cor}"/>`;
      const hParado = (y1 - y2 - 1) * (1 - ocup);
      if (hParado > 0.5) svg += `<rect x="${x0}" y="${y2}" width="${bw - 2}" height="${hParado}" fill="url(#hachura)"/>`;
      partes.push(`${esc(s.funcao)}: <b>${q}</b> (${Math.round(100 * ocup)}% ocupado)`);
      acc += q;
    }
    const dicaTxt = `<b>Semana de ${dataBR(c.semanas[i])}</b><br>Total: ${c.total_semana[i]} contratados<br>${partes.reverse().join("<br>")}`;
    svg += `<rect x="${x0 - 1}" y="10" width="${bw}" height="${base - 10}" fill="transparent" data-dica="${esc(dicaTxt)}"/>`;
    if (i % passoX === 0) svg += `<text x="${x0 + bw / 2}" y="${alto - 8}" class="eixo" text-anchor="middle">${dataBR(c.semanas[i]).slice(0, 5)}</text>`;
  }
  alvo.innerHTML = svg + "</svg>";

  $("#tabela-ociosidade").innerHTML = `<thead><tr><th>Função</th><th>Entradas na obra</th><th class="num">Horas pagas</th><th class="num">Em feriado</th>
    <th class="num">Ocupadas</th><th class="num">Paradas</th><th class="num">Ociosidade</th></tr></thead><tbody>
    ${(c.ociosidade_funcao || []).map((f) => `<tr><td>${esc(f.funcao)}</td><td>${textoEntradas(f.entradas_permitidas ?? (f.pode_sair_e_voltar ? 0 : 1))}</td>
      <td class="num">${fmt1.format(f.horas_pagas)}</td><td class="num">${fmt1.format(f.horas_feriado)}</td><td class="num">${fmt1.format(f.horas_ocupadas)}</td>
      <td class="num">${fmt1.format(f.horas_paradas)}</td><td class="num"><b>${fmt1.format(f.ociosidade)}%</b></td></tr>`).join("")}
    <tr class="total"><td>Total</td><td></td><td class="num">${fmt1.format(c.horas_pagas || 0)}</td><td class="num">${fmt1.format(c.horas_feriado || 0)}</td>
      <td class="num">${fmt1.format(c.horas_ocupadas || 0)}</td><td></td><td class="num"><b>${fmt1.format(c.ociosidade)}%</b></td></tr></tbody>`;

  const cab = `<thead><tr><th>Função</th><th>Entrada</th><th>Pico</th><th>Saída</th>${c.semanas.map((s) => `<th class="num">${dataBR(s).slice(0, 5)}</th>`).join("")}</tr></thead>`;
  const corpo = c.funcoes.map((f) => `<tr><td class="nowrap">${esc(f.funcao)}</td><td class="nowrap">${dataBR(f.entrada)}</td>
      <td class="nowrap">${f.pico} <small class="discreto">${dataBR(f.semana_pico)}</small></td><td class="nowrap">${dataBR(f.saida)}</td>
      ${f.contratados.map((v, i) => `<td class="num ${v && f.horas_ocupadas[i] < 0.5 * (f.horas_pagas[i] - (f.horas_feriado[i] || 0)) ? "ocioso" : ""}">${v || ""}</td>`).join("")}</tr>`).join("");
  const total = `<tr class="total"><td>Total próprios</td><td></td><td>${Math.max(...c.total_semana)}</td><td></td>${c.total_semana.map((v) => `<td class="num">${v || ""}</td>`).join("")}</tr>`;
  const ind = (c.equipe_indireta || []).length
    ? `<tr class="separador"><td colspan="${4 + n}">Equipe indireta (da mão de obra), à parte dos próprios de produção</td></tr>`
      + c.equipe_indireta.map((e) => `<tr class="indireta"><td>${esc(e.funcao)}</td><td></td><td></td><td></td>${c.semanas.map((_, i) => `<td class="num">${e.pessoas[i] ? fmt2.format(e.pessoas[i]) : ""}</td>`).join("")}</tr>`).join("")
    : "";
  $("#tabela-equipe").innerHTML = cab + `<tbody>${corpo}${total}${ind}</tbody>`;
}

// ------------------------------------------------------------------ 5. Resumo

function linhasPeriodo(lista) {
  return (lista || []).map((i) => `<tr><td title="${esc(i.descricao)}">${esc(i.descricao.length > 90 ? i.descricao.slice(0, 90) + "…" : i.descricao)}</td>
      <td>${i.inicio ? `${dataBR(i.inicio)} a ${dataBR(i.termino)}` : "—"}</td><td class="num">${i.meses !== undefined ? fmt2.format(i.meses) : "—"}</td>
      <td class="num">${i.custo_mes !== undefined ? reais(i.custo_mes) : "—"}</td><td class="num">${reais(i.custo)}</td></tr>`).join("")
    || `<tr><td colspan="5" class="discreto">Nenhum item.</td></tr>`;
}

function desenharResumo() {
  const c = est.cen;
  if (!c) {
    $("#numeros-resumo").innerHTML = SEM_CENARIO;
    ["#caminho-critico", "#tabela-indiretos", "#tabela-receitas", "#causas", "#tabela-continuidade", "#melhorias"].forEach((s) => { $(s).innerHTML = ""; });
    return;
  }
  const caixas = [
    ["Prazo do cenário", `${fmt2.format(c.prazo_meses)} meses (até ${dataBR(c.data_limite)})`],
    ["Término previsto", dataBR(c.termino)],
    ["Dias úteis", c.dias_uteis ?? "—"],
    ["Pico de pessoas (próprios)", c.pico],
    ["Homem-semana pago", fmt1.format(c.homem_semana)],
    ["Ociosidade (sem feriados)", fmt1.format(c.ociosidade) + "%"],
    ["Mão de obra própria", reais(c.custo_mao_de_obra)],
    ["Custo de saída e volta de equipe", reais(c.custo_saida_volta || 0)],
    ["Indiretos reais por tempo", reais(c.custo_indiretos)],
    ["Receita que varia com o prazo", reais(c.receita_variavel || 0)],
    ["Resultado (parte variável)", reais(c.resultado)],
    ["Terceirizados (fixo)", reais(c.custo_terceirizados || 0)],
    ["Situação", SITUACAO[c.situacao] + (c.escolhido ? " · cronograma da obra" : "")],
  ];
  $("#numeros-resumo").innerHTML = caixas.map(([t, v]) => `<div class="numero"><span>${t}</span><b>${v}</b></div>`).join("");
  $("#causas").innerHTML = (c.causas_ociosidade || []).length
    ? `<ol>${c.causas_ociosidade.map((x) => `<li><b>${esc(x.funcao)}</b>: ${fmt1.format(x.horas_paradas)} h paradas (${fmt1.format(x.ociosidade)}% da função),
        principalmente nas semanas de ${x.semanas.map(dataBR).join(", ")}</li>`).join("")}</ol>`
    : "<p class='discreto'>Sem horas paradas.</p>";
  desenharContinuidade(c);
  $("#caminho-critico").innerHTML = (c.caminho_critico || []).map((x) => `<b>${esc(x)}</b>`).join(" → ");
  $("#tabela-indiretos").innerHTML = linhasPeriodo((c.indiretos || []).filter((i) => i.tipo !== "fixo"));
  $("#tabela-receitas").innerHTML = linhasPeriodo(c.receitas);
}

// ------------------------------------------------------------------ continuidade de equipe

function textoUso(u, depois) {
  if (!u) return "—";
  const k = depois ? u.semanas_paradas_depois : u.semanas_paradas_antes;
  const outra = depois ? u.seguinte : u.anterior;
  return `<b>${esc(u.codigo)}</b> <small>${esc((u.nome || "").slice(0, 40))}</small> · ${fmt1.format(u.horas)} h`
    + (k ? `<br><small>${k} semana(s) parada ${depois ? "depois" : "antes"}${outra ? ` (${depois ? "até a" : "desde a"} ${esc(outra)})` : ""}</small>` : "");
}

function desenharContinuidade(c) {
  const linhas = c.continuidade;
  if (!linhas) {
    $("#tabela-continuidade").innerHTML = "<tbody><tr><td class='discreto'>Cenário calculado numa versão anterior: recalcule para ver a continuidade de equipe.</td></tr></tbody>";
    $("#btn-melhorias").hidden = true;
    $("#melhorias").innerHTML = "";
    return;
  }
  $("#btn-melhorias").hidden = false;
  const sv = c.saida_volta_funcao || {};
  $("#tabela-continuidade").innerHTML = `<thead><tr><th>Função</th><th>Entrada / saída</th><th class="num">Entradas</th><th class="num">Semanas na obra</th>
    <th class="num">Semanas sem serviço</th><th class="num">Horas paradas</th><th class="num">Custo parado</th><th>Quem puxa a entrada</th><th>Quem segura a saída</th></tr></thead><tbody>
    ${linhas.map((l) => `<tr title="${esc(l.texto)}"><td><b>${esc(l.funcao)}</b></td>
      <td class="nowrap">sem. ${l.semana_entrada} (${dataBR(l.entrada)})<br>sem. ${l.semana_saida} (${dataBR(l.saida)})</td>
      <td class="num">${l.entradas} <small class="discreto">(${textoEntradas(l.entradas_permitidas)})</small>${sv[l.funcao] ? `<br><small>${sv[l.funcao].pessoas} volta(s): ${reais(sv[l.funcao].custo)}</small>` : ""}</td>
      <td class="num">${l.semanas_na_obra}</td><td class="num">${l.semanas_sem_servico}</td>
      <td class="num">${fmt1.format(l.horas_paradas)}</td><td class="num">${reais(l.custo_horas_paradas)}</td>
      <td>${textoUso(l.puxa_entrada, true)}</td><td>${textoUso(l.segura_saida, false)}</td></tr>`).join("")}</tbody>`;
  const textos = linhas.filter((l) => l.semanas_sem_servico && l.texto).slice(0, 3);
  const m = c.melhorias;
  let html = textos.length ? `<ul class="frases-continuidade">${textos.map((l) => `<li>${esc(l.texto)}</li>`).join("")}</ul>` : "";
  if (m) {
    html += `<h3>Melhorias encontradas <small class="discreto">(${m.testadas.length} alternativa(s) testada(s), ${fmt1.format(m.tempo_por_teste)} s cada${m.interrompido ? ", busca interrompida" : ""})</small></h3>
      <p class="discreto">Ganho em relação a este cenário recalculado com o mesmo tempo (${reais(m.base.custo_total)}, ociosidade ${fmt1.format(m.base.ociosidade)}%). Depois de aplicar, o cenário é recalculado com o tempo normal.</p>`;
    html += m.sugestoes.length
      ? `<table class="simples"><thead><tr><th>Mudança</th><th class="num">Ganho</th><th class="num">Ociosidade</th><th class="num">Término</th><th></th></tr></thead><tbody>
        ${m.sugestoes.map((x, i) => `<tr><td>${esc(x.texto)}</td><td class="num"><b>${reais(x.ganho)}</b></td>
          <td class="num">${fmt1.format(x.ociosidade)}% <small>(${x.ganho_ociosidade >= 0 ? "−" : "+"}${fmt1.format(Math.abs(x.ganho_ociosidade))} pontos)</small></td>
          <td class="num">${dataBR(x.termino)}</td>
          <td><button type="button" class="secundario pequeno" data-melhoria="${i}">Aplicar nesta obra</button></td></tr>`).join("")}</tbody></table>`
      : "<p class='discreto'>Nenhuma das alternativas testadas melhorou o custo deste cenário.</p>";
  }
  $("#melhorias").innerHTML = html;
}

$("#btn-melhorias").addEventListener("click", async () => {
  if (!est.cenId) return;
  mensagem($("#msg-melhorias"), "", "");
  try {
    const st = await api(`/api/obras/${obraId}/cronograma/melhorias`, { json: { cenario: est.cenId } });
    mostrarProgresso(st);
    acompanhar();
  } catch (err) { mensagem($("#msg-melhorias"), err.message, "erro"); }
});

$("#melhorias").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-melhoria]");
  if (!b || !est.cen?.melhorias) return;
  const x = est.cen.melhorias.sugestoes[Number(b.dataset.melhoria)];
  try {
    const st = await api(`/api/obras/${obraId}/cronograma/melhorias/aplicar`, { json: { acao: x, prazo_meses: est.cen.prazo_meses } });
    est.p = await api(`/api/obras/${obraId}/cronograma/parametros`);
    desenharParametros();
    mensagem($("#msg-melhorias"), `Aplicado nesta obra: ${x.texto}. Recalculando o cenário de ${fmt2.format(est.cen.prazo_meses)} meses…`, "ok");
    mostrarProgresso(st);
    acompanhar();
  } catch (err) { mensagem($("#msg-melhorias"), err.message, "erro"); }
});

carregar();
