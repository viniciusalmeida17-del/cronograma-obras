"use strict";

const obraId = obraDaUrl();
const est = { dados: null, abertas: new Set() };

async function carregar(url = `/api/obras/${obraId}/ligacao`, opcoes = {}) {
  try {
    est.dados = await api(url, opcoes);
    $("#tela").hidden = false;
    desenhar();
  } catch (err) {
    if (!mostrarErroBiblioteca($("#erro-biblioteca"), err)) mensagem($("#msg-geral"), err.message, "erro");
  }
}

function atividadesPorCodigo() {
  return Object.fromEntries(est.dados.atividades.map((a) => [a.codigo, a]));
}

function desenhar() {
  desenharResumo();
  desenharPendentes();
  desenharAtividades();
}

function desenharResumo() {
  const d = est.dados;
  const r = d.resumo;
  $("#nome-obra").textContent = `Obra nº ${d.obra.numero} · ${d.obra.nome || d.obra.arquivo}`;
  const faixa = $("#faixa");
  faixa.className = "faixa " + (r.pendentes ? "aviso" : "ok");
  faixa.textContent = (r.pendentes ? "⚠ " : "✔ ") + r.texto;
  const somaAtiv = d.atividades.reduce((t, a) => t + a.total_bdi, 0);
  const caixas = [
    ["Serviços", r.total],
    ["Automáticos", r.por_status.automatico],
    ["Pela memória", r.por_status.memoria],
    ["Confirmados", r.por_status.confirmado],
    ["Pendentes", r.pendentes],
    ["Atividades com serviços", d.atividades.filter((a) => a.n_itens).length],
    ["Total ligado (com BDI)", reais(somaAtiv)],
    ["Total da obra (com BDI)", reais(d.total_bdi)],
  ];
  $("#numeros").innerHTML = caixas.map(([t, v]) => `<div class="numero"><span>${t}</span><b>${v}</b></div>`).join("");
  $("#btn-seguir").disabled = r.pendentes > 0;
  $("#btn-seguir").title = r.pendentes ? "Resolva as pendências primeiro" : "";
}

function textoGrupos(s) {
  return s.grupos.map(esc).join(" <span class='discreto'>›</span> ");
}

function desenharPendentes() {
  const pend = est.dados.servicos.filter((s) => s.status_ligacao === "ambiguo" || s.status_ligacao === "sem_regra");
  $("#pendentes").hidden = pend.length === 0;
  $("#qtd-pendentes").textContent = pend.length;
  const porCod = atividadesPorCodigo();
  $("#lista-pendentes").innerHTML = pend.map((s) => `
    <div class="pendente" data-id="${s.id}">
      <div class="pendente-cab">
        <b>${esc(s.item)}</b> <span class="discreto">linha ${s.linha_excel} · ${esc(s.base || "")} ${esc(s.codigo || "")} · ${esc(s.unidade)} · ${reais(s.total_bdi)}</span>
        <span class="selo ${s.status_ligacao}">${ROTULO_STATUS[s.status_ligacao]}</span>
      </div>
      <div class="pendente-grupos">${textoGrupos(s)}</div>
      <div class="pendente-desc">${esc(s.descricao)}</div>
      <div class="pendente-opcoes">
        ${s.candidatas.map((c) => `<button type="button" class="opcao" data-escolher="${c}">${c} — ${esc(porCod[c]?.nome || "")}</button>`).join("")}
        <button type="button" class="secundario" data-trocar="${s.id}">${s.candidatas.length ? "Outra atividade…" : "Escolher atividade…"}</button>
      </div>
    </div>`).join("");
}

function servicoPassa(s, termo, status) {
  if (status && s.status_ligacao !== status) return false;
  if (!termo) return true;
  return semAcento(`${s.item} ${s.codigo} ${s.descricao} ${s.grupos.join(" ")}`).includes(termo);
}

