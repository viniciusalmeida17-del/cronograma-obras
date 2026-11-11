"use strict";

const obraId = obraDaUrl();
const est = { d: null, aba: null, abertas: new Set() };
const ORIGENS = {
  composicao: { rotulo: "composição", cor: "#2f6fb5" },
  banco: { rotulo: "banco", cor: "#6b8fc7" },
  manual: { rotulo: "manual", cor: "#2e8b57" },
  referencia: { rotulo: "referência", cor: "#1baf7a" },
  estimado: { rotulo: "estimado", cor: "#e0b000" },
  sem_mao_de_obra: { rotulo: "sem mão de obra", cor: "#c8cdd4" },
};
const fmtH = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
const fmtH4 = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 4 });
const horas = (v) => fmtH.format(v || 0);
const soma = (obj) => Object.values(obj || {}).reduce((t, v) => t + v, 0);

async function chamar(url, opcoes, msgEl = $("#msg-geral"), sucesso = "") {
  try {
    est.d = await api(url, opcoes);
    $("#enviar-arquivo").hidden = true;
    $("#tela").hidden = false;
    desenhar();
    if (sucesso) mensagem(msgEl, sucesso, "ok");
    return true;
  } catch (err) {
    if (err.corpo?.precisa_arquivo) {
      $("#enviar-arquivo").hidden = false;
      $("#tela").hidden = true;
    }
    mensagem(msgEl, err.message, "erro");
    return false;
  }
}

function desenhar() {
  const d = est.d;
  $("#nome-obra").textContent = `Obra nº ${d.obra.numero} · ${d.obra.nome || d.obra.arquivo}`;
  $("#link-sequencia").href = `/sequencia?obra=${obraId}`;
  $("#link-cronograma").href = `/cronograma?obra=${obraId}`;
  $("#link-cronograma").classList.toggle("desabilitado", d.pendencias.length > 0);
  $("#link-cronograma").title = d.pendencias.length ? "Resolva as pendências antes do cronograma" : "Cronograma com datas e equipes";
  const pend = d.pendencias.length;
  $("#faixa").className = "faixa " + (pend ? "aviso" : "ok");
  $("#faixa").textContent = pend
    ? `⚠ ${pend} pendência(s) obrigatória(s) antes do cronograma — veja o Resumo da obra.`
    : "✔ Sem pendências: todas as atividades têm execução e duração.";
  const ativs = d.atividades;
  const caixas = [
    ["Atividades", ativs.length],
    ["Horas ajustadas (própria)", horas(d.resumo_funcoes.reduce((t, f) => t + f.horas_ajustadas, 0))],
    ["Horas por dia", fmtH4.format(d.parametros.horas_por_dia)],
    ["Rendimento", Math.round(d.parametros.rendimento * 100) + "%"],
    ["Cobertura com horas", d.cobertura_com_horas.toLocaleString("pt-BR") + "%"],
    ["Pendências", pend],
  ];
  $("#numeros").innerHTML = caixas.map(([t, v]) => `<div class="numero"><span>${t}</span><b>${v}</b></div>`).join("");
  const abas = d.abas_composicoes || [];
  $("#abas-composicoes").textContent = abas.length
    ? "Composições encontradas: " + abas.map((a) => `${a.aba} (${a.formato_a + a.formato_b})`).join(", ")
    : "Nenhuma composição encontrada no arquivo: horas vindas do banco de coeficientes ou estimadas.";

  const semExec = ativs.filter((a) => !a.execucao).length;
  $("#cont-execucao").hidden = !semExec;
  $("#cont-execucao").textContent = semExec;
  $("#cont-pendencias").hidden = !pend;
  $("#cont-pendencias").textContent = pend;
  if (!est.aba) est.aba = semExec ? "execucao" : "atividades";
  mostrarAba(est.aba);
  desenharParametros();
  desenharExecucao();
  desenharAtividades();
  desenharResumo();
}

function mostrarAba(nome) {
  est.aba = nome;
  $$(".aba").forEach((s) => { s.hidden = s.id !== `aba-${nome}`; });
  $$("#abas button").forEach((b) => b.classList.toggle("ativa", b.dataset.aba === nome));
}
$("#abas").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) mostrarAba(b.dataset.aba); });

