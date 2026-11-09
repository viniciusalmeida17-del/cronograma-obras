"use strict";

const ROTULOS = {
  item: "Item *", base: "Base / Referência", codigo: "Código", descricao: "Descrição *",
  unidade: "Unidade *", quantidade: "Quantidade *", preco_unit: "Valor unitário",
  preco_unit_bdi: "Valor unitário (com BDI)", total: "Custo total", total_bdi: "Custo total (com BDI)",
};
const NATUREZAS = { producao: "Produção", tempo: "Tempo", transporte: "Transporte", taxa: "Taxa" };

const estado = {
  dados: null,          // resultado da leitura
  recolhidos: new Set(),// itens de grupos recolhidos
  naturezas: {},        // linha_excel -> natureza alterada pelo usuário
};

const $ = (sel) => document.querySelector(sel);
const fmtReais = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const fmtQtd = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 4 });
const reais = (v) => (v === null || v === undefined ? "—" : fmtReais.format(v));
const qtd = (v) => (v === null || v === undefined ? "—" : fmtQtd.format(v));

function esc(t) {
  return String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function semAcento(t) {
  return String(t ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toUpperCase();
}
function mensagem(el, texto, tipo = "") {
  el.textContent = texto;
  el.className = "mensagem " + tipo;
}

async function api(url, opcoes = {}) {
  const resp = await fetch(url, opcoes);
  const corpo = await resp.json().catch(() => ({ erro: "Resposta inválida do servidor." }));
  if (!resp.ok) throw new Error(corpo.erro || `Erro ${resp.status}`);
  return corpo;
}

/* ------------------------------------------------------------------ envio */

const inputArquivo = $("#arquivo");
const area = $("#area-arquivo");
inputArquivo.addEventListener("change", () => {
  $("#nome-arquivo").textContent = inputArquivo.files[0]?.name || "Escolha ou arraste o arquivo .xlsx da licitação";
});
["dragenter", "dragover"].forEach((ev) => area.addEventListener(ev, (e) => { e.preventDefault(); area.classList.add("arrastando"); }));
["dragleave", "drop"].forEach((ev) => area.addEventListener(ev, (e) => { e.preventDefault(); area.classList.remove("arrastando"); }));
area.addEventListener("drop", (e) => {
  if (e.dataTransfer.files.length) {
    inputArquivo.files = e.dataTransfer.files;
    inputArquivo.dispatchEvent(new Event("change"));
  }
});

$("#form-envio").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = $("#msg-envio");
  const arquivo = inputArquivo.files[0];
  if (!arquivo) return mensagem(msg, "Escolha o arquivo da planilha.", "erro");
  const fd = new FormData();
  fd.append("arquivo", arquivo);
  $("#btn-ler").disabled = true;
  mensagem(msg, "Lendo planilha…");
  try {
    const dados = await api("/api/leitura", { method: "POST", body: fd });
    estado.naturezas = {};
    estado.recolhidos = new Set();
    mostrar(dados, true);
    mensagem(msg, `Arquivo lido: ${dados.arquivo}`, "ok");
  } catch (err) {
    mensagem(msg, err.message, "erro");
  } finally {
    $("#btn-ler").disabled = false;
  }
});

async function reler(opcoes) {
  const msg = $("#msg-envio");
  mensagem(msg, "Lendo novamente…");
  try {
    const dados = await api(`/api/leitura/${estado.dados.token}`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(opcoes),
    });
    estado.naturezas = {};
    mostrar(dados, true);
    mensagem(msg, `Aba '${dados.aba}' lida.`, "ok");
  } catch (err) {
    mensagem(msg, err.message, "erro");
  }
}

/* ------------------------------------------------------------------ tela */

function mostrar(dados, preencherObra) {
  estado.dados = dados;
  $("#conferencia").hidden = false;
  mostrarAba(dados);
  mostrarMapeamento(dados);
  if (preencherObra) preencherCamposObra(dados.obra);
  mostrarResumo();
  mostrarAlertas(dados.alertas);
  montarFiltroGrupos(dados.grupos);
  desenharArvore();
  mensagem($("#msg-salvar"), "");
  $("#btn-salvar").disabled = !dados.servicos.length;
}

