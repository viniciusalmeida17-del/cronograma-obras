"use strict";

const obraId = obraDaUrl();
let dados = null;
let editando = null;

const ROTULO_PERIODO = { INICIO_OBRA: "início da obra", FIM_OBRA: "fim da obra" };
const ROTULO_ORIGEM = { biblioteca: "da biblioteca", herdada: "herdada de atividade que saiu", fim: "sem sucessor: termina antes da limpeza final", usuario: "editada nesta obra" };

async function carregar() {
  try {
    dados = await api(`/api/obras/${obraId}/rede`);
    $("#tela").hidden = false;
    desenhar();
  } catch (err) {
    if (!mostrarErroBiblioteca($("#erro-biblioteca"), err)) mensagem($("#msg-geral"), err.message, "erro");
  }
}

function desenhar() {
  const r = dados.resumo;
  $("#nome-obra").textContent = `Obra nº ${obraId} · ${dados.obra.nome || dados.obra.arquivo}`;
  $("#link-ligacao").href = `/ligacao?obra=${obraId}`;
  $("#link-mao-de-obra").href = `/mao-de-obra?obra=${obraId}`;
  const caixas = [
    ["Atividades na obra", r.atividades],
    ["Na sequência", r.na_sequencia],
    ["Indiretas", r.indiretas],
    ["Itens da planilha", r.itens],
    ["Total (sem BDI)", reais(r.total)],
    ["Total (com BDI)", reais(r.total_bdi)],
  ];
  $("#numeros").innerHTML = caixas.map(([t, v]) => `<div class="numero"><span>${t}</span><b>${v}</b></div>`).join("");

  $("#tabela-sequencia tbody").innerHTML = dados.sequencia.map((a) => linhaAtividade(a) + (editando === a.codigo ? linhaEdicao(a) : "")).join("");
  $("#tabela-indiretas").innerHTML = dados.indiretas.map((a) => `<tr>
      <td class="nowrap"><b>${a.codigo}</b></td><td>${esc(a.nome)}</td>
      <td>${esc(ROTULO_PERIODO[a.periodo_de] || ("início de " + a.periodo_de))} → ${esc(ROTULO_PERIODO[a.periodo_ate] || ("fim de " + a.periodo_ate))}</td>
      <td class="num">${a.n_itens}</td><td class="num">${reais(a.total_bdi)}</td></tr>`).join("")
    || `<tr><td colspan="5" class="discreto">Nenhuma atividade indireta.</td></tr>`;
}

function linhaAtividade(a) {
  const deps = a.dependencias
    .map((d) => `<span class="dep ${d.origem}" title="${ROTULO_ORIGEM[d.origem] || ""}">${d.depende_de}${d.espera_dias ? `<b>+${d.espera_dias}d</b>` : ""}</span>`)
    .join(" ");
  return `<tr class="tipo-${a.tipo} ${editando === a.codigo ? "em-edicao" : ""}">
    <td class="num">${a.posicao}</td>
    <td class="nowrap"><b>${a.codigo}</b></td>
    <td class="desc">${esc(a.nome)}<span class="linha-excel">${esc(a.etapa || "")}${a.editada ? " · <b>editada nesta obra</b>" : ""}</span></td>
    <td><span class="selo-tipo ${a.tipo}">${ROTULO_TIPO[a.tipo]}</span></td>
    <td class="deps">${deps || '<span class="discreto">início</span>'}</td>
    <td class="num">${a.n_itens}</td>
    <td class="num">${a.n_itens ? reais(a.total_bdi) : '<span class="discreto">sem custo</span>'}</td>
    <td><button type="button" class="secundario pequeno" data-editar="${a.codigo}">Editar</button></td>
  </tr>`;
}

function linhaEdicao(a) {
  const depsTexto = a.dependencias.filter((d) => d.origem !== "fim").map((d) => d.depende_de + (d.espera_dias ? `+${d.espera_dias}d` : "")).join(", ");
  const temFim = a.dependencias.some((d) => d.origem === "fim");
  return `<tr class="edicao"><td colspan="8">
    <form id="form-edicao" class="form-edicao">
      <label>Tipo
        <select name="tipo">${["rigida", "flexivel", "aguardar"].map((t) => `<option value="${t}" ${t === a.tipo ? "selected" : ""}>${ROTULO_TIPO[t]}</option>`).join("")}</select>
      </label>
      <label class="largo">Depende de <small>(códigos separados por vírgula; espera em dias: FUN-04+3d)</small>
        <input name="depende_de" value="${esc(depsTexto)}" list="lista-codigos" autocomplete="off">
      </label>
      <label class="inline"><input type="checkbox" name="salvar_biblioteca"> salvar também na biblioteca padrão</label>
      <span class="botoes">
        <button type="button" class="secundario" data-cancelar>Cancelar</button>
        <button type="submit" class="primario">Salvar</button>
      </span>
      ${temFim ? `<p class="discreto">As ligações das atividades sem sucessor ("fim") são refeitas automaticamente e não precisam ser digitadas.</p>` : ""}
      <p id="msg-edicao" class="mensagem"></p>
    </form>
    <datalist id="lista-codigos">${dados.sequencia.filter((x) => x.codigo !== a.codigo).map((x) => `<option value="${x.codigo}">${esc(x.nome)}</option>`).join("")}</datalist>
  </td></tr>`;
}

document.addEventListener("click", (e) => {
  const ed = e.target.closest("[data-editar]");
  if (ed) {
    editando = editando === ed.dataset.editar ? null : ed.dataset.editar;
    desenhar();
    $("#form-edicao [name=depende_de]")?.focus();
  }
  if (e.target.closest("[data-cancelar]")) {
    editando = null;
    desenhar();
  }
});

document.addEventListener("submit", async (e) => {
  if (e.target.id !== "form-edicao") return;
  e.preventDefault();
  const f = e.target;
  const salvarBib = f.salvar_biblioteca.checked;
  if (salvarBib && !confirm(`Gravar a mudança de ${editando} também no Excel da biblioteca padrão? (Uma cópia de segurança será feita antes.)`)) return;
  try {
    const r = await api(`/api/obras/${obraId}/rede/${editando}`, {
      json: { tipo: f.tipo.value, depende_de: f.depende_de.value, salvar_biblioteca: salvarBib },
    });
    const cod = editando;
    dados = r;
    editando = null;
    desenhar();
    mensagem($("#msg-geral"), `${cod} atualizada nesta obra.` + (r.backup_biblioteca ? ` Biblioteca padrão gravada (cópia de segurança: ${r.backup_biblioteca}).` : ""), "ok");
  } catch (err) {
    mensagem($("#msg-edicao"), err.message, "erro");
  }
});

if (!obraId) mensagem($("#msg-geral"), "Obra não informada.", "erro");
else carregar();