function desenharAtividades() {
  const d = est.dados;
  const termo = semAcento($("#busca").value.trim());
  const status = $("#filtro-status").value;
  const vazias = $("#mostrar-vazias").checked;
  const porAtiv = {};
  d.servicos.forEach((s) => {
    if (!s.atividade_biblioteca) return;
    (porAtiv[s.atividade_biblioteca] ||= []).push(s);
  });
  const filtrando = Boolean(termo || status);
  const html = [];
  let etapaAtual = null;
  for (const a of d.atividades) {
    const todos = porAtiv[a.codigo] || [];
    const ativCasa = termo && semAcento(`${a.codigo} ${a.nome} ${a.etapa}`).includes(termo);
    const servs = todos.filter((s) => (ativCasa && !status) || servicoPassa(s, termo, status));
    if (!todos.length && !(vazias && !filtrando)) continue;
    if (filtrando && !servs.length && !ativCasa) continue;
    if (a.etapa !== etapaAtual) {
      etapaAtual = a.etapa;
      html.push(`<h3 class="titulo-etapa">${esc(a.etapa)}</h3>`);
    }
    const aberta = est.abertas.has(a.codigo) || (filtrando && servs.length > 0 && servs.length < 40);
    html.push(`
      <details class="atividade" data-codigo="${a.codigo}" ${aberta ? "open" : ""}>
        <summary>
          <span class="cod">${a.codigo}</span>
          <span class="nome">${esc(a.nome)}</span>
          <span class="selo-tipo ${a.tipo}">${ROTULO_TIPO[a.tipo]}</span>
          <span class="qtd">${a.n_itens} ${a.n_itens === 1 ? "item" : "itens"}</span>
          <span class="valor">${reais(a.total_bdi)}</span>
        </summary>
        ${servs.length ? tabelaServicos(servs) : `<p class="discreto vazio">Nenhum serviço ligado a esta atividade.</p>`}
      </details>`);
  }
  $("#lista-atividades").innerHTML = html.join("") || `<p class="discreto">Nada encontrado.</p>`;
}

function tabelaServicos(servs) {
  return `<table class="servicos"><thead><tr><th>Item</th><th>Código</th><th class="desc">Descrição</th><th>Und</th><th class="num">Quant.</th><th class="num">Total c/ BDI</th><th>Ligação</th><th></th></tr></thead><tbody>
    ${servs.map((s) => `<tr>
      <td class="nowrap">${esc(s.item)}<span class="linha-excel">linha ${s.linha_excel}</span></td>
      <td class="nowrap">${esc(s.codigo)}<span class="linha-excel">${esc(s.base || "")}</span></td>
      <td class="desc">${esc(s.descricao)}<span class="linha-excel">${textoGrupos(s)}</span></td>
      <td>${esc(s.unidade)}</td>
      <td class="num">${qtd(s.quantidade)}</td>
      <td class="num">${reais(s.total_bdi)}</td>
      <td><span class="selo ${s.status_ligacao}">${ROTULO_STATUS[s.status_ligacao]}${s.regra_usada ? ` · regra ${s.regra_usada}` : ""}</span></td>
      <td><button type="button" class="secundario pequeno" data-trocar="${s.id}">Trocar</button></td>
    </tr>`).join("")}
  </tbody></table>`;
}

/* ------------------------------------------------------------ escolha / troca */

let servicoEmEscolha = null;

function abrirSeletor(servico) {
  servicoEmEscolha = servico;
  const porCod = atividadesPorCodigo();
  $("#seletor-servico").innerHTML = `<b>${esc(servico.item)}</b> · ${esc(servico.codigo || "")} · ${esc(servico.unidade)}<br>${esc(servico.descricao)}
    <div class="discreto">${textoGrupos(servico)}</div>
    ${servico.atividade_biblioteca ? `<div>Atual: <b>${servico.atividade_biblioteca}</b> — ${esc(porCod[servico.atividade_biblioteca]?.nome || "")}</div>` : ""}`;
  $("#seletor-candidatas").innerHTML = servico.candidatas.length
    ? `<p class="discreto">Empatadas pelas regras:</p>` + servico.candidatas.map((c) => `<button type="button" class="opcao" data-escolher="${c}">${c} — ${esc(porCod[c]?.nome || "")}</button>`).join(" ")
    : "";
  $("#seletor-busca").value = "";
  desenharListaSeletor();
  $("#seletor").showModal();
  $("#seletor-busca").focus();
}