function mostrarAba(d) {
  const sel = $("#aba");
  sel.innerHTML = d.abas
    .map((a) => `<option value="${esc(a.nome)}" ${a.nome === d.aba ? "selected" : ""}>${esc(a.nome)}${a.tem_cabecalho ? " ✓" : ""}</option>`)
    .join("");
  const letras = Object.values(d.colunas).sort((a, b) => a.length - b.length || a.localeCompare(b));
  const info = d.linha_cabecalho
    ? `Cabeçalho na linha ${d.linha_cabecalho} · colunas ${letras[0]} a ${letras[letras.length - 1]}`
    : "Cabeçalho não encontrado";
  $("#info-cabecalho").textContent = info;
}
$("#aba").addEventListener("change", (e) => reler({ aba: e.target.value }));

function mostrarMapeamento(d) {
  const faltando = d.colunas_faltando.length > 0 || !d.linha_cabecalho;
  $("#mapeamento").hidden = !faltando && $("#mapeamento").dataset.aberto !== "1";
  $("#linha-cabecalho").value = d.linha_cabecalho || d.linha_cabecalho_sugerida || "";
  const opcoes = (atual) =>
    `<option value="">— não usar —</option>` +
    d.cabecalhos.map((c) => `<option value="${c.letra}" ${c.letra === atual ? "selected" : ""}>${c.letra} · ${esc(c.texto.replace(/\s+/g, " "))}</option>`).join("") +
    // permite apontar colunas sem texto no cabeçalho
    letrasExtras().filter((l) => !d.cabecalhos.some((c) => c.letra === l)).map((l) => `<option value="${l}" ${l === atual ? "selected" : ""}>${l}</option>`).join("");
  $("#grade-mapeamento").innerHTML = Object.entries(ROTULOS)
    .map(([campo, rotulo]) => {
      const falta = d.colunas_faltando.includes(campo);
      return `<label class="${falta ? "faltando" : ""}">${rotulo}<select data-campo="${campo}">${opcoes(d.colunas[campo])}</select></label>`;
    })
    .join("");
}
function letrasExtras() {
  const letras = [];
  for (let i = 0; i < 26; i++) letras.push(String.fromCharCode(65 + i));
  return letras;
}
$("#btn-ajustar").addEventListener("click", () => {
  const m = $("#mapeamento");
  m.hidden = !m.hidden;
  m.dataset.aberto = m.hidden ? "0" : "1";
});
$("#btn-reler").addEventListener("click", () => {
  const mapeamento = {};
  document.querySelectorAll("#grade-mapeamento select").forEach((s) => { mapeamento[s.dataset.campo] = s.value; });
  reler({ aba: estado.dados.aba, mapeamento, linha_cabecalho: Number($("#linha-cabecalho").value) || null });
});

function preencherCamposObra(o) {
  $("#obra-nome").value = o.nome || "";
  $("#obra-prazo").value = o.prazo_valor ?? "";
  $("#obra-prazo-unidade").value = o.prazo_unidade || "";
  $("#obra-bdi").value = o.bdi !== null && o.bdi !== undefined ? +(o.bdi * 100).toFixed(4) : "";
  $("#obra-desoneracao").value = o.desoneracao || "";
  $("#obra-referencias").value = (o.referencias || []).join("\n");
  marcarPrazo();
}
function marcarPrazo() {
  const p = Number($("#obra-prazo").value);
  $("#obra-prazo").classList.toggle("campo-faltando", !(p > 0));
  $("#obra-prazo-unidade").classList.toggle("campo-faltando", !$("#obra-prazo-unidade").value);
}
$("#obra-prazo").addEventListener("input", marcarPrazo);
$("#obra-prazo-unidade").addEventListener("change", marcarPrazo);

function naturezaDe(s) {
  return estado.naturezas[s.linha_excel] || s.natureza;
}

