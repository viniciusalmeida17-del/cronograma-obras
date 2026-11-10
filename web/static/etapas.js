"use strict";
/* Barra de etapas da obra (Leitura › Ligação › Sequência › Mão de obra › Cronograma) abaixo do topo das telas da obra.
   Etapas que ainda não podem ser abertas ficam desativadas, com o motivo ao passar o mouse. */
(() => {
  const obra = new URLSearchParams(location.search).get("obra");
  const topo = document.querySelector("header.topo");
  if (!obra || !topo) return;
  const PAGINAS = { "/": "leitura", "/ligacao": "ligacao", "/sequencia": "sequencia", "/mao-de-obra": "mao_de_obra", "/cronograma": "cronograma" };
  const aqui = PAGINAS[location.pathname];
  const escapar = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const barra = document.createElement("nav");
  barra.className = "barra-etapas";
  barra.setAttribute("aria-label", "Etapas da obra");
  topo.insertAdjacentElement("afterend", barra);

  async function desenhar() {
    let d;
    try {
      const r = await fetch(`/api/obras/${encodeURIComponent(obra)}/etapas`, { cache: "no-store" });
      d = await r.json();
      if (!r.ok) throw new Error(d.erro || "Obra não encontrada");
    } catch (e) {
      barra.innerHTML = `<a href="/" class="obra-nome">← Obras salvas</a><span class="discreto">${escapar(e.message)}</span>`;
      return;
    }
    const nome = (d.obra.nome || d.obra.arquivo || "Obra sem nome").replace(/\s+/g, " ");
    const itens = d.etapas.map((e) => {
      const classe = "etapa-link" + (e.chave === aqui ? " aqui" : "");
      if (!e.ativa) {
        return `<li><span class="${classe} desativada" title="${escapar(e.motivo)}" aria-disabled="true">${escapar(e.rotulo)}</span></li>`;
      }
      const atual = e.chave === aqui ? ' aria-current="page"' : "";
      return `<li><a class="${classe}" href="${e.url}?obra=${encodeURIComponent(obra)}"${atual}>${escapar(e.rotulo)}</a></li>`;
    }).join('<li class="separador" aria-hidden="true">›</li>');
    barra.innerHTML = `<a href="/" class="obra-nome" title="${escapar(nome)} — voltar para a lista de obras">
        <span class="discreto">Obra nº ${d.obra.numero}</span> ${escapar(nome.length > 70 ? nome.slice(0, 68) + "…" : nome)}</a>
      <ol>${itens}</ol>
      <span class="etapa-atual-info discreto">Etapa atual: <b>${escapar(d.atual_rotulo)}</b></span>`;
  }
  desenhar();
  setTimeout(desenhar, 2500);   // a tela pode gravar ao abrir (ex.: a Ligação liga os serviços na primeira vez)
  // a obra pode avançar nesta tela (ex.: montar a sequência): atualiza a barra quando a aba volta a ficar visível
  // e quando a página pede (window.dispatchEvent(new Event("obra-mudou")))
  document.addEventListener("visibilitychange", () => { if (!document.hidden) desenhar(); });
  window.addEventListener("obra-mudou", desenhar);
})();