/* ------------------------------------------------------------ 1. parâmetros */

function desenharParametros() {
  const p = est.d.parametros;
  const f = $("#form-parametros");
  f.horas_semana.value = p.horas_semana;
  f.dias_semana.value = String(p.dias_semana);
  f.rendimento.value = Math.round(p.rendimento * 1000) / 10;
  f.volume_caminhao.value = p.volume_caminhao;
  f.caminhoes_dia.value = p.caminhoes_dia;
  const j = est.d.juntar || { possivel: {}, obra: {} };
  $("#lista-juntar").innerHTML = Object.entries(j.possivel).map(([fn, destino]) => `<label class="inline">
      <input type="checkbox" name="juntar" data-funcao="${esc(fn)}" data-destino="${esc(destino)}" ${j.obra && j.obra[fn] ? "checked" : ""}>
      ${esc(fn)} → ${esc(destino)}</label>`).join("") || '<p class="discreto">A tabela de funções não tem a aba Juntar funções.</p>';
  $("#horas-dia").textContent = fmtH4.format(p.horas_por_dia) + " h";
  const o = est.d.obra;
  $("#prazo-licitacao").textContent = o.prazo_valor ? `${fmtH4.format(o.prazo_valor)} ${o.prazo_unidade || ""} (${fmtH.format(est.d.semanas_prazo || 0)} semanas)` : "—";
  $("#lista-mudancas").innerHTML = (p.mudancas_jornada || []).map(linhaMudanca).join("") || `<p class="discreto vazio-mud">Nenhuma mudança cadastrada.</p>`;
}
function linhaMudanca(m = {}) {
  return `<div class="mudanca">A partir de <input type="date" name="data" value="${esc(m.a_partir_de || "")}">
    <input type="number" name="horas" min="1" max="80" step="0.5" value="${m.horas_semana ?? ""}"> h/semana
    <button type="button" class="secundario pequeno" data-remover-mudanca>remover</button></div>`;
}
$("#btn-add-mudanca").addEventListener("click", () => {
  $(".vazio-mud")?.remove();
  $("#lista-mudancas").insertAdjacentHTML("beforeend", linhaMudanca());
});
$("#lista-mudancas").addEventListener("click", (e) => { if (e.target.closest("[data-remover-mudanca]")) e.target.closest(".mudanca").remove(); });
$("#form-parametros").addEventListener("submit", (e) => {
  e.preventDefault();
  const f = e.target;
  const mudancas = $$(".mudanca", f).map((m) => ({ a_partir_de: $("[name=data]", m).value, horas_semana: $("[name=horas]", m).value }))
    .filter((m) => m.a_partir_de || m.horas_semana);
  chamar(`/api/obras/${obraId}/parametros`, { json: {
    horas_semana: f.horas_semana.value, dias_semana: f.dias_semana.value,
    rendimento: Number(f.rendimento.value) / 100, mudancas_jornada: mudancas,
    volume_caminhao: f.volume_caminhao.value, caminhoes_dia: f.caminhoes_dia.value,
    juntar: Object.fromEntries($$("[name=juntar]", f).filter((i) => i.checked).map((i) => [i.dataset.funcao, i.dataset.destino])),
  } }, $("#msg-parametros"), "Parâmetros salvos; durações recalculadas.");
});

/* ------------------------------------------------------------ 2. execução */