function mostrarResumo() {
  const d = estado.dados;
  const v = d.validacao;
  const faixa = $("#faixa");
  if (!v) {
    faixa.className = "faixa erro";
    faixa.textContent = d.resumo;
    $("#numeros").innerHTML = "";
    return;
  }
  faixa.className = "faixa " + (v.ok ? "ok" : "erro");
  const extra = [];
  if (v.grupos_divergentes) extra.push(`${v.grupos_divergentes} grupo(s) com total divergente`);
  if (v.servicos_divergentes) extra.push(`${v.servicos_divergentes} serviço(s) com quantidade × preço ≠ total`);
  faixa.textContent = (v.ok ? "✔ " : "✖ ") + d.resumo + (extra.length ? " · " + extra.join(" · ") : "");

  const cont = { producao: 0, tempo: 0, transporte: 0, taxa: 0 };
  d.servicos.forEach((s) => { cont[naturezaDe(s)]++; });
  const caixas = [
    ["Serviços", v.qtd_servicos],
    ["Grupos", v.qtd_grupos],
    ["Total lido", reais(v.soma_servicos)],
    ["Total da planilha", reais(d.obra.total_planilha)],
    ["Total lido (com BDI)", reais(v.soma_servicos_bdi)],
    ["Total planilha (com BDI)", reais(d.obra.total_bdi_planilha)],
    ...Object.entries(NATUREZAS).map(([k, r]) => [r, cont[k]]),
  ];
  $("#numeros").innerHTML = caixas.map(([r, val]) => `<div class="numero"><span>${r}</span><b>${val}</b></div>`).join("");
}

function mostrarAlertas(alertas) {
  const n = { erro: 0, aviso: 0, info: 0 };
  alertas.forEach((a) => n[a.nivel]++);
  $("#resumo-alertas").textContent = alertas.length
    ? `Alertas: ${n.erro} erro(s), ${n.aviso} aviso(s), ${n.info} informação(ões)`
    : "Nenhum alerta";
  const ordem = { erro: 0, aviso: 1, info: 2 };
  $("#lista-alertas").innerHTML = [...alertas]
    .sort((a, b) => ordem[a.nivel] - ordem[b.nivel] || (a.linha || 0) - (b.linha || 0))
    .map((a) => `<li class="${a.nivel}">${a.linha ? `<a data-linha="${a.linha}">linha ${a.linha}</a>` : ""}${esc(a.mensagem)}</li>`)
    .join("");
  $("#alertas").open = n.erro > 0;
}
$("#lista-alertas").addEventListener("click", (e) => {
  const linha = e.target.dataset?.linha;
  if (linha) irParaLinha(Number(linha));
});

function irParaLinha(linha) {
  const d = estado.dados;
  const alvo = d.servicos.find((s) => s.linha_excel === linha) || d.grupos.find((g) => g.linha_excel === linha);
  if (!alvo) return;
  // limpa filtros e abre os grupos do caminho
  $("#filtro-grupo").value = ""; $("#filtro-natureza").value = ""; $("#filtro-texto").value = "";
  (alvo.caminho_grupos || caminhoGrupo(alvo.item)).forEach((g) => estado.recolhidos.delete(g));
  desenharArvore();
  const tr = document.querySelector(`#arvore tr[data-linha="${linha}"]`);
  if (tr) {
    tr.scrollIntoView({ block: "center", behavior: "smooth" });
    tr.classList.add("destaque");
    setTimeout(() => tr.classList.remove("destaque"), 2500);
  }
}

function caminhoGrupo(item) {
  const porItem = Object.fromEntries(estado.dados.grupos.map((g) => [g.item, g]));
  const cam = [];
  let atual = porItem[item]?.item_pai;
  while (atual) { cam.unshift(atual); atual = porItem[atual]?.item_pai; }
  return cam;
}

function montarFiltroGrupos(grupos) {
  const sel = $("#filtro-grupo");
  const atual = sel.value;
  sel.innerHTML = `<option value="">Todos</option>` + grupos
    .map((g) => `<option value="${esc(g.item)}">${"  ".repeat(g.nivel - 1)}${esc(g.item)} – ${esc(g.descricao.slice(0, 70))}</option>`)
    .join("");
  if (grupos.some((g) => g.item === atual)) sel.value = atual;
}

/* ------------------------------------------------------------------ árvore */

function filtrosAtivos() {
  return {
    grupo: $("#filtro-grupo").value,
    natureza: $("#filtro-natureza").value,
    texto: semAcento($("#filtro-texto").value.trim()),
  };
}