function desenharListaSeletor() {
  const termo = semAcento($("#seletor-busca").value.trim());
  const lista = est.dados.atividades.filter((a) => !termo || semAcento(`${a.codigo} ${a.nome} ${a.etapa}`).includes(termo));
  $("#seletor-lista").innerHTML = lista.map((a) => `<li><button type="button" data-escolher="${a.codigo}" class="${a.codigo === servicoEmEscolha?.atividade_biblioteca ? "atual" : ""}">
      <span class="cod">${a.codigo}</span> ${esc(a.nome)} <span class="discreto">· ${esc(a.etapa)}</span></button></li>`).join("")
    || `<li class="discreto">Nenhuma atividade encontrada.</li>`;
}
$("#seletor-busca").addEventListener("input", desenharListaSeletor);
$("#seletor-busca").addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    const primeiro = $("#seletor-lista button");
    if (primeiro) primeiro.click();
  }
});

async function escolher(servico, atividade) {
  const semelhantes = est.dados.servicos.filter((s) => s.id !== servico.id && s.codigo === servico.codigo
    && s.base === servico.base && s.item_grupo === servico.item_grupo);
  const ids = [servico.id];
  if (semelhantes.length && confirm(`Aplicar também aos outros ${semelhantes.length} serviço(s) com o mesmo código (${servico.codigo}) neste grupo?\n\n`
      + semelhantes.map((s) => `${s.item} — ${s.descricao.slice(0, 80)}`).join("\n"))) {
    ids.push(...semelhantes.map((s) => s.id));
  }
  est.abertas.add(atividade);
  await carregar(`/api/obras/${obraId}/ligacao`, { json: { servicos: ids, atividade } });
  mensagem($("#msg-geral"), `${ids.length} serviço(s) ligado(s) a ${atividade}. A escolha foi guardada na memória para as próximas obras.`, "ok");
}

document.addEventListener("click", (e) => {
  const btnTrocar = e.target.closest("[data-trocar]");
  if (btnTrocar) {
    const s = est.dados.servicos.find((x) => x.id === Number(btnTrocar.dataset.trocar));
    abrirSeletor(s);
    return;
  }
  const btnEscolher = e.target.closest("[data-escolher]");
  if (btnEscolher) {
    const noDialogo = btnEscolher.closest("#seletor");
    const servico = noDialogo ? servicoEmEscolha : est.dados.servicos.find((x) => x.id === Number(btnEscolher.closest("[data-id]").dataset.id));
    if (noDialogo) $("#seletor").close();
    escolher(servico, btnEscolher.dataset.escolher);
  }
});

$("#lista-atividades").addEventListener("toggle", (e) => {
  const det = e.target.closest("details.atividade");
  if (!det) return;
  if (det.open) est.abertas.add(det.dataset.codigo);
  else est.abertas.delete(det.dataset.codigo);
}, true);

let tempo;
$("#busca").addEventListener("input", () => { clearTimeout(tempo); tempo = setTimeout(desenharAtividades, 150); });
$("#filtro-status").addEventListener("change", desenharAtividades);
$("#mostrar-vazias").addEventListener("change", desenharAtividades);
$("#btn-abrir").addEventListener("click", () => { est.dados.atividades.forEach((a) => est.abertas.add(a.codigo)); desenharAtividades(); });
$("#btn-fechar").addEventListener("click", () => { est.abertas.clear(); $("#busca").value = ""; desenharAtividades(); });

$("#btn-refazer").addEventListener("click", async () => {
  if (!confirm("Rodar o reconhecimento automático de novo? As escolhas que você confirmou serão mantidas.")) return;
  await carregar(`/api/obras/${obraId}/ligacao/refazer`, { method: "POST" });
  mensagem($("#msg-geral"), "Reconhecimento refeito.", "ok");
});

$("#btn-seguir").addEventListener("click", async () => {
  const msg = $("#msg-seguir");
  $("#btn-seguir").disabled = true;
  mensagem(msg, "Montando a rede de atividades…");
  try {
    await api(`/api/obras/${obraId}/rede`, { method: "POST" });
    location.href = `/sequencia?obra=${obraId}`;
  } catch (err) {
    if (!mostrarErroBiblioteca($("#erro-biblioteca"), err)) mensagem(msg, err.message, "erro");
    $("#btn-seguir").disabled = false;
  }
});

if (!obraId) mensagem($("#msg-geral"), "Obra não informada. Volte à tela inicial e escolha uma importação salva.", "erro");
else carregar();