function desenharExecucao() {
  const ativs = est.d.atividades;
  const porEtapa = {};
  ativs.forEach((a) => (porEtapa[a.etapa] ||= []).push(a));
  const pendentesPrimeiro = Object.entries(porEtapa).sort(([, a], [, b]) =>
    (b.some((x) => !x.execucao) - a.some((x) => !x.execucao)) || a[0].ordem_biblioteca - b[0].ordem_biblioteca);
  $("#lista-execucao").innerHTML = pendentesPrimeiro.map(([etapa, lista]) => {
    const falta = lista.filter((a) => !a.execucao).length;
    return `<div class="grupo-execucao ${falta ? "com-pendencia" : ""}">
      <div class="grupo-cab"><h3>${esc(etapa)} ${falta ? `<span class="contador erro">${falta}</span>` : ""}</h3>
        <span class="botoes">Aplicar à etapa inteira:
          <button type="button" class="secundario pequeno" data-etapa="${esc(etapa)}" data-exec="propria">Própria</button>
          <button type="button" class="secundario pequeno" data-etapa="${esc(etapa)}" data-exec="terceirizada">Terceirizada</button></span></div>
      ${lista.map((a) => `<div class="linha-execucao ${a.execucao ? "" : "sem-resposta"}">
        <span class="cod">${a.codigo}</span><span class="nome">${esc(a.nome)}${a.execucao_padrao === "perguntar" ? ' <span class="selo">perguntar</span>' : ""}</span>
        <span class="discreto">${horas(soma(a.horas_brutas))} h</span>
        <span class="alternar">
          <button type="button" data-ativ="${a.codigo}" data-exec="propria" class="${a.execucao === "propria" ? "ativo" : ""}">Própria</button>
          <button type="button" data-ativ="${a.codigo}" data-exec="terceirizada" class="${a.execucao === "terceirizada" ? "ativo" : ""}">Terceirizada</button>
        </span></div>`).join("")}
    </div>`;
  }).join("");
}
$("#lista-execucao").addEventListener("click", (e) => {
  const b = e.target.closest("[data-exec]");
  if (!b) return;
  const codigos = b.dataset.ativ ? [b.dataset.ativ]
    : est.d.atividades.filter((a) => a.etapa === b.dataset.etapa).map((a) => a.codigo);
  chamar(`/api/obras/${obraId}/execucao`, { json: { atividades: codigos, execucao: b.dataset.exec } });
});

/* ------------------------------------------------------------ 3. atividades */

function barraOrigens(porOrigem) {
  const total = soma(porOrigem);
  if (!total) return `<span class="discreto">sem horas</span>`;
  return `<div class="barra" title="${Object.entries(porOrigem).map(([o, h]) => `${ORIGENS[o]?.rotulo || o}: ${horas(h)} h`).join(" · ")}">`
    + Object.entries(porOrigem).map(([o, h]) => `<span style="width:${(100 * h) / total}%;background:${ORIGENS[o]?.cor || "#999"}"></span>`).join("")
    + "</div>";
}

function textoDuracao(a) {
  if (!a.duracao) return `<span class="falta">informar</span>`;
  const um = a.duracao.dias === 1;
  const u = a.duracao.unidade === "corridos" ? (um ? "dia corrido" : "dias corridos") : (um ? "dia útil" : "dias úteis");
  const tipo = { calculada: "", fixa: " (fixa)", manual: " (manual)" }[a.duracao.tipo];
  return `<b>${a.duracao.dias}</b> ${u}${tipo}`;
}

function desenharAtividades() {
  $("#legenda-origens").innerHTML = Object.values(ORIGENS).map((o) => `<span><i style="background:${o.cor}"></i>${o.rotulo}</span>`).join("");
  const servPorAtiv = {};
  est.d.servicos.forEach((s) => (servPorAtiv[s.atividade] ||= []).push(s));
  $("#tabela-atividades tbody").innerHTML = est.d.atividades.map((a) => {
    const aberta = est.abertas.has(a.codigo);
    const bruto = soma(a.horas_brutas), ajust = soma(a.horas_ajustadas), eq = soma(a.horas_equipamento);
    const pend = !a.duracao || !a.execucao;
    return `<tr class="linha-ativ ${aberta ? "aberta" : ""} ${pend ? "pendente-linha" : ""}" data-codigo="${a.codigo}">
      <td><span class="seta">${aberta ? "▾" : "▸"}</span> <b>${a.codigo}</b> ${esc(a.nome)}<span class="linha-excel">${a.n_itens} ${a.n_itens === 1 ? "item" : "itens"} · ${esc(a.etapa)}${a.trocas_aplicadas?.length ? ` · <span class="troca" title="${esc(a.trocas_aplicadas.map(textoTroca).join("\n"))}">função trocada</span>` : ""}</span></td>
      <td>${a.execucao ? `<span class="selo-exec ${a.execucao}">${a.execucao === "propria" ? "própria" : "terceirizada"}</span>` : '<span class="falta">escolher</span>'}</td>
      <td>${esc(a.funcao_principal || "—")}</td>
      <td class="num" title="${Object.entries(a.horas_ajustadas).map(([f, h]) => `${f}: ${horas(h)} h`).join("\n")}">${horas(bruto)} → <b>${horas(ajust)}</b></td>
      <td class="num">${eq ? horas(eq) : "—"}</td>
      <td class="num">${a.equipe_padrao}${a.equipe_padrao !== a.equipe_padrao_biblioteca ? "*" : ""}</td>
      <td class="num">${textoDuracao(a)}</td>
      <td class="col-barra">${barraOrigens(a.horas_por_origem)}</td>
    </tr>${aberta ? detalheAtividade(a, servPorAtiv[a.codigo] || []) : ""}`;
  }).join("");
}