function servicoPassa(s, f) {
  if (f.grupo && !s.caminho_grupos.includes(f.grupo)) return false;
  if (f.natureza && naturezaDe(s) !== f.natureza) return false;
  if (f.texto) {
    const alvo = semAcento(`${s.item} ${s.codigo} ${s.descricao} ${s.base}`);
    if (!alvo.includes(f.texto)) return false;
  }
  return true;
}

function desenharArvore() {
  const d = estado.dados;
  const f = filtrosAtivos();
  const filtrando = Boolean(f.grupo || f.natureza || f.texto);
  const visiveis = d.servicos.filter((s) => servicoPassa(s, f));
  const gruposComServico = new Set();
  visiveis.forEach((s) => s.caminho_grupos.forEach((g) => gruposComServico.add(g)));

  const linhas = [
    ...d.grupos.map((g) => ({ tipo: "g", l: g.linha_excel, o: g })),
    ...visiveis.map((s) => ({ tipo: "s", l: s.linha_excel, o: s })),
  ].sort((a, b) => a.l - b.l);

  const html = [];
  for (const { tipo, o } of linhas) {
    const caminho = tipo === "g" ? caminhoGrupo(o.item) : o.caminho_grupos;
    // com filtro ativo, mostra os resultados mesmo dentro de grupos recolhidos
    if (!filtrando && caminho.some((g) => estado.recolhidos.has(g))) continue;
    if (tipo === "g") {
      if (filtrando && !gruposComServico.has(o.item)) continue;
      if (f.grupo && !(o.item === f.grupo || caminho.includes(f.grupo) || caminhoGrupo(f.grupo).includes(o.item))) continue;
      html.push(linhaGrupo(o));
    } else {
      html.push(linhaServico(o, caminho.length));
    }
  }
  $("#arvore tbody").innerHTML = html.join("") || `<tr><td colspan="9" class="discreto">Nenhum serviço para os filtros escolhidos.</td></tr>`;
  $("#contagem-filtro").textContent = filtrando
    ? `${visiveis.length} de ${d.servicos.length} serviços · total filtrado ${reais(visiveis.reduce((t, s) => t + (s.total || 0), 0))}`
    : `${d.servicos.length} serviços em ${d.grupos.length} grupos`;
}

function linhaGrupo(g) {
  const recolhido = estado.recolhidos.has(g.item);
  let confere = "";
  if (g.confere === true) confere = `<span class="confere ok" title="Soma dos serviços confere com o total do grupo">✔</span>`;
  else if (g.confere === false) confere = `<span class="confere erro" title="Soma dos serviços: ${reais(g.soma_servicos)}">✖ soma ${reais(g.soma_servicos)}</span>`;
  const total = g.total_planilha ? reais(g.total_planilha) : `<span class="discreto" title="Grupo sem total na planilha; mostrada a soma dos serviços">${reais(g.soma_servicos)}</span>`;
  const recuo = (g.nivel - 1) * 14;
  return `<tr class="grupo n${g.nivel} ${recolhido ? "recolhido" : ""}" data-grupo="${esc(g.item)}" data-linha="${g.linha_excel}">
    <td style="padding-left:${8 + recuo}px"><span class="seta">▾</span>${esc(g.item)}<span class="linha-excel">linha ${g.linha_excel}</span></td>
    <td></td><td></td>
    <td class="desc">${esc(g.descricao)} <span class="discreto">(${g.qtd_servicos} serviços)</span></td>
    <td></td><td></td><td></td>
    <td class="num">${total}${confere}</td><td></td></tr>`;
}

function linhaServico(s, nivel) {
  const nat = naturezaDe(s);
  const alterada = nat !== s.natureza_automatica;
  const opcoes = Object.entries(NATUREZAS).map(([k, r]) => `<option value="${k}" ${k === nat ? "selected" : ""}>${r}</option>`).join("");
  const titulo = s.divergencia !== null && s.divergencia !== undefined ? ` title="Quantidade × preço difere do total em ${reais(s.divergencia)}"` : "";
  return `<tr class="servico ${s.divergencia ? "divergente" : ""}" data-linha="${s.linha_excel}">
    <td style="padding-left:${22 + nivel * 14}px">${esc(s.item)}<span class="linha-excel">linha ${s.linha_excel}</span></td>
    <td>${esc(s.base)}</td><td>${esc(s.codigo)}</td>
    <td class="desc">${esc(s.descricao)}</td>
    <td>${esc(s.unidade)}</td>
    <td class="num">${qtd(s.quantidade)}</td>
    <td class="num">${reais(s.preco_unit)}</td>
    <td class="num total"${titulo}>${reais(s.total)}</td>
    <td><select class="natureza ${alterada ? "alterada" : ""}" data-linha="${s.linha_excel}" title="${alterada ? "Alterada (automática: " + NATUREZAS[s.natureza_automatica] + ")" : "Classificação automática pela unidade"}">${opcoes}</select></td>
  </tr>`;
}

