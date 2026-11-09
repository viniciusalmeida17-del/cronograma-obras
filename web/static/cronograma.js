"use strict";

const obraId = obraDaUrl();
const est = { p: null, cmp: null, cen: null, cenId: null, aba: null, timer: null };
const fmt1 = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
const fmt2 = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });
const SITUACAO = {
  otimo: "ótimo", melhor_encontrado: "melhor encontrado", impossivel: "impossível", sem_solucao: "sem solução no tempo",
};
const ORIGEM_CUSTO = { obra: "desta obra", ultimo_usado: "último usado", composicoes: "composições", faltando: "falta informar" };
// paleta categórica fixa (ordem nunca muda); a 8ª posição é "Outras"
const SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6"];
const COR_OUTRAS = "#898781";
const COR_TIPO = { rigida: "#2a78d6", flexivel: "#1baf7a", aguardar: "#898781", terceirizada: "#eb6834" };
const ROTULO_BARRA = { rigida: "rígida", flexivel: "flexível", aguardar: "aguardar / duração fixa", terceirizada: "terceirizada" };

const dataBR = (iso) => (iso ? iso.slice(8, 10) + "/" + iso.slice(5, 7) + "/" + iso.slice(0, 4) : "—");
const dias = (a, b) => Math.round((new Date(b + "T00:00") - new Date(a + "T00:00")) / 86400000);
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
  $("#nome-obra").textContent = `Obra nº ${obraId} · ${p.obra.nome || ""}`;
  $("#link-mao-de-obra").href = `/mao-de-obra?obra=${obraId}`;
  const faltaCusto = Object.entries(p.custos).filter(([, v]) => !v.custo_hora).map(([f]) => f);
  const problemas = [];
  if (p.pendencias_etapa4.length) problemas.push(`${p.pendencias_etapa4.length} pendência(s) da etapa 4`);
  if (!p.data_inicio) problemas.push("falta a data de início");
  if (faltaCusto.length) problemas.push("falta o custo por hora de " + faltaCusto.join(", "));
  $("#faixa").className = "faixa " + (problemas.length ? "aviso" : "ok");
  $("#faixa").textContent = problemas.length
    ? "⚠ Antes de calcular: " + problemas.join("; ") + "."
    : `✔ Pronto para calcular. Prazo da licitação: ${p.prazo_licitacao ? fmt2.format(p.prazo_licitacao) + " meses" : "—"}.`;
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

function desenharParametros() {
  const p = est.p;
  const f = $("#form-parametros");
  f.data_inicio.value = p.data_inicio || "";
  f.limite_rigidas.value = p.limite_rigidas;
  f.tempo_limite.value = p.tempo_limite;
  f.max_pessoas_total.value = p.max_pessoas_total ?? "";
  $("#info-dias").textContent = p.dias_semana === 6 ? "6 (com sábado)" : "5 (segunda a sexta)";
  $("#info-jornada").textContent = `${fmt1.format(p.horas_semana)} h/semana` + (p.mudancas_jornada || [])
    .map((m) => `, ${fmt1.format(m.horas_semana)} h a partir de ${dataBR(m.a_partir_de)}`).join("");
  $("#lista-feriados").innerHTML = "";
  (p.feriados_locais || []).forEach(linhaFeriado);
  $("#tabela-custos").innerHTML = p.funcoes.map((fn) => {
    const c = p.custos[fn] || {};
    return `<tr><td>${esc(fn)}</td>
      <td class="num"><input type="number" name="custo" data-funcao="${esc(fn)}" min="0.01" step="0.01" value="${c.custo_hora ?? ""}" class="${c.custo_hora ? "" : "campo-faltando"}"></td>
      <td class="discreto">${ORIGEM_CUSTO[c.origem] || ""}</td>
      <td class="num discreto">${c.composicoes ? reais(c.composicoes) : "—"}</td>
      <td class="num"><input type="number" name="maximo" data-funcao="${esc(fn)}" min="1" step="1" value="${p.max_por_funcao[fn] ?? ""}" placeholder="—"></td></tr>`;
  }).join("") || `<tr><td colspan="5" class="discreto">Nenhuma atividade própria com horas.</td></tr>`;
  $("#tabela-travas tbody").innerHTML = p.atividades_proprias.map((a) => `<tr>
      <td><b>${esc(a.codigo)}</b> ${esc(a.nome || "")}</td><td>${esc(a.funcao_principal || "")}</td>
      <td class="num">${a.equipe_padrao}</td><td class="num">${a.equipe_max}</td>
      <td><select data-trava="${esc(a.codigo)}"><option value="">— otimizador escolhe</option>
        ${Array.from({ length: a.equipe_max }, (_, i) => i + 1).map((n) => `<option value="${n}" ${a.travada === n ? "selected" : ""}>${n} ${esc((a.funcao_principal || "").toLowerCase())}</option>`).join("")}
      </select></td></tr>`).join("");
  const fc = $("#form-calcular");
  fc.prazos.value = (p.prazos || []).map((x) => fmt2.format(x)).join("; ");
  fc.tempo_limite.value = p.tempo_limite;
}