function textoTroca(t) {
  return `${t.origem} → ${t.destino}: ${horas(t.horas)} h`;
}

function formTrocas(a) {
  const mudou = (a.trocar_funcoes || "") !== (a.trocar_funcoes_biblioteca || "");
  const aplicadas = a.trocas_aplicadas?.length
    ? a.trocas_aplicadas.map((t) => `<span class="troca">${esc(textoTroca(t))}</span>`).join(" ")
    : (a.trocar_funcoes && a.execucao === "terceirizada" ? '<span class="discreto">ignoradas: atividade terceirizada</span>'
      : '<span class="discreto">nenhuma</span>');
  return `<form class="form-trocas" data-codigo="${a.codigo}">
      <label class="largo">Trocar funções <small>(só nesta obra; ex.: Pintor &gt; Servente; Eletricista &gt; Pedreiro — as horas não mudam, só a função)</small>
        <input name="trocar_funcoes" value="${esc(a.trocar_funcoes || "")}" list="lista-funcoes" autocomplete="off" placeholder="sem troca"></label>
      <label class="inline"><input type="checkbox" name="salvar_biblioteca"> salvar também na biblioteca padrão</label>
      <button type="submit" class="secundario">Salvar trocas</button>
      <p class="discreto">Trocas aplicadas: ${aplicadas}${mudou ? ` · <b>mudada nesta obra</b> (biblioteca: ${esc(a.trocar_funcoes_biblioteca || "sem troca")})` : ""}</p>
      <p class="mensagem msg-trocas"></p>
      <datalist id="lista-funcoes">${(est.d.funcoes_empresa || []).map((f) => `<option value="${esc(f)}">`).join("")}</datalist>
    </form>`;
}