$("#arvore tbody").addEventListener("click", (e) => {
  if (e.target.closest("select")) return;
  const tr = e.target.closest("tr.grupo");
  if (!tr) return;
  const item = tr.dataset.grupo;
  if (estado.recolhidos.has(item)) estado.recolhidos.delete(item);
  else estado.recolhidos.add(item);
  desenharArvore();
});
$("#arvore tbody").addEventListener("change", (e) => {
  const sel = e.target.closest("select.natureza");
  if (!sel) return;
  const linha = Number(sel.dataset.linha);
  const s = estado.dados.servicos.find((x) => x.linha_excel === linha);
  if (sel.value === s.natureza_automatica) delete estado.naturezas[linha];
  else estado.naturezas[linha] = sel.value;
  sel.classList.toggle("alterada", sel.value !== s.natureza_automatica);
  mostrarResumo();
});
["#filtro-grupo", "#filtro-natureza"].forEach((id) => $(id).addEventListener("change", desenharArvore));
let tempoBusca;
$("#filtro-texto").addEventListener("input", () => { clearTimeout(tempoBusca); tempoBusca = setTimeout(desenharArvore, 150); });
$("#btn-expandir").addEventListener("click", () => { estado.recolhidos.clear(); desenharArvore(); });
$("#btn-recolher").addEventListener("click", () => {
  estado.recolhidos = new Set(estado.dados.grupos.filter((g) => g.nivel === 1).map((g) => g.item));
  desenharArvore();
});

/* ------------------------------------------------------------------ salvar */

$("#btn-salvar").addEventListener("click", async () => {
  const msg = $("#msg-salvar");
  const prazo = Number($("#obra-prazo").value);
  const unidade = $("#obra-prazo-unidade").value;
  if (!(prazo > 0) || !unidade) {
    marcarPrazo();
    $("#obra-prazo").focus();
    return mensagem(msg, "Informe o prazo da obra (valor e unidade) — ele é obrigatório para as próximas etapas.", "erro");
  }
  const v = estado.dados.validacao;
  if (v && !v.ok && !confirm("A validação dos totais encontrou divergências. Deseja salvar mesmo assim?")) return;
  const bdi = $("#obra-bdi").value;
  const corpo = {
    token: estado.dados.token,
    obra: {
      nome: $("#obra-nome").value.trim() || null,
      prazo_valor: prazo,
      prazo_unidade: unidade,
      bdi: bdi === "" ? null : Number(bdi) / 100,
      desoneracao: $("#obra-desoneracao").value.trim() || null,
      referencias: $("#obra-referencias").value.split("\n").map((t) => t.trim()).filter(Boolean),
    },
    naturezas: estado.naturezas,
  };
  $("#btn-salvar").disabled = true;
  try {
    const r = await api("/api/importacoes", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo) });
    mensagem(msg, r.mensagem, "ok");
    carregarSalvas();
  } catch (err) {
    mensagem(msg, err.message, "erro");
  } finally {
    $("#btn-salvar").disabled = false;
  }
});

async function carregarSalvas() {
  try {
    const lista = await api("/api/importacoes");
    $("#salvas").hidden = lista.length === 0;
    $("#salvas tbody").innerHTML = lista
      .map((o) => `<tr><td>${o.id}</td><td>${esc((o.nome || "").slice(0, 80))}</td><td>${esc(o.arquivo)}</td><td>${o.qtd_servicos}</td><td>${reais(o.soma_servicos)}</td><td>${esc((o.data_importacao || "").replace("T", " "))}</td></tr>`)
      .join("");
  } catch (_) { /* sem lista */ }
}
carregarSalvas();
