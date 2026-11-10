"use strict";
/* Botão "Fechar o app" no topo de todas as páginas: encerra o servidor e avisa que pode fechar a aba. */
(() => {
  const topo = document.querySelector("header.topo");
  if (!topo) return;
  const botao = document.createElement("button");
  botao.type = "button";
  botao.className = "botao-fechar-app";
  botao.textContent = "Fechar o app";
  botao.title = "Encerra o Cronograma de Obras (o servidor que roda no seu computador)";
  topo.appendChild(botao);

  function fechado() {
    document.title = "App fechado";
    document.body.innerHTML = `<header class="topo"><h1>Cronograma de obras</h1></header>
      <main><section class="cartao fechado">
        <h2>O app foi fechado.</h2>
        <p>Pode fechar esta aba. Para abrir de novo, use o atalho <b>Cronograma de Obras</b> na área de trabalho ou no menu Iniciar.</p>
      </section></main>`;
  }

  /* ---------------- atualização: confere no GitHub e oferece "Atualizar agora" ---------------- */
  const CHAVE_ADIADA = "cronograma_atualizacao_adiada";
  const CHAVE_ANTES = "cronograma_versao_antes";
  const guardar = (k, v) => { try { v === null ? sessionStorage.removeItem(k) : sessionStorage.setItem(k, v); } catch (e) { /* sem storage */ } };
  const lerGuardado = (k) => { try { return sessionStorage.getItem(k); } catch (e) { return null; } };
  const escapar = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function faixa(html, tipo) {
    let el = document.querySelector(".faixa-atualizacao");
    if (!el) {
      el = document.createElement("div");
      topo.insertAdjacentElement("afterend", el);
    }
    el.className = "faixa-atualizacao " + (tipo || "");
    el.innerHTML = html;
    return el;
  }

  async function sobre() {
    const r = await fetch("/api/sobre", { cache: "no-store" });
    return r.json();
  }

  // voltou de uma atualização pedida por esta aba?
  const antes = lerGuardado(CHAVE_ANTES);
  if (antes) {
    guardar(CHAVE_ANTES, null);
    sobre().then((d) => {
      if (d.versao && d.versao !== antes) {
        const el = faixa(`<span>✓ App atualizado (versão ${escapar(d.versao)}).</span><button type="button" class="fechar-faixa">OK</button>`, "ok");
        el.querySelector(".fechar-faixa").onclick = () => el.remove();
      } else {
        const el = faixa(`<span>A atualização não foi concluída. Veja a janela de aviso ou o arquivo logs\\atualizacao.log.</span><button type="button" class="fechar-faixa">OK</button>`, "erro");
        el.querySelector(".fechar-faixa").onclick = () => el.remove();
      }
    }).catch(() => {});
  }

  async function esperarVoltar(versaoAntes) {
    const inicio = Date.now();
    let caiu = false;
    while (Date.now() - inicio < 10 * 60 * 1000) {
      await new Promise((ok) => setTimeout(ok, 2000));
      try {
        const d = await sobre();
        if (caiu || (d.versao && d.versao !== versaoAntes)) { location.reload(); return; }
        if (Date.now() - inicio > 60 * 1000) {
          // o app nunca fechou: a atualização parou antes (ex.: Git não instalado) e mostrou uma janela de aviso
          guardar(CHAVE_ANTES, null);
          faixa("<span>A atualização não foi concluída. Veja a janela de aviso ou o arquivo logs\\atualizacao.log.</span>", "erro");
          return;
        }
      } catch (e) {
        caiu = true; // o app fechou para atualizar; espera ele voltar
      }
    }
    faixa("<span>A atualização está demorando. Quando terminar, abra o app pelo atalho Cronograma de Obras.</span>", "erro");
  }

  async function atualizarAgora(info) {
    if (!confirm("Atualizar agora?\n\nO app fecha, baixa a versão nova e abre de novo sozinho (leva de alguns segundos a alguns minutos). "
      + "Cálculos de cronograma em andamento serão interrompidos. O que já foi salvo continua salvo.")) return;
    const r = await fetch("/api/atualizar", { method: "POST", headers: { "X-Atualizar": "1" } }).catch(() => null);
    if (!r || !r.ok) {
      const d = r ? await r.json().catch(() => ({})) : {};
      alert(d.erro || "Não foi possível iniciar a atualização.");
      return;
    }
    guardar(CHAVE_ANTES, info.versao || "");
    faixa('<span class="girando"></span><span>Atualizando… não feche esta aba: a página recarrega sozinha quando o app abrir de novo.</span>', "andamento");
    esperarVoltar(info.versao);
  }

  if (!antes && lerGuardado(CHAVE_ADIADA) === null) {
    fetch("/api/atualizacao", { cache: "no-store" }).then((r) => r.json()).then((info) => {
      if (!info.disponivel) return;
      const lista = (info.novidades || []).slice(0, 5).map((n) => `<li>${escapar(n)}</li>`).join("");
      const mais = info.quantidade > 5 ? `<li>… e mais ${info.quantidade - 5}</li>` : "";
      const el = faixa(`<div><b>Tem uma atualização do app</b> (${info.quantidade} ${info.quantidade === 1 ? "mudança" : "mudanças"}).
          <ul>${lista}${mais}</ul></div>
        <div class="acoes-faixa"><button type="button" class="atualizar-agora">Atualizar agora</button>
          <button type="button" class="agora-nao">Agora não</button></div>`, "nova");
      el.querySelector(".atualizar-agora").onclick = () => atualizarAgora(info);
      el.querySelector(".agora-nao").onclick = () => { guardar(CHAVE_ADIADA, "1"); el.remove(); };
    }).catch(() => {});
  }

  botao.addEventListener("click", async () => {
    if (!confirm("Fechar o app?\n\nCálculos de cronograma em andamento serão interrompidos. O que já foi salvo continua salvo.")) return;
    botao.disabled = true;
    try {
      const r = await fetch("/api/fechar", { method: "POST", headers: { "X-Fechar": "1" } });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        alert(d.erro || "Não foi possível fechar o app.");
        botao.disabled = false;
        return;
      }
    } catch (e) {
      /* o servidor pode cair antes de responder: já está fechado */
    }
    fechado();
  });
})();