function detalheAtividade(a, servs) {
  const c = a.calculo;
  const equipe = c ? Object.entries(c.equipe).map(([f, n]) => `${n} ${esc(f)} (${fmtH.format(c.dias_por_funcao[f])} d)`).join(" · ") : "—";
  const maquinas = c && Object.keys(c.dias_por_equipamento).length
    ? Object.entries(c.dias_por_equipamento).map(([e, dd]) => `${c.maquinas[e]}× ${esc(e.slice(0, 60))}: ${fmtH.format(dd)} d`).join(" · ") : "";
  return `<tr class="detalhe"><td colspan="8">
    <form class="form-atividade" data-codigo="${a.codigo}">
      <label>Equipe padrão (${esc(a.funcao_principal || "função principal")})
        <input type="number" name="equipe_padrao" min="1" max="${a.equipe_max}" value="${a.equipe_padrao}"> <small>máx. ${a.equipe_max}</small></label>
      <label>Rendimento desta atividade (%)
        <input type="number" name="rendimento" min="30" max="150" placeholder="${Math.round(est.d.parametros.rendimento * 100)} (obra)" value="${a.rendimento_especifico ? Math.round(a.rendimento_especifico * 1000) / 10 : ""}"></label>
      ${Object.keys(a.horas_equipamento).length ? `<fieldset class="maquinas"><legend>Máquinas de cada equipamento</legend>
        ${Object.entries(a.horas_equipamento).map(([e, h]) => `<label class="inline" title="${esc(e)}">
          <input type="number" name="maquina" min="1" max="20" step="1" data-equip="${esc(e)}" value="${(c && c.maquinas && c.maquinas[e]) || 1}">
          <span>${esc(e.length > 70 ? e.slice(0, 70) + "…" : e)} <small>(${horas(h)} h)</small></span></label>`).join("")}
      </fieldset>` : ""}
      <label>Duração manual (dias úteis)
        <input type="number" name="duracao_manual" min="1" step="1" value="${a.duracao_manual ?? ""}" placeholder="${a.duracao && a.duracao.tipo !== "manual" ? a.duracao.dias : "obrigatória"}"></label>
      ${a.execucao === "terceirizada" ? (() => {
        const pr = (est.d.producao || {})[a.codigo] || {};
        return `<label>ou produção por dia (${esc(pr.unidade || "un")}/dia)
          <input type="number" name="producao_dia" min="0.01" step="any" value="${pr.producao_dia ?? ""}" placeholder="ex.: 150">
          <small>${pr.quantidade ? `${fmtH4.format(pr.quantidade)} ${esc(pr.unidade || "")}` : ""}${pr.dias ? ` → ${pr.dias} dias úteis` : ""}${pr.origem === "padrao" ? " (padrão de outra obra)" : ""}</small></label>`;
      })() : ""}
      <button type="submit" class="primario">Aplicar</button>
      <p class="mensagem msg-ativ"></p>
    </form>
    ${formTrocas(a)}
    <p class="discreto">Equipe padrão: ${equipe}${maquinas ? `<br>Equipamentos: ${maquinas}` : ""}${c ? `<br>Duração exata ${fmtH.format(c.dias_exatos)} dias (limitada por ${{ equipamento: "equipamento", concretagem: `concretagem: ${fmtH.format(a.volume_m3 || 0)} m³` }[c.limitante] || "mão de obra"})` : ""}${a.duracao_fixa_dias ? `<br>Duração fixa da biblioteca: ${a.duracao_fixa_dias} dias corridos` : ""}</p>
    <table class="servicos"><thead><tr><th>Item</th><th class="desc">Serviço</th><th class="num">Quant.</th><th>Origem</th><th>Horas por função (h/un → total)</th><th></th></tr></thead><tbody>
    ${servs.map(linhaServico).join("")}
    </tbody></table>
  </td></tr>`;
}

function linhaServico(s) {
  const porFuncao = {};
  s.horas.forEach((h) => { (porFuncao[h.funcao] ||= []).push(h); });
  const htmlHoras = Object.entries(porFuncao).map(([f, hs]) => hs.map((h) =>
    `<div class="${h.origem === "estimado" ? "estimado" : ""}">${esc(f)}: ${fmtH4.format(h.horas_un)} → ${horas(h.horas_total)} h${h.origem !== s.origem ? ` <small>(${ORIGENS[h.origem]?.rotulo})</small>` : ""}</div>`).join("")).join("")
    || '<span class="discreto">—</span>';
  const pend = s.pendentes.length ? `<details class="pendentes-sub"><summary>${s.pendentes.length} subcomposição(ões) pendente(s)</summary>
    <table class="simples"><thead><tr><th>Código</th><th>Descrição</th><th class="num">Coef.</th><th class="num">R$/un</th><th class="num">Horas estimadas</th><th></th></tr></thead><tbody>
    ${s.pendentes.map((p) => `<tr><td>${esc(p.codigo || "—")}${p.via?.length ? `<small class="discreto"> via ${esc(p.via.join(" › "))}</small>` : ""}</td><td>${esc((p.descricao || "").slice(0, 110))}</td>
      <td class="num">${fmtH4.format(p.coeficiente || 0)} ${esc(p.unidade || "")}</td><td class="num">${reais(p.total_linha)}</td>
      <td class="num estimado">${p.horas_estimadas != null ? horas(p.horas_estimadas) : "—"}</td>
      <td>${p.codigo ? `<button type="button" class="secundario pequeno" data-sub='${esc(JSON.stringify({ codigo: p.codigo, descricao: p.descricao, unidade: p.unidade }))}'>Digitar h/un</button>` : ""}</td></tr>`).join("")}
    </tbody></table></details>` : "";
  return `<tr class="${s.origem === "estimado" ? "linha-estimada" : ""}">
    <td class="nowrap">${esc(s.item)}<span class="linha-excel">linha ${s.linha_excel}</span></td>
    <td class="desc">${esc(s.descricao)}<span class="linha-excel">${esc(s.base || "")} ${esc(s.codigo || "")}</span>${pend}</td>
    <td class="num">${fmtH4.format(s.quantidade || 0)} ${esc(s.unidade)}</td>
    <td><span class="selo-origem ${s.origem}">${ORIGENS[s.origem]?.rotulo}</span>${s.estimativa ? `<small class="discreto"><br>razão da ${s.estimativa.nivel}</small>` : ""}${s.estimativa?.limitada ? `<br><span class="limitada" title="Sem o limite: ${horas(s.estimativa.horas_sem_limite)} h">estimativa limitada, revisar</span>` : ""}</td>
    <td class="horas-servico">${htmlHoras}</td>
    <td><button type="button" class="secundario pequeno" data-servico="${s.id}">Digitar h/un</button></td>
  </tr>`;
}

