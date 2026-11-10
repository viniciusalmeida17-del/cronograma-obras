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