$("#btn-add-feriado").addEventListener("click", () => linhaFeriado());

$("#form-parametros").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  const custos = {};
  $$("input[name=custo]", f).forEach((i) => { custos[i.dataset.funcao] = i.value; });
  const maximos = {};
  $$("input[name=maximo]", f).forEach((i) => { if (i.value) maximos[i.dataset.funcao] = i.value; });
  const feriados = $$("#lista-feriados .mudanca").map((d) => ({ data: $("[name=feriado_data]", d).value, nome: $("[name=feriado_nome]", d).value }))
    .filter((x) => x.data);
  try {
    est.p = await api(`/api/obras/${obraId}/cronograma/parametros`, { json: {
      data_inicio: f.data_inicio.value, limite_rigidas: f.limite_rigidas.value, tempo_limite: f.tempo_limite.value,
      max_pessoas_total: f.max_pessoas_total.value, feriados_locais: feriados, custos_hora: custos, max_por_funcao: maximos,
    } });
    desenharTopo();
    desenharParametros();
    mensagem($("#msg-parametros"), "Parâmetros salvos. Recalcule os cenários para aplicar.", "ok");
  } catch (err) { mensagem($("#msg-parametros"), err.message, "erro"); }
});

$("#tabela-travas").addEventListener("change", async (e) => {
  const s = e.target.closest("select[data-trava]");
  if (!s) return;
  try {
    est.p = await api(`/api/obras/${obraId}/cronograma/travar`, { json: { atividade: s.dataset.trava, pessoas: s.value || null } });
    mensagem($("#msg-travas"), `${s.dataset.trava}: ${s.value ? "equipe travada em " + s.value : "otimizador escolhe a equipe"}. Recalcule os cenários.`, "ok");
  } catch (err) { mensagem($("#msg-travas"), err.message, "erro"); }
});

// ------------------------------------------------------------------ 2. cenários

function desenharCenarios() {
  const cmp = est.cmp;
  $("#tabela-cenarios tbody").innerHTML = cmp.cenarios.map((c) => {
    const ok = c.situacao === "otimo" || c.situacao === "melhor_encontrado";
    if (!ok) {
      const mp = c.menor_prazo || {};
      return `<tr class="impossivel"><td>${fmt2.format(c.prazo_meses)} meses<br><small class="discreto">até ${dataBR(c.data_limite)}</small></td>
        <td colspan="8">${c.situacao === "impossivel" ? `<b>Não cabe em ${fmt2.format(c.prazo_meses)} meses.</b>` : esc(c.mensagem || "")}
          ${mp.dias_uteis ? ` Menor prazo possível com a equipe máxima: <b>${mp.dias_uteis} dias úteis</b> (${fmt2.format(mp.meses)} meses, término ${dataBR(mp.termino)}).
          <br><small>Caminho crítico: ${(mp.caminho_critico || []).map(esc).join(" → ")}</small>` : ""}</td>
        <td><span class="selo ambiguo">${SITUACAO[c.situacao]}</span></td></tr>`;
    }
    const dif = c.diferenca === null ? "—" : `${reais(c.diferenca)}<br><small>${fmt2.format(c.diferenca_pct || 0)}%</small>`;
    return `<tr class="${c.mais_barato ? "mais-barato" : ""} ${c.escolhido ? "escolhido" : ""}">
      <td><b>${fmt2.format(c.prazo_meses)} meses</b><br><small class="discreto">até ${dataBR(c.data_limite)}</small></td>
      <td>${dataBR(c.termino)}</td><td class="num">${c.pico}</td><td class="num">${fmt1.format(c.homem_semana)}</td>
      <td class="num">${fmt1.format(c.ociosidade)}%</td><td class="num">${reais(c.custo_mao_de_obra)}</td>
      <td class="num">${reais(c.custo_indiretos)}</td><td class="num"><b>${reais(c.custo_total)}</b></td>
      <td class="num ${c.diferenca > 0 ? "economia" : ""}">${dif}</td>
      <td><span class="selo ${c.situacao === "otimo" ? "confirmado" : "memoria"}">${SITUACAO[c.situacao]}</span>
        ${c.mais_barato ? '<span class="selo confirmado">mais barato</span>' : ""}
        <small class="discreto">${fmt1.format(c.segundos || 0)} s</small>
        <div class="botoes-cenario">${c.escolhido ? "<b>✔ cronograma da obra</b>" : `<button type="button" class="secundario pequeno" data-escolher="${c.id}">Usar este</button>`}
        <button type="button" class="secundario pequeno" data-ver="${c.id}">Ver</button></div></td></tr>`;
  }).join("") || `<tr><td colspan="10" class="discreto">Nenhum cenário calculado ainda.</td></tr>`;
  const opcoes = cmp.cenarios.filter((c) => c.termino)
    .map((c) => `<option value="${c.id}">${fmt2.format(c.prazo_meses)} meses${c.escolhido ? " (cronograma da obra)" : ""}</option>`).join("");
  $$(".sel-cenario").forEach((s) => { s.innerHTML = opcoes || "<option value=''>— nenhum cenário —</option>"; if (est.cenId) s.value = est.cenId; });
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
    }
  } catch (err) { mensagem($("#msg-cenarios"), err.message, "erro"); }
});