$("#tabela-atividades").addEventListener("click", (e) => {
  if (e.target.closest("button, input, select, form, details")) {
    const bServ = e.target.closest("[data-servico]");
    const bSub = e.target.closest("[data-sub]");
    if (bServ) abrirHorasServico(Number(bServ.dataset.servico));
    if (bSub) abrirHorasSub(JSON.parse(bSub.dataset.sub));
    return;
  }
  const tr = e.target.closest("tr.linha-ativ");
  if (!tr) return;
  const c = tr.dataset.codigo;
  est.abertas.has(c) ? est.abertas.delete(c) : est.abertas.add(c);
  desenharAtividades();
});
$("#tabela-atividades").addEventListener("submit", (e) => {
  const ft = e.target.closest(".form-trocas");
  if (ft) {
    e.preventDefault();
    const cod = ft.dataset.codigo;
    const salvarBib = ft.salvar_biblioteca.checked;
    if (salvarBib && !confirm(`Gravar as trocas de ${cod} também no Excel da biblioteca padrão? (Uma cópia de segurança será feita antes.)`)) return;
    chamar(`/api/obras/${obraId}/atividade/${cod}/trocas`, { json: { trocar_funcoes: ft.trocar_funcoes.value, salvar_biblioteca: salvarBib } },
      $(".msg-trocas", ft), "").then((ok) => {
      if (ok) mensagem($("#msg-geral"), `${cod}: trocas de função salvas; horas, equipes e duração recalculadas.`
        + (est.d.backup_biblioteca ? ` Biblioteca padrão gravada (cópia de segurança: ${est.d.backup_biblioteca}).` : ""), "ok");
    });
    return;
  }
  const f = e.target.closest(".form-atividade");
  if (!f) return;
  e.preventDefault();
  const maquinas = {};
  $$("[name=maquina]", f).forEach((i) => { maquinas[i.dataset.equip] = i.value; });
  const extra = {};
  if (f.producao_dia && f.producao_dia.value !== String(((est.d.producao || {})[f.dataset.codigo] || {}).producao_dia ?? "")) {
    extra.producao_dia = f.producao_dia.value;
  }
  chamar(`/api/obras/${obraId}/atividade/${f.dataset.codigo}`, { json: {
    ...extra,
    equipe_padrao: f.equipe_padrao.value, rendimento: f.rendimento.value, duracao_manual: extra.producao_dia ? undefined : f.duracao_manual.value, maquinas,
  } }, $(".msg-ativ", f), "").then((ok) => {
    // a tabela é redesenhada (o formulário some e volta): a confirmação vai para o topo; erros ficam no formulário
    if (ok) mensagem($("#msg-geral"), `${f.dataset.codigo} atualizada: duração recalculada.`, "ok");
  });
});

/* ------------------------------------------------------------ horas digitadas */

