const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
const GLYPH = { k: "♚", q: "♛", r: "♜", b: "♝", n: "♞", p: "♟" };
const PTS = { p: 1, n: 3, b: 3, r: 5, q: 9, k: 0 };
let G = null, view = null, sel = null, timer = null, MODELS = [], revSeq = 0, revOpts = { model: "", effort: "medium", depth: "full" };
let reviewMode = false, showBefore = false, rvTab = "walk", lastGid = null, lastLen = 0, lastStatus = null, lastBusy = false;

async function api(url, method = "GET", body) {
  const r = await fetch(url, { method, headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
  const text = await r.text();
  let j;
  try { j = JSON.parse(text); } catch {
    throw new Error(r.status === 404 || r.status === 405
      ? "o servidor não conhece esta ação (provavelmente está rodando uma versão antiga). Feche o terminal do servidor com Ctrl+C e rode `python app.py` de novo."
      : `resposta inesperada do servidor (HTTP ${r.status}).`);
  }
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}

/* ---------- lobby ---------- */
async function showLobby() {
  clearTimeout(timer); G = null; location.hash = "";
  $("#lobby").hidden = false; $("#game").hidden = true; $("#usage-pill").hidden = true;
  loadModels(); loadProviders(); loadEngine(); loadHealth();
  const { games: list, total_size } = await api("/api/games");
  $("#disk").textContent = `${list.length} partida(s) no disco · ${(total_size / 1024).toFixed(0)} KB`;
  $("#games-list").innerHTML = list.length ? "" : '<p class="hint">Nenhuma partida ainda.</p>';
  for (const g of list) {
    const d = document.createElement("div"); d.className = "row";
    const when = new Date(g.created * 1000).toLocaleString("pt-BR");
    const st = g.status === "over" ? `fim ${g.result}` : "em andamento";
    d.innerHTML = `<span>${when} · você de ${g.human_color === "white" ? "brancas" : "pretas"} · ${g.plies} lances · ${st}</span><span class="hint">${g.model} · US$${g.cost.toFixed(2)} · ${(g.size / 1024).toFixed(0)} KB${g.exported ? " · 💾 salva" : ""} <a href="/api/games/${g.id}/export" download>baixar</a> <a href="#" data-del="${g.id}">apagar</a></span>`;
    d.onclick = e => { if (e.target.download !== undefined && e.target.tagName === "A" && e.target.hasAttribute("download")) { e.stopPropagation(); setTimeout(showLobby, 800); return; } if (e.target.dataset.del) { e.preventDefault(); e.stopPropagation(); if (confirm("Apagar esta partida?")) api("/api/games/" + g.id, "DELETE").then(showLobby); } else openGame(g.id); };
    $("#games-list").appendChild(d);
  }
}

$("#new-form").onsubmit = async e => {
  e.preventDefault();
  const f = Object.fromEntries(new FormData(e.target));
  f.budget_usd = parseFloat(f.budget_usd || 0);
  f.facts = !!f.facts; f.autosave = !!f.autosave;
  const g = await api("/api/games", "POST", f);
  openGame(g.id);
};
$("#home-link").onclick = showLobby;

async function loadModels() {
  const sel = $("#model-select"), keep = sel.value;
  sel.innerHTML = (await api("/api/models")).map(m => `<option value="${esc(m.value)}">${esc(m.label)}</option>`).join("");
  if (keep) sel.value = keep;
}
async function loadProviders() {
  const list = await api("/api/providers");
  $("#prov-list").innerHTML = list.length ? "" : '<p class="hint">Nenhum provedor.</p>';
  for (const p of list) {
    const d = document.createElement("div"); d.className = "row";
    d.innerHTML = `<span><b>${esc(p.name)}</b> · ${esc(p.base_url || "sem URL")} · chave ${esc(p.key)} · ${p.models.length ? esc(p.models.join(", ")) : "sem modelos"} ${p.ready ? "✅" : "⚠️ incompleto"}</span><span><a href="#" data-fetch>buscar modelos</a> <a href="#" data-edit>editar</a> <a href="#" data-rm>remover</a></span>`;
    d.querySelector("[data-edit]").onclick = e => { e.preventDefault(); const f = $("#prov-form"); f.id.value = p.id; f.name.value = p.name; f.base_url.value = p.base_url; f.models.value = p.models.join(", "); f.api_key.value = ""; f.base_url.focus(); };
    d.querySelector("[data-fetch]").onclick = async e => {
      e.preventDefault(); e.target.textContent = "buscando…";
      try { const r = await api(`/api/providers/${p.id}/fetch_models`, "POST"); alert("Modelos encontrados: " + r.models.join(", ")); } catch (err) { alert("Não foi possível buscar: " + err.message); }
      loadProviders(); loadModels();
    };
    d.querySelector("[data-rm]").onclick = async e => { e.preventDefault(); if (confirm("Remover este provedor e a chave?")) { await api("/api/providers/" + p.id, "DELETE"); loadProviders(); loadModels(); } };
    $("#prov-list").appendChild(d);
  }
}
$("#prov-preset").onchange = e => { if (!e.target.value) return; const [n, u] = e.target.value.split("|"), f = $("#prov-form"); f.name.value = n; f.base_url.value = u; };
$("#prov-form").onsubmit = async e => {
  e.preventDefault();
  await api("/api/providers", "POST", Object.fromEntries(new FormData(e.target)));
  e.target.reset(); loadProviders(); loadModels();
};
$("#import-file").onchange = async e => {
  const f = e.target.files[0]; if (!f) return;
  try {
    const r = await fetch("/api/games/import", { method: "POST", body: await f.arrayBuffer() });
    const j = await r.json(); if (!r.ok) throw new Error(j.error);
    openGame(j.id);
  } catch (err) { alert("Não foi possível importar: " + err.message); }
  e.target.value = "";
};
$("#btn-cleanup").onclick = async () => {
  if (!confirm("Apagar do disco as partidas encerradas que já foram salvas em arquivo? (você pode importá-las de volta depois)")) return;
  const r = await api("/api/games/cleanup", "POST"); alert(`${r.removed} partida(s) removida(s), ${(r.freed / 1024).toFixed(0)} KB liberados.`); showLobby();
};

/* ---------- jogo ---------- */
/* ---------- configuração inicial (assistente) ---------- */
let healthTimer = null;
async function loadHealth(refresh = false) {
  clearTimeout(healthTimer);
  let h;
  try { h = await api("/api/health" + (refresh ? "?refresh=1" : "")); } catch { return; }
  $("#ver").textContent = "v" + h.version;
  const box = $("#health"), c = h.claude || {};
  const claudeOk = c.installed && c.logged_in !== false, ready = claudeOk || h.api_providers > 0;
  box.hidden = false; box.className = "card" + (ready && !h.setup.installing ? " ready" : "");
  const demo = h.demo ? `<button class="demo" id="btn-demo">▶ Ver partida de demonstração (sem gastar tokens)</button>` : "";
  const sf = h.stockfish.found ? `<span class="ok">✅ Motor forte para a revisão: ${esc(h.stockfish.name)}</span>` : `<span class="warn">⚠️ Motor forte não encontrado (a revisão usará uma régua mais fraca)</span>`;
  if (ready && !h.setup.installing) {
    box.innerHTML = `<div class="step"><span class="ok">✅ ${claudeOk ? "Claude Code pronto" : "Provedor de API configurado"}</span>${sf}${demo}</div>`;
  } else {
    let a;
    if (h.setup.installing) a = `<span class="warn">⏳ Instalando o Claude Code… pode levar de 1 a 3 minutos.</span>`;
    else if (!c.installed) a = h.can_auto_install
      ? `<span class="warn">Claude Code não instalado.</span><button class="primary" id="btn-inst">⬇ Instalar automaticamente</button>${h.setup.ok === false ? `<span class="hint">A instalação falhou: ${esc(h.setup.log.slice(-160))}</span>` : ""}`
      : `<span class="warn">Claude Code não instalado.</span><span class="hint">Instale em <a href="https://claude.com/claude-code" target="_blank" rel="noopener">claude.com/claude-code</a> e volte aqui.</span>`;
    else a = `<span class="warn">🔑 Claude Code instalado, falta entrar na sua conta.</span><button class="primary" id="btn-login">Entrar na minha conta</button><button id="btn-recheck">Já entrei, verificar</button>`;
    box.innerHTML = `<h2>Configuração inicial</h2><p class="hint">O Claude precisa de um "cérebro" para jogar. Escolha um caminho:</p>
      <div class="step"><b>A) Sua conta do Claude (Claude Code)</b>${a}</div>
      <div class="step"><b>B) Uma chave de API</b><span class="hint">DeepSeek, OpenAI, OpenRouter… </span><button id="btn-api">Configurar chave de API</button></div>
      <div class="step">${sf}${demo}</div>`;
  }
  $("#btn-inst")?.addEventListener("click", async () => { try { await api("/api/setup/install-claude", "POST"); } catch (e) { alert(e.message); } loadHealth(true); });
  $("#btn-login")?.addEventListener("click", async () => { try { await api("/api/setup/login-claude", "POST"); alert("Uma janela vai abrir e depois o navegador, para você entrar na sua conta. Depois clique em \"Já entrei, verificar\"."); } catch (e) { alert(e.message); } loadHealth(true); });
  $("#btn-recheck")?.addEventListener("click", () => loadHealth(true));
  $("#btn-api")?.addEventListener("click", () => { const d = $("#prov-card"); d.open = true; d.scrollIntoView({ behavior: "smooth", block: "center" }); });
  $("#btn-demo")?.addEventListener("click", async () => { try { const r = await api("/api/demo", "POST"); openGame(r.id); } catch (e) { alert(e.message); } });
  if (!$("#lobby").hidden && (h.setup.installing || (!ready && c.installed && c.logged_in === false))) healthTimer = setTimeout(() => loadHealth(true), 4000);
}

function openGame(id) {
  location.hash = "g/" + id; view = null; sel = null; reviewMode = false; showBefore = false;
  $("#lobby").hidden = true; $("#game").hidden = false;
  refresh(id);
}

async function refresh(id = G?.id) {
  clearTimeout(timer);
  G = await api(`/api/games/${id}` + ($("#peek").checked ? "?peek=1" : ""));
  render();
  const humanTurn = G.turn === G.human_color;
  if (G.audit_progress || G.review_busy) timer = setTimeout(() => refresh(id), 3000);
  else if (G.status === "ongoing" && (G.busy || !humanTurn) && !G.error) timer = setTimeout(() => refresh(id), 2000);
}

const curPly = () => view ?? G.moves.length;
const fenAt = p => (p === 0 ? START : G.moves[p - 1].fen_after);

function parseFen(fen) {
  return fen.split(" ")[0].split("/").map(row => {
    const out = [];
    for (const ch of row) /\d/.test(ch) ? out.push(...Array(+ch).fill(null)) : out.push(ch);
    return out;
  });
}
function matOf(fen) {
  let s = 0;
  for (const row of parseFen(fen)) for (const c of row) if (c) s += (c === c.toUpperCase() ? 1 : -1) * PTS[c.toLowerCase()];
  return s;
}

function render() {
  if (G.status !== "over") reviewMode = false;
  document.body.classList.toggle("reviewing", reviewMode);
  const mine = G.human_color === "white";
  const ply = shownPly(), grid = parseFen(fenAt(ply));
  const last = ply > 0 ? G.moves[ply - 1].uci : "";
  const live = !reviewMode && ply === G.moves.length;
  const dests = sel && live ? G.legal.filter(u => u.startsWith(sel)).map(u => u.slice(2, 4)) : [];
  const b = $("#board"); b.innerHTML = "";
  for (let i = 0; i < 8; i++) for (let j = 0; j < 8; j++) {
    const rank = mine ? 7 - i : i, file = mine ? j : 7 - j;
    const name = "abcdefgh"[file] + (rank + 1), pc = grid[7 - rank][file];
    const d = document.createElement("div");
    d.className = "sq " + ((rank + file) % 2 ? "l" : "d");
    if (last && (last.startsWith(name) || last.slice(2, 4) === name)) d.classList.add("last");
    if (name === sel) d.classList.add("sel");
    if (dests.includes(name)) d.classList.add("dest");
    if (G.check && live && pc && pc.toLowerCase() === "k" && (pc === pc.toUpperCase()) === (G.turn === "white")) d.classList.add("chk");
    if (pc) d.innerHTML = `<span class="p ${pc === pc.toUpperCase() ? "w" : "b"}">${GLYPH[pc.toLowerCase()]}︎</span>`;
    if (j === 0) d.insertAdjacentHTML("beforeend", `<span class="co r">${rank + 1}</span>`);
    if (i === 7) d.insertAdjacentHTML("beforeend", `<span class="co f">${"abcdefgh"[file]}</span>`);
    d.onclick = () => clickSq(name, pc);
    b.appendChild(d);
  }
  renderStatus(); renderMoves(); renderThought(); renderChart(); renderAsk(); renderStats(); renderAutosave(); renderRvPanel(); drawArrows(); renderEvalBar(); soundsOnRender();
  $("#btn-draw").disabled = $("#btn-resign").disabled = G.status !== "ongoing" || !!G.busy;
  $("#btn-undo").disabled = !G.moves.some(m => m.by === "human");
  const p = $("#usage-pill"), u = G.usage || {};
  p.hidden = false;
  p.textContent = `${((u.tokens || 0) / 1000).toFixed(0)}k tokens · US$${(u.cost || 0).toFixed(2)}` + (G.settings.budget_usd ? ` / ${G.settings.budget_usd}` : "") + ` · ${G.settings.model}`;
}

function renderStatus() {
  const s = $("#status"); let h = "";
  $("#btn-retry").hidden = !G.error;
  if (G.error) h = `<span style="color:var(--bad)">Erro do agente: ${esc(G.error)}</span>`;
  else if (G.status === "over") h = `Fim de jogo: <b>${esc(G.result)}</b> (${esc(G.reason)}).` + (G.review && !reviewMode ? ` <button id="btn-startrv" class="primary">▶ Começar a revisão</button>` : "") + (reviewMode ? ` <span class="hint">Revisão em andamento</span>` : "");
  else if (G.busy) h = `<span class="think">Claude está ${esc(G.busy)}</span>`;
  else if (G.turn === G.human_color) h = "Sua vez" + (G.check ? " — você está em xeque!" : "");
  else h = "Aguardando o agente…";
  s.innerHTML = h;
  const sb = $("#btn-startrv"); if (sb) sb.onclick = startReview;
}

function renderMoves() {
  const m = $("#moves"); m.innerHTML = ""; const cur = curPly();
  for (let i = 0; i < G.moves.length; i += 2) {
    m.insertAdjacentHTML("beforeend", `<span class="n">${i / 2 + 1}.</span>`);
    for (const k of [i, i + 1]) {
      const mv = G.moves[k], el = document.createElement("span");
      if (mv) {
        const cm = !G.hidden && momentAt(k + 1);
        el.className = "m" + (mv.by === "agent" ? " ai" : "") + (k + 1 === cur ? " cur" : "") + (cm ? " has " + sev(cm) : "");
        el.textContent = mv.san + (A(k + 1) ? { blunder: "??", mistake: "?", inaccuracy: "?!" }[A(k + 1).cls] || "" : ""); el.onclick = () => gotoPly(k + 1);
      }
      m.appendChild(el);
    }
  }
  m.scrollTop = m.scrollHeight;
}

function sec(title, html) { return html ? `<div class="sec"><b>${title}</b>${html}</div>` : ""; }
function renderThought() {
  const ply = curPly(), box = $("#thought"), title = $("#thought-title");
  if (ply === 0) { title.textContent = "Raciocínio"; box.innerHTML = G.hidden ? '<p class="locked">Oculto até o fim da partida.</p>' : (G.briefing ? sec("Briefing inicial", `<p>${esc(G.briefing)}</p>`) : '<p class="hint">Selecione um lance.</p>'); return; }
  const mv = G.moves[ply - 1];
  title.textContent = `Lance ${Math.ceil(ply / 2)}${ply % 2 ? "." : "..."} ${mv.san} — ${mv.by === "agent" ? "Claude" : "você"}`;
  if (mv.by === "human") { box.innerHTML = '<p class="hint">Lance seu. Use a caixa abaixo para perguntar ao Claude o que ele pensaria aqui.</p>' + auditHtml(ply); return; }
  const t = mv.thought || {};
  if (G.hidden) {
    box.innerHTML = `<p class="locked">🔒 Raciocínio oculto durante a partida.</p>` + (t.message_to_human ? `<p>“${esc(t.message_to_human)}”</p>` : "");
    return;
  }
  const meta = mv.meta || {}, eng = meta.engine || {}, u = meta.usage || {}, rv = meta.review;
  let h = sec("Leitura", `<p>${esc(t.position_read)}</p>`) + sec("Ameaças do adversário", `<p>${esc(t.opponent_threats)}</p>`) + sec("Plano", `<p>${esc(t.plan)}</p>`);
  h += sec("Candidatos", (t.candidates || []).map(c => `<div class="cand ${c.move === mv.san ? "chosen" : ""}"><b style="display:inline">${esc(c.move)}</b> — ${esc(c.idea)}<br><span class="hint">Risco: ${esc(c.risk)} · Linha: ${esc(c.line)}</span></div>`).join(""));
  h += sec("Decisão", `<p>${esc(t.decision)}</p>`) + sec("Checagem anti-erro", `<p>${esc(t.blunder_check)}</p>`);
  const cls = (n, bad) => `<span class="tag ${bad === true ? "bad" : bad === false ? "ok" : ""}">${n}</span>`;
  h += sec("Números", `<div class="tags">${cls("nota (brancas): " + (t.eval_pawns >= 0 ? "+" : "") + t.eval_pawns)}${cls("confiança " + t.confidence + "/5")}${cls("material: " + (matOf(mv.fen_after) >= 0 ? "+" : "") + matOf(mv.fen_after))}${eng.chosen_ev != null ? cls("motor raso (lance): " + eng.chosen_ev.toFixed(2) + " / melhor " + eng.best + " " + eng.best_ev.toFixed(2)) : ""}</div>`);
  if (rv) h += sec("Revisor Haiku", `<p>Acionado: ${esc(rv.reason)} → <b>${esc(rv.verdict)}</b>${rv.problem ? ": " + esc(rv.problem) : ""}${rv.verdict === "problem" ? (rv.revised ? " (lance trocado)" : " (lance mantido)") : ""}</p>`);
  if (eng.probes) h += sec("Sondagem recebida do motor raso", `<table class="t">${eng.probes.map(p => `<tr><td>${esc(p.san)}</td><td>${esc(p.ev)}</td><td>${esc(p.pv)}</td><td>${esc((p.flags || []).join("; "))}</td></tr>`).join("")}</table>`);
  h += sec("Memória passada adiante", `<p>${esc(t.plan_notes)}</p>`);
  const aidLbl = { full: "motor completo", material: "só material", none: "sem motor" }[meta.assist || "full"];
  h += sec("Ajudas e auditoria", `<div class="tags">${cls("ajuda: " + aidLbl)}${cls("fatos: " + (meta.facts === false ? "off" : "on"))}${eng.agrees != null ? cls(eng.agrees ? "igual ao melhor do motor" + (eng.positional ? "" : " (material)") : "diferente do melhor do motor (" + eng.best + ")", eng.agrees ? undefined : false) : ""}${eng.shown === false ? cls("o jogador não viu o motor") : ""}</div>`);
  h += sec("Custo deste lance", `<div class="tags">${cls(((u.tokens || 0) / 1000).toFixed(1) + "k tokens")}${cls("US$" + (u.cost || 0).toFixed(3))}${cls((u.calls || 1) + " chamada(s)")}${cls("esforço " + meta.effort)}${meta.attempts > 1 ? cls(meta.attempts + " tentativas (lance ilegal)", true) : ""}${meta.fallback ? cls("fallback do motor", true) : ""}${meta.economy ? cls("modo econômico", true) : ""}</div>`);
  box.innerHTML = h + auditHtml(ply);
}

function renderChart() {
  const card = $("#chart-card"); card.hidden = G.hidden || !G.moves.length; if (card.hidden) return;
  const W = 600, H = 150, n = G.moves.length, clamp = v => Math.max(-6, Math.min(6, v));
  const X = p => 10 + (p / Math.max(1, n)) * (W - 20), Y = v => H / 2 - (clamp(v) / 6) * (H / 2 - 8);
  const agentWhite = G.human_color === "black";
  const pts = (f) => G.moves.map((m, i) => { const v = f(m, i); return v == null ? null : [X(i + 1), Y(v), i + 1]; }).filter(Boolean);
  const line = (a, color, dash) => a.length ? `<polyline fill="none" stroke="${color}" stroke-width="2" ${dash ? 'stroke-dasharray="4 3"' : ""} points="${a.map(p => p[0] + "," + p[1]).join(" ")}"/>` : "";
  const llm = pts(m => m.thought?.eval_pawns ?? null);
  const mat = pts(m => matOf(m.fen_after));
  const eng = G.review?.curve ? pts((m, i) => G.review.curve[i + 1]) : G.audit ? pts((m, i) => G.audit[i]?.eval_white / 100) : pts(m => (m.meta?.engine?.chosen_ev != null ? (agentWhite ? 1 : -1) * m.meta.engine.chosen_ev : null));
  const ag = G.moves.filter(m => m.meta?.engine?.agrees != null), yes = ag.filter(m => m.meta.engine.agrees).length;
  $("#agree").textContent = ag.length ? `Concordância com o melhor lance do motor: ${yes}/${ag.length} (${Math.round(100 * yes / ag.length)}%) · ajuda: ${G.settings.assist || "full"}. Perto de 100% com ajuda completa sugere que o motor decide; com "nenhuma", é o raciocínio dela.` : "";
  const cx = X(curPly());
  $("#chart").innerHTML = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"><line x1="0" x2="${W}" y1="${H / 2}" y2="${H / 2}" stroke="#888" stroke-opacity=".4"/>
    <line x1="${cx}" x2="${cx}" y1="0" y2="${H}" stroke="#f6e05e" stroke-opacity=".7"/>${line(mat, "#9aa3af", true)}${line(eng, "#e6a23c", true)}${line(llm, "#6aa5ff")}
    ${llm.map(p => `<circle cx="${p[0]}" cy="${p[1]}" r="4" fill="#6aa5ff" data-ply="${p[2]}" style="cursor:pointer"/>`).join("")}</svg>`;
  $("#chart").querySelectorAll("circle").forEach(c => c.onclick = () => { view = +c.dataset.ply === n ? null : +c.dataset.ply; render(); });
}

function renderAsk() {
  const card = $("#ask-card"); card.hidden = G.hidden; if (card.hidden) return;
  const ply = curPly();
  $("#ask-title").textContent = ply ? `Perguntar ao Claude sobre o lance ${Math.ceil(ply / 2)}${ply % 2 ? "." : "..."} ${G.moves[ply - 1].san}` : "Perguntar ao Claude sobre a posição inicial";
  $("#comments").innerHTML = (G.comments || []).filter(c => c.ply === ply).map(c => `<div class="cm"><div class="q">Você: ${esc(c.question)}</div>${esc(c.answer)}</div>`).join("");
}

$("#btn-ask").onclick = async () => {
  const q = $("#question").value.trim(); if (!q) return;
  $("#ask-status").textContent = "Claude está pensando…"; $("#btn-ask").disabled = true;
  try { const r = await api(`/api/games/${G.id}/ask`, "POST", { ply: curPly(), question: q }); G.comments = r.comments; G.usage = r.usage; $("#question").value = ""; render(); $("#ask-status").textContent = ""; }
  catch (e) { $("#ask-status").textContent = "Erro: " + e.message; }
  $("#btn-ask").disabled = false;
};

/* ---------- ações ---------- */
function clickSq(name, pc) {
  if (!G || G.status !== "ongoing" || G.busy || curPly() !== G.moves.length) return;
  if (sel && G.legal.some(u => u.startsWith(sel + name))) {
    const opts = G.legal.filter(u => u.startsWith(sel + name));
    if (opts.length > 1) return askPromo(opts);
    return send(opts[0]);
  }
  const own = pc && ((pc === pc.toUpperCase()) === (G.human_color === "white"));
  sel = own && G.legal.some(u => u.startsWith(name)) ? name : null; render();
}
function askPromo(opts) {
  const o = $("#promo-opts"); o.innerHTML = "";
  for (const u of opts) { const b = document.createElement("button"); b.textContent = GLYPH[u[4]] + "︎"; b.onclick = () => { $("#promo").hidden = true; send(u); }; o.appendChild(b); }
  $("#promo").hidden = false;
}
async function send(uci) {
  sel = null;
  try { G = await api(`/api/games/${G.id}/move`, "POST", { uci }); view = null; render(); refresh(); } catch (e) { alert(e.message); }
}
$("#btn-resign").onclick = async () => { if (confirm("Abandonar a partida?")) { await api(`/api/games/${G.id}/resign`, "POST"); refresh(); } };
$("#btn-draw").onclick = async () => { const r = await api(`/api/games/${G.id}/draw`, "POST"); alert(r.accepted ? "Empate aceito." : "O Claude recusou o empate."); refresh(); };
$("#btn-save").onclick = () => { const a = document.createElement("a"); a.href = `/api/games/${G.id}/export`; a.download = ""; a.click(); };
$("#btn-new").onclick = async () => {
  const s = G.settings, other = G.human_color === "white" ? "black" : "white";  // revanche: cores trocadas
  await showLobby(); await loadModels();
  const f = $("#new-form");
  f.human_color.value = other; f.model.value = s.model; f.effort.value = s.effort; f.briefing.value = s.briefing;
  f.assist.value = s.assist || "full"; f.reviewer.value = s.reviewer; f.budget_usd.value = s.budget_usd;
  f.facts.checked = s.facts !== false; f.autosave.checked = !!s.autosave;
  f.scrollIntoView({ behavior: "smooth", block: "center" });
};
$("#btn-undo").onclick = async () => {
  try { G = await api(`/api/games/${G.id}/undo`, "POST"); view = null; sel = null; render(); refresh(); } catch (e) { alert(e.message); }
};
$("#btn-retry").onclick = async () => { await api(`/api/games/${G.id}/retry`, "POST"); refresh(); };
$("#peek").onchange = () => refresh();
document.querySelectorAll("[data-nav]").forEach(b => b.onclick = () => nav(b.dataset.nav));
function nav(w) {
  if (!G) return; const n = G.moves.length, c = curPly();
  const t = w === "start" ? 0 : w === "end" ? n : w === "prev" ? Math.max(0, c - 1) : Math.min(n, c + 1);
  if (t !== c) gotoPly(t, t > c);
}
document.addEventListener("keydown", e => {
  if (e.target.tagName === "TEXTAREA") return;
  if (e.key === "ArrowLeft") nav("prev"); if (e.key === "ArrowRight") nav("next");
  if (reviewMode && (e.key === "ArrowDown" || e.key === "ArrowUp")) { e.preventDefault(); nextComment(e.key === "ArrowDown" ? 1 : -1); }
});

if (location.hash.startsWith("#g/")) openGame(location.hash.slice(3)); else showLobby();

/* ---------- auditoria, estatísticas, autosave ---------- */
function A(ply) { return G.audit && !G.hidden ? G.audit[ply - 1] : null; }
const CLS = { ok: "ok", inaccuracy: "imprecisão", mistake: "erro", blunder: "blunder" };
function auditHtml(ply) {
  const a = A(ply); if (!a) return "";
  const bad = a.cls !== "ok";
  return `<div class="sec"><b>Auditoria do motor</b><div class="tags"><span class="tag ${bad ? "bad" : "ok"}">${CLS[a.cls]}</span><span class="tag">perda ${a.loss} cp</span><span class="tag">motor preferia ${esc(a.best)}</span>${a.top1 ? '<span class="tag ok">= melhor do motor</span>' : ""}</div><p class="hint">Régua rasa de 3 lances: confie menos em táticas profundas e sacrifícios.</p></div>`;
}
function renderStats() {
  const card = $("#stats-card"); card.hidden = G.status !== "over" || G.hidden || reviewMode; if (card.hidden) return;
  const box = $("#stats");
  if (G.audit_progress) { const [d, n] = G.audit_progress; box.innerHTML = `<p>Analisando… ${d}/${n} lances</p><progress value="${d}" max="${n}" style="width:100%"></progress>`; return; }
  if (!G.stats) { box.innerHTML = '<button id="btn-audit" class="primary">Analisar com o motor</button>'; $("#btn-audit").onclick = async () => { G = await api(`/api/games/${G.id}/audit`, "POST"); render(); refresh(); }; return; }
  const row = (n, x) => x.n ? `<tr><td>${n}</td><td>${x.n}</td><td>${x.acpl}</td><td>${x.accuracy}%</td><td>${x.inaccuracies}/${x.mistakes}/${x.blunders}</td><td>${x.top1}%</td></tr>` : `<tr><td>${n}</td><td colspan="5">sem lances suficientes</td></tr>`;
  const h = G.stats.human, a = G.stats.agent;
  const diff = h?.n && a?.n ? `<p>Claude vs você: precisão <b>${(a.accuracy - h.accuracy >= 0 ? "+" : "") + (a.accuracy - h.accuracy).toFixed(1)}</b> pontos, perda média <b>${(a.acpl - h.acpl >= 0 ? "+" : "") + (a.acpl - h.acpl).toFixed(1)}</b> cp.</p>` : "";
  box.innerHTML = `<table class="t"><tr><th>lado</th><th>lances</th><th>perda média (cp)</th><th>precisão</th><th>imprec/erros/blunders</th><th>= motor</th></tr>${row("Você", h || { n: 0 })}${row("Claude", a || { n: 0 })}</table>${diff}
  <p class="hint">Régua: motor de só 3 lances. Ele não vê táticas profundas nem sacrifícios, então a perda sai subestimada para os dois lados e <b>isto não é rating</b>. Use para comparar vocês dois e achar os lances mais discrepantes (marcados ?! ? ?? na lista). Ignoro os 6 primeiros lances e posições já decididas. Para rating de verdade seria preciso um motor forte só na auditoria (o Claude nunca o vê).</p>
  <button id="btn-audit">Reanalisar</button>`;
  $("#btn-audit").onclick = async () => { G = await api(`/api/games/${G.id}/audit`, "POST"); render(); refresh(); };
}
function renderAutosave() {
  $("#autosave-on").checked = !!G.settings.autosave;
  $("#autosave-lbl").textContent = G.settings.autosave ? `autosave → ${G.autosave_file}` : "autosave desligado";
}
$("#autosave-on").onchange = async e => { G = await api(`/api/games/${G.id}/autosave`, "POST", { on: e.target.checked }); render(); };

/* ---------- motor forte (configuração) ---------- */
async function loadEngine() {
  try {
    const s = await api("/api/engine");
    $("#eng-state").textContent = s.found ? `· ✅ ${s.name}` : "· ⚠️ não encontrado (usará a régua rasa)";
    if (s.path && !$("#eng-form").path.value) $("#eng-form").path.value = s.path;
  } catch { }
}
$("#eng-form").onsubmit = async e => {
  e.preventDefault();
  try { await api("/api/engine", "POST", { path: e.target.path.value }); loadEngine(); alert("Motor configurado."); } catch (err) { alert(err.message); }
};

/* ---------- sons (Web Audio sintetizado, sem arquivos) ---------- */
let AC = null, muted = (() => { try { return localStorage.getItem("mute") === "1"; } catch { return false; } })();
function ac() {
  if (!AC) { try { AC = new (window.AudioContext || window.webkitAudioContext)(); } catch { return null; } }
  if (AC.state === "suspended") AC.resume();
  return AC;
}
["pointerdown", "keydown"].forEach(ev => document.addEventListener(ev, () => { if (!muted) ac(); }, { once: true }));
function envl(g, t0, dur, vol) { g.gain.setValueAtTime(0.0001, t0); g.gain.exponentialRampToValueAtTime(vol, t0 + 0.005); g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur); }
function tone(f, t0, dur, vol = 0.2, type = "sine", f2) {
  const c = ac(); if (!c) return;
  const o = c.createOscillator(), g = c.createGain();
  o.type = type; o.frequency.setValueAtTime(f, t0); if (f2) o.frequency.exponentialRampToValueAtTime(f2, t0 + dur);
  envl(g, t0, dur, vol); o.connect(g).connect(c.destination); o.start(t0); o.stop(t0 + dur + 0.03);
}
function noise(t0, dur, vol = 0.3, cutoff = 2000) {
  const c = ac(); if (!c) return;
  const n = Math.floor(c.sampleRate * dur), buf = c.createBuffer(1, n, c.sampleRate), d = buf.getChannelData(0);
  for (let i = 0; i < n; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / n);
  const s = c.createBufferSource(), f = c.createBiquadFilter(), g = c.createGain();
  s.buffer = buf; f.type = "lowpass"; f.frequency.value = cutoff; envl(g, t0, dur, vol);
  s.connect(f).connect(g).connect(c.destination); s.start(t0);
}
const SFX = {
  move: t => { noise(t, .06, .35, 1600); tone(190, t, .09, .25, "sine", 120); },
  capture: t => { noise(t, .1, .55, 2800); tone(140, t, .14, .35, "triangle", 80); },
  castle: t => { SFX.move(t); SFX.move(t + .11); },
  check: t => { SFX.move(t); tone(880, t + .08, .12, .12, "square"); tone(660, t + .2, .16, .12, "square"); },
  promote: t => { [523, 659, 784, 1047].forEach((f, i) => tone(f, t + i * .07, .12, .15, "triangle")); },
  win: t => { [523, 659, 784, 1047].forEach((f, i) => tone(f, t + i * .12, .25, .18, "triangle")); },
  loss: t => { [392, 330, 262, 196].forEach((f, i) => tone(f, t + i * .14, .3, .18, "sawtooth")); },
  draw: t => { [392, 392].forEach((f, i) => tone(f, t + i * .16, .25, .16, "triangle")); },
  done: t => { tone(784, t, .14, .15, "sine"); tone(1175, t + .12, .25, .15, "sine"); },
  tick: t => noise(t, .03, .15, 1200),
};
function play(name) { if (muted) return; const c = ac(); if (!c) return; try { SFX[name](c.currentTime + 0.01); } catch { } }
const sfxFor = san => /[#+]/.test(san) ? "check" : san.includes("O-O") ? "castle" : san.includes("=") ? "promote" : san.includes("x") ? "capture" : "move";
function paintMute() { $("#mute").textContent = muted ? "🔇" : "🔊"; }
$("#mute").onclick = () => { muted = !muted; try { localStorage.setItem("mute", muted ? "1" : "0"); } catch { } paintMute(); if (!muted) play("move"); };
paintMute();
// som dos lances novos (seus e do Claude), do fim da partida e do fim da revisão
function soundsOnRender() {
  if (!G) return;
  if (lastGid !== G.id) { lastGid = G.id; lastLen = G.moves.length; lastStatus = G.status; lastBusy = !!G.review_busy; return; }
  if (G.moves.length > lastLen && !reviewMode) play(sfxFor(G.moves[G.moves.length - 1].san));
  lastLen = G.moves.length;
  if (lastStatus === "ongoing" && G.status === "over") {
    const win = G.result === (G.human_color === "white" ? "1-0" : "0-1"), draw = G.result === "1/2-1/2";
    setTimeout(() => play(draw ? "draw" : win ? "win" : "loss"), 400);
  }
  lastStatus = G.status;
  if (lastBusy && !G.review_busy && G.review) play("done");
  lastBusy = !!G.review_busy;
}

/* ---------- navegação e revisão (estilo chess.com) ---------- */
const lbl = p => `${Math.ceil(p / 2)}${p % 2 ? "." : "..."}`;
const momentAt = p => (G.review?.moments || []).find(m => m.ply === p) || null;
const commentPlies = () => (G.review?.moments || []).map(m => m.ply).sort((a, b) => a - b);
const sev = m => (m.loss >= 300 ? "blunder" : m.loss >= 100 ? "mistake" : m.loss >= 50 ? "inacc" : "good");
const SEVL = { blunder: "Erro grave", mistake: "Erro", inacc: "Imprecisão", good: "Lance crítico" };
const evs = v => (Math.abs(v) >= 10 ? (v > 0 ? "+10 (decisivo)" : "−10 (decisivo)") : (v >= 0 ? "+" : "") + v.toFixed(1));
// posição mostrada: a do lance atual; com "ver antes", a anterior ao lance comentado
function shownPly() { const p = curPly(); return reviewMode && showBefore && momentAt(p) ? p - 1 : p; }
function gotoPly(p, forward = true) {
  view = p === G.moves.length ? null : p; showBefore = false; sel = null;
  if (forward && p > 0) play(sfxFor(G.moves[p - 1].san)); else play("tick");
  render();
}
function nextComment(dir) {
  const cur = curPly(), list = commentPlies();
  const t = dir > 0 ? list.find(p => p > cur) : [...list].reverse().find(p => p < cur);
  if (t != null) gotoPly(t, dir > 0);
}
function startReview() { reviewMode = true; rvTab = "walk"; showBefore = false; view = 0; sel = null; play("tick"); render(); }
function exitReview() { reviewMode = false; showBefore = false; view = null; render(); }

/* ---------- setas e casas (camada SVG acima das peças) ---------- */
const ACOL = { best: "#2fb344", threat: "#e03131", plan: "#339af0", mistake: "#f08c00", played: "#868e96" };
const SCOL = { key: "#f6e05e", weak: "#e03131", target: "#339af0" };
function sqPt(sq) {
  const f = "abcdefgh".indexOf(sq[0]), r = +sq[1] - 1, mine = G.human_color === "white";
  return [mine ? f + 0.5 : 7 - f + 0.5, mine ? 7 - r + 0.5 : r + 0.5];
}
function drawArrows() {
  const svg = $("#arrows"), lg = $("#arrow-legend");
  const mo = reviewMode && !G.hidden ? momentAt(curPly()) : null;
  lg.hidden = !mo;
  if (!mo) { svg.innerHTML = ""; return; }
  let out = "";
  for (const s of mo.squares || []) {
    const [cx, cy] = sqPt(s.sq);
    out += `<rect x="${cx - 0.5}" y="${cy - 0.5}" width="1" height="1" fill="${SCOL[s.kind]}" opacity=".38"/>`;
  }
  const order = { played: 0, plan: 1, threat: 2, mistake: 3, best: 4 };
  // depois do lance, a seta do "jogado" é redundante (o lance já aparece no tabuleiro); antes, ela mostra o que foi feito
  const arrows = (mo.arrows || []).filter(a => a.kind !== "played" || showBefore);
  for (const a of arrows.sort((x, y) => order[x.kind] - order[y.kind])) {
    const [x1, y1] = sqPt(a.from), [x2, y2] = sqPt(a.to), dx = x2 - x1, dy = y2 - y1, L = Math.hypot(dx, dy) || 1, ux = dx / L, uy = dy / L;
    const ex = x2 - ux * 0.1, ey = y2 - uy * 0.1, bx = ex - ux * 0.36, by = ey - uy * 0.36, hw = 0.25, col = ACOL[a.kind] || ACOL.plan;
    out += `<g opacity=".9"><line x1="${x1 + ux * 0.18}" y1="${y1 + uy * 0.18}" x2="${bx}" y2="${by}" stroke="${col}" stroke-width=".14" stroke-linecap="round"${a.kind === "played" ? ' stroke-dasharray=".22 .16"' : ""}/>` +
      `<polygon points="${ex},${ey} ${bx - uy * hw},${by + ux * hw} ${bx + uy * hw},${by - ux * hw}" fill="${col}"/></g>`;
    if (a.label && a.kind !== "played") {  // rótulo dentro do tabuleiro (não corta na borda); o "jogado" já está na legenda
      const hw2 = a.label.length * 0.085 + 0.1;  // meia largura estimada do texto
      const lx = Math.max(hw2, Math.min(8 - hw2, (x1 + x2) / 2 - uy * 0.2)), ly = Math.max(0.35, Math.min(7.75, (y1 + y2) / 2 + ux * 0.2));
      out += `<text x="${lx}" y="${ly}" fill="${col}" text-anchor="middle">${esc(a.label)}</text>`;
    }
  }
  svg.innerHTML = out;
}

function renderEvalBar() {
  const bar = $("#evalbar"), R = G.review;
  bar.hidden = !(reviewMode && R && R.curve && !G.hidden);
  if (bar.hidden) return;
  const ev = R.curve[Math.min(shownPly(), R.curve.length - 1)], flip = G.human_color === "black";
  bar.classList.toggle("flip", flip);
  bar.querySelector(".evw").style.height = (100 / (1 + Math.exp(-0.5 * ev))).toFixed(1) + "%";
  const t = bar.querySelector(".evt"), atBottom = (ev >= 0) !== flip;
  t.textContent = Math.abs(ev) >= 10 ? "#" : Math.abs(ev).toFixed(1);
  t.style.cssText = atBottom ? "bottom:0;color:#222" : "top:0;color:#eee";
}

/* ---------- painel da revisão (ao lado do tabuleiro) ---------- */
async function ensureModels() { if (!MODELS.length) MODELS = await api("/api/models"); }
const STAGE = { engine: "O motor está avaliando a partida", deep: "O motor está calculando os momentos", moments: "O professor está explicando os momentos", synth: "O professor está escrevendo a síntese" };

function commentHtml(mo, m) {
  const s = sev(mo), tags = (mo.concepts || []).map(c => `<span class="tag">${esc(c)}</span>`).join("");
  let h = `<div class="cmt ${s}"><div class="tags"><span class="tag ${s === "good" ? "" : "bad"}">${SEVL[s]}</span><span class="tag">perda ${mo.loss} cp</span>` +
    `${mo.best && mo.best !== mo.san ? `<span class="tag">motor preferia ${esc(mo.best)}</span>` : ""}${mo.better ? `<span class="tag ok">melhor: ${esc(mo.better)}</span>` : ""}</div>`;
  h += `<h4>${esc(mo.title || "Momento crítico")}</h4>`;
  if (mo.status === "done") {
    h += `<div class="tags">${tags}</div><p>${esc(mo.explanation)}</p>` + (mo.agent_check ? `<p class="hint"><b>Leitura do Claude na época:</b> ${esc(mo.agent_check)}</p>` : "");
  } else if (mo.status === "error") h += `<p style="color:var(--bad)">Explicação indisponível: ${esc(mo.error || "falha")}</p>`;
  else h += `<p class="hint">⏳ O professor está escrevendo esta explicação… as setas do motor já estão no tabuleiro.</p>`;
  const t = m && m.by === "agent" ? m.thought : null;
  if (t) h += `<details><summary>O que o Claude pensou na época</summary><p><b>Plano:</b> ${esc(t.plan)}</p><p><b>Decisão:</b> ${esc(t.decision)}</p><p class="hint">nota ${t.eval_pawns >= 0 ? "+" : ""}${t.eval_pawns} (brancas) · confiança ${t.confidence}/5</p></details>`;
  h += `<button data-before>${showBefore ? "▶ Ver depois do lance" : "◀ Ver antes do lance (posição da decisão)"}</button></div>`;
  return h;
}

function summaryHtml(R) {
  const strongOk = R.engine_kind === "strong";
  let h = `<div class="tags">${strongOk ? `<span class="tag ok">motor forte: ${esc(R.engine_name)}</span>` : `<span class="tag bad">sem motor forte: régua rasa (números menos confiáveis)</span>`}</div>`;
  const st = R.stats || {}, row = (n, x) => x && x.n ? `<tr><td>${n}</td><td>${x.accuracy}%</td><td>${x.acpl}</td><td>${x.inaccuracies}/${x.mistakes}/${x.blunders}</td><td>${x.top1}%</td></tr>` : "";
  if (st.human?.n || st.agent?.n) h += `<table class="t"><tr><th></th><th>precisão</th><th>perda média (cp)</th><th>imprec/erros/blunders</th><th>= melhor do motor</th></tr>${row("Você", st.human)}${row("Claude", st.agent)}</table>`;
  if (R.overall) {
    h += `<h4 class="sec">Resumo</h4><p>${esc(R.overall)}</p><p><b>Por que esse resultado:</b> ${esc(R.result_reason)}</p>`;
    h += `<h4 class="sec">Fases</h4>` + (R.phases || []).map(p => `<p><b>${esc(p.name)}</b> <span class="hint">(lances ${esc(p.plies)})</span>: ${esc(p.assessment)}<br><span class="tags">${(p.concepts || []).map(c => `<span class="tag">${esc(c)}</span>`).join("")}</span></p>`).join("");
    h += `<h4 class="sec">Lições para você</h4>` + (R.lessons || []).map(l => `<div class="lesson"><b>${esc(l.title)}</b><br>${esc(l.explanation)}<br><span class="hint">Exercício: ${esc(l.practice)}</span></div>`).join("");
    if (R.agent_insights) h += `<h4 class="sec">O raciocínio do Claude</h4><p>${esc(R.agent_insights)}</p>`;
  } else h += `<p class="hint">A síntese (resumo, fases e lições) ainda está sendo escrita…</p>`;
  h += `<p class="hint">Revisão por ${esc(R.model)} (${esc(R.effort)}) · ${((R.usage?.tokens || 0) / 1000).toFixed(0)}k tokens · US$${(R.usage?.cost || 0).toFixed(2)}${R.dropped ? ` · ${R.dropped} sugestão(ões) inválida(s) descartada(s)` : ""}</p>`;
  return h;
}

function walkHtml(R) {
  const p = curPly(), mo = momentAt(p), m = p > 0 ? G.moves[p - 1] : null, ev = R.curve ? R.curve[Math.min(p, R.curve.length - 1)] : null;
  let h = `<div class="rvhead"><b>${p ? `${lbl(p)} ${esc(m.san)}` : "Posição inicial"}</b> <span class="hint">${m ? (m.by === "human" ? "você" : "Claude") : ""}${ev != null ? ` · avaliação ${evs(ev)}` : ""}</span></div>`;
  if (!p) h += `<p class="hint">Passe lance a lance com ▶ (ou as setas ← → do teclado). Quando houver comentário do professor, ele aparece aqui e as setas surgem no tabuleiro. <b>Próximo comentário</b> (ou a seta ↓) pula direto aos lances comentados.</p>`;
  if (mo) h += commentHtml(mo, m); else if (p) h += `<p class="hint">Sem comentário neste lance.</p>`;
  const list = commentPlies(), hasPrev = list.some(x => x < p), hasNext = list.some(x => x > p);
  h += `<div class="rvnav"><button data-nav2="start">⏮</button><button data-nav2="prev">◀</button><button data-nav2="next">▶</button><button data-nav2="end">⏭</button></div>
    <div class="rvnav"><button data-cm="-1"${hasPrev ? "" : " disabled"}>‹ comentário anterior</button><button class="primary" data-cm="1"${hasNext ? "" : " disabled"}>próximo comentário ›</button></div>`;
  h += `<div class="chips">${R.moments.map(x => `<button class="chip ${sev(x)}${x.ply === p ? " on" : ""}${x.status !== "done" ? " pend" : ""}" data-goto="${x.ply}">${esc(x.label)} ${esc(x.san)}</button>`).join("")}</div>`;
  return h;
}

function genFormHtml(R) {
  const opts = MODELS.map(m => `<option value="${esc(m.value)}"${m.value === revOpts.model ? " selected" : ""}>${esc(m.label)}</option>`).join("");
  return `<div class="revform"><p class="hint">Um professor lê a partida, o raciocínio que o Claude registrou e os momentos mais instrutivos, e explica por <b>conceitos</b> (centro, estrutura, colunas, segurança do rei…), com setas no tabuleiro e a verdade de um motor forte. Faz uma chamada curta por momento (em paralelo) e uma de síntese; estime ~${revOpts.depth === "quick" ? "20–40k" : "35–80k"} tokens. Fica salvo na partida.</p>
    <label>Modelo<select id="rv-model">${opts}</select></label>
    <label>Esforço<select id="rv-effort">${["low", "medium", "high", "xhigh"].map(e => `<option${e === revOpts.effort ? " selected" : ""}>${e}</option>`).join("")}</select></label>
    <label>Profundidade<select id="rv-depth"><option value="quick"${revOpts.depth === "quick" ? " selected" : ""}>rápida (6 momentos)</option><option value="full"${revOpts.depth === "full" ? " selected" : ""}>completa (10 momentos)</option></select></label>
    <button class="primary" id="rv-go">${R ? "Gerar de novo" : "Gerar revisão"}</button></div>`;
}

async function renderRvPanel() {
  const my = ++revSeq, card = $("#rv-panel");
  card.hidden = G.status !== "over" || G.hidden;
  if (card.hidden) return;
  const R = G.review, P = G.review_progress, keep = card.scrollTop;
  let html = "";
  if (G.review_busy) {
    html += `<div class="rvprog"><b>${P ? esc(STAGE[P.stage] || "Trabalhando") + `… (${P.done}/${P.total})` : "Preparando…"}</b><progress value="${P ? P.done : 0}" max="${P ? P.total : 1}" style="width:100%"></progress><span class="hint">Os comentários aparecem conforme ficam prontos${R ? ": já dá para começar a revisão." : "."}</span></div>`;
  }
  if (G.review_error) html += `<p style="color:var(--bad)">Problema na revisão: ${esc(G.review_error)}</p>`;
  let needForm = false;
  if (R && reviewMode) {
    html += `<div class="tabs"><button data-tab="walk" class="${rvTab === "walk" ? "on" : ""}">Lance a lance</button><button data-tab="sum" class="${rvTab === "sum" ? "on" : ""}">Resumo e lições</button><button data-exit style="margin-left:auto">✕ Sair</button></div>`;
    html += rvTab === "walk" ? walkHtml(R) : summaryHtml(R);
  } else if (R) {
    html += `<h3>Revisão do professor</h3>${R.overall ? `<p>${esc(R.overall)}</p>` : ""}<p class="hint">${R.moments.length} lances comentados, com setas no tabuleiro.</p><button class="primary big" id="rv-start">▶ Começar a revisão</button>`;
    if (!G.review_busy) { needForm = true; }
  } else if (!G.review_busy) {
    html += `<h3>Revisão do professor <small>(opcional, usa tokens)</small></h3>`;
    needForm = true;
  }
  let form = "";
  if (needForm) {
    await ensureModels(); if (my !== revSeq) return;
    revOpts.model = revOpts.model || G.settings.model;
    form = R ? `<details style="margin-top:10px"><summary>Gerar de novo…</summary>${genFormHtml(R)}</details>` : genFormHtml(R);
  }
  card.innerHTML = html + form;
  card.scrollTop = keep;
  card.querySelector("#rv-start")?.addEventListener("click", startReview);
  card.querySelector("[data-exit]")?.addEventListener("click", exitReview);
  card.querySelectorAll("[data-tab]").forEach(b => b.onclick = () => { rvTab = b.dataset.tab; renderRvPanel(); });
  card.querySelectorAll("[data-nav2]").forEach(b => b.onclick = () => nav(b.dataset.nav2));
  card.querySelectorAll("[data-cm]").forEach(b => b.onclick = () => nextComment(+b.dataset.cm));
  card.querySelectorAll("[data-goto]").forEach(b => b.onclick = () => gotoPly(+b.dataset.goto));
  card.querySelector("[data-before]")?.addEventListener("click", () => { showBefore = !showBefore; play("tick"); render(); });
  if (form) {
    card.querySelector("#rv-model").onchange = e => revOpts.model = e.target.value;
    card.querySelector("#rv-effort").onchange = e => revOpts.effort = e.target.value;
    card.querySelector("#rv-depth").onchange = e => { revOpts.depth = e.target.value; renderRvPanel(); };
    card.querySelector("#rv-go").onclick = async () => {
      if (R && !confirm("Gerar de novo substitui a revisão salva e gasta tokens novamente. Continuar?")) return;
      try { G = await api(`/api/games/${G.id}/review`, "POST", revOpts); reviewMode = false; render(); refresh(); } catch (e) { alert(e.message); }
    };
  }
}