$("#form-calcular").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  const prazos = f.prazos.value.split(/[;\s]+/).map((x) => x.trim().replace(",", ".")).filter(Boolean);
  try {
    const st = await api(`/api/obras/${obraId}/cronograma/calcular`, { json: { prazos, tempo_limite: f.tempo_limite.value } });
    mensagem($("#msg-cenarios"), "", "");
    mostrarProgresso(st);
    acompanhar();
  } catch (err) { mensagem($("#msg-cenarios"), err.message, "erro"); }
});

$("#btn-parar").addEventListener("click", () => api(`/api/obras/${obraId}/cronograma/parar`, { method: "POST" }).catch(() => {}));

function mostrarProgresso(st) {
  $("#progresso").hidden = !st.rodando;
  $("#btn-parar").hidden = !st.rodando;
  $("#btn-calcular").disabled = !!st.rodando;
  if (!st.rodando) return;
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
  if (st.erro) mensagem($("#msg-cenarios"), st.erro, "erro");
  const antes = JSON.stringify(est.cmp);
  est.cmp = await api(`/api/obras/${obraId}/cenarios`);
  if (antes !== JSON.stringify(est.cmp)) {
    desenharCenarios();
    const escolhido = est.cmp.cenarios.find((c) => c.escolhido) || est.cmp.cenarios.find((c) => c.mais_barato);
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

function desenharGantt() {
  const c = est.cen;
  const g = $("#gantt");
  $("#legenda-gantt").innerHTML = Object.entries(ROTULO_BARRA).map(([k, r]) => `<span><i class="quadrado" style="background:${COR_TIPO[k]}"></i>${r}</span>`).join("")
    + '<span><i class="quadrado critica"></i>caminho crítico</span>';
  if (!c) { g.innerHTML = SEM_CENARIO; return; }
  const inicio = est.p.data_inicio || c.atividades.reduce((m, a) => (a.inicio < m ? a.inicio : m), c.termino);
  const fim = c.termino;
  const total = dias(inicio, fim) + 1;
  const px = Math.max(2, Math.min(8, 1100 / total));
  const largura = Math.ceil(total * px);
  const x = (d) => dias(inicio, d) * px;
  // régua de meses
  let regua = "";
  const d0 = new Date(inicio + "T00:00");
  for (let m = new Date(d0.getFullYear(), d0.getMonth(), 1); m <= new Date(fim + "T00:00"); m.setMonth(m.getMonth() + 1)) {
    const iso = m.toISOString().slice(0, 10) < inicio ? inicio : `${m.getFullYear()}-${String(m.getMonth() + 1).padStart(2, "0")}-01`;
    regua += `<span class="mes" style="left:${x(iso)}px">${String(m.getMonth() + 1).padStart(2, "0")}/${String(m.getFullYear()).slice(2)}</span>`;
  }
  const linhas = [];
  linhas.push(`<div class="g-linha g-regua"><div class="g-rotulo"></div><div class="g-trilho" style="width:${largura}px">${regua}</div></div>`);
  for (const p of c.periodos_indiretas || []) {
    if (!p.inicio || !p.termino) continue;
    linhas.push(`<div class="g-linha g-indireta"><div class="g-rotulo" title="${esc(p.nome)}"><b>${esc(p.codigo)}</b> ${esc(p.nome || "")}</div>
      <div class="g-trilho" style="width:${largura}px"><span class="g-faixa" style="left:${x(p.inicio)}px;width:${Math.max(2, (dias(p.inicio, p.termino) + 1) * px)}px"
        data-dica="${esc(`<b>${p.codigo}</b> ${p.nome || ""}<br>${dataBR(p.inicio)} a ${dataBR(p.termino)}<br>de ${p.de} até ${p.ate}`)}"></span></div></div>`);
  }
  const porEtapa = new Map();
  [...c.atividades].sort((a, b) => a.ordem - b.ordem).forEach((a) => {
    const k = a.etapa || "—";
    if (!porEtapa.has(k)) porEtapa.set(k, []);
    porEtapa.get(k).push(a);
  });
  for (const [etapa, ativs] of porEtapa) {
    linhas.push(`<div class="g-linha g-etapa"><div class="g-rotulo">${esc(etapa)}</div><div class="g-trilho" style="width:${largura}px"></div></div>`);
    for (const a of ativs.sort((p, q) => (p.inicio < q.inicio ? -1 : p.inicio > q.inicio ? 1 : p.ordem - q.ordem))) {
      const [tipo, cor] = corBarra(a);
      const equipe = Object.entries(a.equipe || {}).sort((p, q) => q[1] - p[1]).map(([f, n]) => `${n} ${f.toLowerCase()}`).join(" + ");
      const texto = `<b>${esc(a.codigo)}</b> ${esc(a.nome || "")}<br>${dataBR(a.inicio)} a ${dataBR(a.termino)}<br>`
        + `Duração: ${a.duracao} dias ${a.unidade === "corridos" ? "corridos" : "úteis"} · ${ROTULO_BARRA[tipo]}`
        + (equipe ? `<br>Equipe: ${esc(equipe)}` : a.execucao === "terceirizada" ? "<br>Equipe terceirizada" : "")
        + `<br>Folga: ${a.folga} dia(s) útil(eis)` + (a.critica ? "<br><b>Caminho crítico</b>" : "");
      linhas.push(`<div class="g-linha ${a.critica ? "g-critica" : ""}"><div class="g-rotulo" title="${esc(a.nome || "")}"><b>${esc(a.codigo)}</b> ${esc(a.nome || "")}</div>
        <div class="g-trilho" style="width:${largura}px"><span class="g-barra ${a.critica ? "critica" : ""}" style="left:${x(a.inicio)}px;width:${Math.max(3, (dias(a.inicio, a.termino) + 1) * px)}px;background:${cor}"
          data-dica="${esc(texto)}"></span></div></div>`);
    }
  }
  g.innerHTML = linhas.join("");
}

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
  const principais = ordem.slice(0, SERIES.length);
  const nomes = new Set(principais.map((f) => f.funcao));
  // cor segue a função (ordem de entrada na obra), nunca a posição no ranking
  const cores = {};
  let k = 0;
  c.funcoes.forEach((f) => { if (nomes.has(f.funcao)) cores[f.funcao] = SERIES[k++] || COR_OUTRAS; });
  const series = c.funcoes.filter((f) => nomes.has(f.funcao)).map((f) => ({ ...f, cor: cores[f.funcao] }));
  const resto = c.funcoes.filter((f) => !nomes.has(f.funcao));
  if (resto.length) {
    const n = c.semanas.length;
    series.push({
      funcao: `Outras (${resto.length})`, cor: COR_OUTRAS, outras: resto.map((f) => f.funcao),
      contratados: Array.from({ length: n }, (_, i) => resto.reduce((t, f) => t + f.contratados[i], 0)),
      horas_ocupadas: Array.from({ length: n }, (_, i) => resto.reduce((t, f) => t + f.horas_ocupadas[i], 0)),
      horas_pagas: Array.from({ length: n }, (_, i) => resto.reduce((t, f) => t + f.horas_pagas[i], 0)),
    });
  }
  return series;
}

function desenharEquipe() {
  const c = est.cen;
  const alvo = $("#grafico-equipe");
  $("#link-excel").href = c ? `/api/obras/${obraId}/cenarios/${c.id}/excel` : "#";
  if (!c || !c.semanas.length) { alvo.innerHTML = SEM_CENARIO; $("#tabela-equipe").innerHTML = ""; $("#legenda-equipe").innerHTML = ""; return; }
  const series = seriesDoGrafico(c);
  $("#legenda-equipe").innerHTML = series.map((s) => `<span><i class="quadrado" style="background:${s.cor}"></i>${esc(s.funcao)}</span>`).join("")
    + '<span><i class="quadrado parado"></i>parte hachurada = contratado parado</span>';
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
      const ocup = s.horas_pagas[i] ? Math.min(1, s.horas_ocupadas[i] / s.horas_pagas[i]) : 0;
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

  // tabela semana × função
  const cab = `<thead><tr><th>Função</th><th>Entrada</th><th>Pico</th><th>Saída</th>${c.semanas.map((s) => `<th class="num">${dataBR(s).slice(0, 5)}</th>`).join("")}</tr></thead>`;
  const corpo = c.funcoes.map((f) => `<tr><td class="nowrap">${esc(f.funcao)}</td><td class="nowrap">${dataBR(f.entrada)}</td>
      <td class="nowrap">${f.pico} <small class="discreto">${dataBR(f.semana_pico)}</small></td><td class="nowrap">${dataBR(f.saida)}</td>
      ${f.contratados.map((v, i) => `<td class="num ${v && f.horas_ocupadas[i] < 0.5 * f.horas_pagas[i] ? "ocioso" : ""}">${v || ""}</td>`).join("")}</tr>`).join("");
  const total = `<tr class="total"><td>Total próprios</td><td></td><td>${Math.max(...c.total_semana)}</td><td></td>${c.total_semana.map((v) => `<td class="num">${v || ""}</td>`).join("")}</tr>`;
  const ind = (c.equipe_indireta || []).length
    ? `<tr class="separador"><td colspan="${4 + n}">Equipe indireta (etapa 4), à parte dos próprios de produção</td></tr>`
      + c.equipe_indireta.map((e) => `<tr class="indireta"><td>${esc(e.funcao)}</td><td></td><td></td><td></td>${c.semanas.map((_, i) => `<td class="num">${e.pessoas[i] ? fmt2.format(e.pessoas[i]) : ""}</td>`).join("")}</tr>`).join("")
    : "";
  $("#tabela-equipe").innerHTML = cab + `<tbody>${corpo}${total}${ind}</tbody>`;
}

// ------------------------------------------------------------------ 5. Resumo

function desenharResumo() {
  const c = est.cen;
  if (!c) { $("#numeros-resumo").innerHTML = SEM_CENARIO; $("#caminho-critico").textContent = ""; $("#tabela-indiretos").innerHTML = ""; return; }
  const caixas = [
    ["Prazo do cenário", `${fmt2.format(c.prazo_meses)} meses (até ${dataBR(c.data_limite)})`],
    ["Término previsto", dataBR(c.termino)],
    ["Dias úteis", c.dias_uteis ?? "—"],
    ["Pico de pessoas (próprios)", c.pico],
    ["Homem-semana pago", fmt1.format(c.homem_semana)],
    ["Ociosidade", fmt1.format(c.ociosidade) + "%"],
    ["Mão de obra própria", reais(c.custo_mao_de_obra)],
    ["Indiretos por tempo", reais(c.custo_indiretos)],
    ["Total que varia com o prazo", reais(c.custo_total)],
    ["Situação", SITUACAO[c.situacao] + (c.escolhido ? " · cronograma da obra" : "")],
  ];
  $("#numeros-resumo").innerHTML = caixas.map(([t, v]) => `<div class="numero"><span>${t}</span><b>${v}</b></div>`).join("");
  $("#caminho-critico").innerHTML = (c.caminho_critico || []).map((x) => `<b>${esc(x)}</b>`).join(" → ");
  $("#tabela-indiretos").innerHTML = (c.indiretos || []).map((i) => `<tr><td title="${esc(i.descricao)}">${esc(i.descricao.length > 90 ? i.descricao.slice(0, 90) + "…" : i.descricao)}</td>
      <td>${i.inicio ? `${dataBR(i.inicio)} a ${dataBR(i.termino)}` : "—"}</td><td class="num">${i.meses !== undefined ? fmt2.format(i.meses) : "—"}</td>
      <td class="num">${i.custo_mes !== undefined ? reais(i.custo_mes) : "—"}</td><td class="num">${reais(i.custo)}</td>
      <td class="discreto">${i.tipo === "obra" ? "obra toda (varia com o prazo)" : i.tipo === "periodo" ? `de ${esc(i.de)} até ${esc(i.ate)}` : esc(i.motivo || "fixo")}</td></tr>`).join("");
}

carregar();