let destinoHoras = null;
function abrirDialogoHoras(titulo, contexto, linhas, podeLimpar) {
  $("#horas-titulo").textContent = titulo;
  $("#horas-contexto").innerHTML = contexto;
  $("#lista-funcoes").innerHTML = est.d.funcoes_conhecidas.map((f) => `<option value="${esc(f)}">`).join("");
  $("#horas-linhas").innerHTML = (linhas.length ? linhas : [{ funcao: "", horas_un: "" }]).map(linhaHoras).join("");
  $("#btn-limpar-horas").hidden = !podeLimpar;
  mensagem($("#msg-horas"), "");
  $("#dialogo-horas").showModal();
}
function linhaHoras(l) {
  return `<tr><td><input list="lista-funcoes" name="funcao" value="${esc(l.funcao)}" placeholder="ex.: Pedreiro"></td>
    <td class="num"><input type="number" name="horas" step="any" min="0" value="${l.horas_un === "" ? "" : +Number(l.horas_un).toFixed(6)}"></td>
    <td><button type="button" class="secundario pequeno" data-remover-linha>×</button></td></tr>`;
}
$("#btn-add-funcao").addEventListener("click", () => $("#horas-linhas").insertAdjacentHTML("beforeend", linhaHoras({ funcao: "", horas_un: "" })));
$("#horas-linhas").addEventListener("click", (e) => { if (e.target.closest("[data-remover-linha]")) e.target.closest("tr").remove(); });

function abrirHorasServico(id) {
  const s = est.d.servicos.find((x) => x.id === id);
  destinoHoras = { tipo: "servico", id };
  const porFuncao = {};
  s.horas.forEach((h) => { porFuncao[h.funcao] = (porFuncao[h.funcao] || 0) + h.horas_un; });
  abrirDialogoHoras(`Horas por ${s.unidade} — item ${s.item}`,
    `${esc(s.descricao)}<br><span class="discreto">Substitui composição/banco/estimativa deste serviço e vai para o banco de coeficientes (${esc(s.base || "")} ${esc(s.codigo || "")}).</span>`,
    Object.entries(porFuncao).map(([funcao, horas_un]) => ({ funcao, horas_un })), s.origem === "manual");
}
function abrirHorasSub(p) {
  destinoHoras = { tipo: "sub", ...p };
  abrirDialogoHoras(`Horas por ${p.unidade || "unidade"} — subcomposição ${p.codigo}`,
    `${esc(p.descricao)}<br><span class="discreto">Vai para o banco de coeficientes e vale para todo serviço que usa ${esc(p.codigo)}, nesta e nas próximas obras.</span>`, [], false);
}

async function salvarHoras(limpar) {
  const horasF = {};
  if (!limpar) {
    $$("#horas-linhas tr").forEach((tr) => {
      const f = $("[name=funcao]", tr).value.trim(), h = $("[name=horas]", tr).value;
      if (f && h !== "") horasF[f] = (horasF[f] || 0) + Number(h);
    });
    if (!Object.keys(horasF).length) return mensagem($("#msg-horas"), "Informe ao menos uma função com horas.", "erro");
  }
  mensagem($("#msg-horas"), "Recalculando…");
  const url = destinoHoras.tipo === "servico" ? `/api/obras/${obraId}/servico/${destinoHoras.id}/horas` : `/api/obras/${obraId}/subcomposicao`;
  const corpo = destinoHoras.tipo === "servico" ? { horas: horasF } : { codigo: destinoHoras.codigo, descricao: destinoHoras.descricao, horas: horasF };
  const ok = await chamar(url, { json: corpo }, $("#msg-horas"), "");
  if (ok) {
    $("#dialogo-horas").close();
    mensagem($("#msg-geral"), limpar ? "Serviço voltou ao cálculo automático." : "Horas gravadas no banco de coeficientes e obra recalculada.", "ok");
  }
}
$("#btn-salvar-horas").addEventListener("click", () => salvarHoras(false));
$("#btn-limpar-horas").addEventListener("click", () => salvarHoras(true));

/* ------------------------------------------------------------ 4. resumo */

