"use strict";
/* Funções compartilhadas pelas telas das etapas 3 em diante. */

const $ = (sel, raiz = document) => raiz.querySelector(sel);
const $$ = (sel, raiz = document) => [...raiz.querySelectorAll(sel)];
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
function obraDaUrl() {
  return Number(new URLSearchParams(location.search).get("obra")) || null;
}

class ErroApi extends Error {
  constructor(corpo, status) {
    super(corpo.erro || `Erro ${status}`);
    this.corpo = corpo;
  }
}

async function api(url, opcoes = {}) {
  if (opcoes.json !== undefined) {
    opcoes = { ...opcoes, method: opcoes.method || "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(opcoes.json) };
  }
  const resp = await fetch(url, opcoes);
  const corpo = await resp.json().catch(() => ({ erro: "Resposta inválida do servidor." }));
  if (!resp.ok) throw new ErroApi(corpo, resp.status);
  if ((opcoes.method || "GET").toUpperCase() !== "GET") avisarMudanca();
  return corpo;
}

/** Algo foi gravado: a barra de etapas (etapas.js) confere de novo até onde a obra chegou. */
let _tempoMudanca;
function avisarMudanca() {
  clearTimeout(_tempoMudanca);
  _tempoMudanca = setTimeout(() => window.dispatchEvent(new Event("obra-mudou")), 300);
}

/** Mostra os erros de validação da biblioteca (com aba e linha do Excel). */
function mostrarErroBiblioteca(el, err) {
  const erros = err.corpo?.erros_biblioteca;
  if (!erros) return false;
  el.hidden = false;
  el.innerHTML = `<h2>A biblioteca de atividades tem erros</h2>
    <p>Corrija o arquivo <code>dados/biblioteca_atividades.xlsx</code> no Excel e recarregue esta página.</p>
    <ul>${erros.map((e) => `<li>${e.aba ? `<b>${esc(e.aba)}</b>` : ""}${e.linha ? `, linha ${e.linha}` : ""}${e.aba || e.linha ? ": " : ""}${esc(e.mensagem)}</li>`).join("")}</ul>`;
  return true;
}

const ROTULO_STATUS = {
  automatico: "automático",
  memoria: "memória",
  confirmado: "confirmado",
  ambiguo: "ambíguo",
  sem_regra: "sem regra",
};
const ROTULO_TIPO = { rigida: "rígida", flexivel: "flexível", aguardar: "aguardar", indireta: "indireta" };