const ROTULO_PERIODO = { INICIO_OBRA: "início da obra", FIM_OBRA: "fim da obra" };
function desenharResumo() {
  const d = est.d;
  $("#cartao-pendencias").innerHTML = d.pendencias.length
    ? `<h2>Pendências obrigatórias <span class="contador erro">${d.pendencias.length}</span></h2>
       <p class="discreto">Precisam ser resolvidas antes do cronograma.</p>
       <ul class="lista-pendencias">${d.pendencias.map((p) => `<li><a data-ir="${p.tipo === "execucao" ? "execucao" : "atividades"}" data-codigo="${p.atividade}">${esc(p.mensagem)}</a></li>`).join("")}</ul>`
    : `<h2>Pendências</h2><p class="mensagem ok">✔ Nenhuma pendência. A obra está pronta para o cronograma.</p>`;
  $("#tabela-equipe-fixa").innerHTML = d.equipe_fixa.map((e) => `<tr><td>${esc(e.funcao)}</td><td class="num">${fmtH4.format(e.pessoas)}</td></tr>`).join("")
    || `<tr><td colspan="2" class="discreto">Nenhuma equipe indireta encontrada.</td></tr>`;
  const periodo = d.equipe_indireta.filter((e) => !e.toda_obra);
  $("#tabela-equipe-periodo").innerHTML = periodo.map((e) => `<tr><td>${esc(e.funcao)}</td><td class="num">${fmtH4.format(e.pessoas)}</td>
    <td>${esc(e.atividade)}: ${esc(ROTULO_PERIODO[e.periodo_de] || "início de " + e.periodo_de)} → ${esc(ROTULO_PERIODO[e.periodo_ate] || "fim de " + e.periodo_ate)}</td></tr>`).join("")
    || `<tr><td colspan="3" class="discreto">—</td></tr>`;
  $("#info-media").textContent = d.semanas_prazo
    ? `Média de pessoas = horas ÷ (${fmtH.format(d.semanas_prazo)} semanas do prazo × ${d.parametros.horas_semana} h/semana). É só uma referência: o número semana a semana sai no cronograma.`
    : "Prazo da licitação não informado: sem média de pessoas.";
  $("#tabela-funcoes").innerHTML = d.resumo_funcoes.map((f) => `<tr><td>${esc(f.funcao)}</td><td class="num">${horas(f.horas_ajustadas)}</td>
    <td class="num"><b>${f.media_pessoas != null ? f.media_pessoas.toLocaleString("pt-BR") : "—"}</b></td></tr>`).join("");
  const cob = d.cobertura;
  const ordem = Object.keys(ORIGENS).filter((o) => cob[o]);
  $("#barra-cobertura").innerHTML = ordem.map((o) => [o, cob[o]]).map(([o, c]) => `<span style="width:${c.percentual}%;background:${ORIGENS[o].cor}" title="${ORIGENS[o].rotulo}: ${c.percentual}%"></span>`).join("");
  $("#tabela-cobertura").innerHTML = ordem.map((o) => [o, cob[o]]).map(([o, c]) => `<tr><td><i class="quadrado" style="background:${ORIGENS[o].cor}"></i>${ORIGENS[o].rotulo}</td>
    <td class="num">${reais(c.custo)}</td><td class="num">${c.percentual.toLocaleString("pt-BR")}%</td></tr>`).join("");
}
$("#cartao-pendencias").addEventListener("click", (e) => {
  const a = e.target.closest("[data-ir]");
  if (!a) return;
  mostrarAba(a.dataset.ir);
  if (a.dataset.ir === "atividades") {
    est.abertas.add(a.dataset.codigo);
    desenharAtividades();
    $(`tr[data-codigo="${a.dataset.codigo}"]`)?.scrollIntoView({ block: "center" });
  }
});

/* ------------------------------------------------------------ início */

$("#btn-reanalisar").addEventListener("click", () =>
  chamar(`/api/obras/${obraId}/mao-de-obra/analisar`, { method: "POST" }, $("#msg-geral"), "Composições relidas."));
$("#form-arquivo").addEventListener("submit", (e) => {
  e.preventDefault();
  const arq = $("#arquivo").files[0];
  if (!arq) return mensagem($("#msg-geral"), "Escolha o arquivo.", "erro");
  const fd = new FormData();
  fd.append("arquivo", arq);
  mensagem($("#msg-geral"), "Lendo composições…");
  chamar(`/api/obras/${obraId}/arquivo`, { method: "POST", body: fd }, $("#msg-geral"), "Arquivo guardado e mão de obra calculada.");
});

if (!obraId) mensagem($("#msg-geral"), "Obra não informada.", "erro");
else { mensagem($("#msg-geral"), "Calculando a mão de obra…"); chamar(`/api/obras/${obraId}/mao-de-obra`, {}, $("#msg-geral"), " "); }
