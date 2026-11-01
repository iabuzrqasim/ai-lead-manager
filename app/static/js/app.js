// Shared frontend helpers: auth, API calls, layout, formatting.

const TOKEN_KEY = "alm_token";
const STATUSES = ["New", "Contacted", "Qualified", "Proposal", "Won", "Lost"];

const auth = {
  get token() { try { return localStorage.getItem(TOKEN_KEY); } catch { return null; } },
  set(token) { try { localStorage.setItem(TOKEN_KEY, token); } catch {} },
  logout() { try { localStorage.removeItem(TOKEN_KEY); } catch {} location.href = "/login"; },
  require() { if (!this.token) { location.href = "/login"; throw new Error("not logged in"); } },
};

async function api(path, { method = "GET", body, form } = {}) {
  const headers = {};
  if (auth.token) headers.Authorization = `Bearer ${auth.token}`;
  let payload;
  if (form) { payload = new URLSearchParams(form); }
  else if (body !== undefined) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }

  let res;
  try { res = await fetch(path, { method, headers, body: payload }); }
  catch { throw new Error("Cannot reach the server. Is it running?"); }

  if (res.status === 401 && !path.endsWith("/login")) { auth.logout(); throw new Error("Session expired"); }
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    let msg = data.detail || `Request failed (${res.status})`;
    if (Array.isArray(msg)) msg = msg.map(e => `${e.loc?.slice(-1)[0] ?? ""}: ${e.msg}`).join("; ");
    throw new Error(msg);
  }
  return data;
}

// ---------- formatting ----------
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const statusBadge = (s) => `<span class="badge-status st-${esc(s)}">${esc(s)}</span>`;
const money = (n) => (n == null ? "—" : "$" + Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 }));
// API datetimes are naive UTC; treat them as UTC and show in local time.
const toDate = (iso) => (iso ? new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : iso + "Z") : null);
const fmtDate = (iso) => (iso ? toDate(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "—");
const fmtDateTime = (iso) => (iso ? toDate(iso).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "—");
const isPast = (iso) => iso && toDate(iso) < new Date();
const qs = (sel, root = document) => root.querySelector(sel);

// ---------- toasts ----------
function toast(message, type = "success") {
  let box = qs("#toast-box");
  if (!box) {
    box = document.createElement("div");
    box.id = "toast-box";
    box.className = "toast-container position-fixed bottom-0 end-0 p-3";
    document.body.appendChild(box);
  }
  const el = document.createElement("div");
  el.className = `toast align-items-center text-bg-${type === "error" ? "danger" : type} border-0`;
  el.innerHTML = `<div class="d-flex"><div class="toast-body">${esc(message)}</div>
    <button class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button></div>`;
  box.appendChild(el);
  const t = new bootstrap.Toast(el, { delay: 3500 });
  el.addEventListener("hidden.bs.toast", () => el.remove());
  t.show();
}

// ---------- layout ----------
const NAV = [
  ["dashboard", "bi-speedometer2", "Dashboard"],
  ["leads", "bi-people", "Leads"],
  ["follow-ups", "bi-calendar-check", "Follow-ups"],
];

function renderLayout(active, title, actionsHtml = "") {
  auth.require();
  const page = qs("#page");
  const shell = document.createElement("div");
  shell.className = "app-shell";
  shell.innerHTML = `
    <aside class="sidebar" id="sidebar">
      <div class="brand"><i class="bi bi-lightning-charge-fill text-warning"></i> AI Lead Manager
        <small>by TechNest Nova</small></div>
      <nav class="nav flex-column mt-3">
        ${NAV.map(([href, icon, label]) => `<a class="nav-link ${active === href ? "active" : ""}" href="/${href}">
          <i class="bi ${icon}"></i>${label}</a>`).join("")}
        <a class="nav-link" href="/docs" target="_blank"><i class="bi bi-code-slash"></i>API Docs</a>
      </nav>
      <div class="mt-auto p-3 small">
        <div class="text-truncate mb-2" id="user-email"></div>
        <button class="btn btn-sm btn-outline-light w-100" id="logout"><i class="bi bi-box-arrow-right"></i> Log out</button>
      </div>
    </aside>
    <div class="main">
      <div class="topbar">
        <button class="btn btn-light d-lg-none" id="menu-toggle"><i class="bi bi-list"></i></button>
        <h1 class="h5 mb-0 me-auto">${title}</h1>
        <div id="topbar-actions">${actionsHtml}</div>
      </div>
      <div class="content" id="content"></div>
    </div>`;
  const content = shell.querySelector("#content");
  while (page.firstChild) content.appendChild(page.firstChild);
  page.appendChild(shell);

  qs("#logout").onclick = () => auth.logout();
  qs("#menu-toggle").onclick = () => qs("#sidebar").classList.toggle("open");
  api("/api/auth/me").then(u => (qs("#user-email").textContent = u.email)).catch(() => {});
}

function setLoading(el, colspan) {
  const spinner = `<div class="text-center text-secondary py-4"><div class="spinner-border spinner-border-sm"></div> Loading…</div>`;
  el.innerHTML = colspan ? `<tr><td colspan="${colspan}">${spinner}</td></tr>` : spinner;
}

function emptyState(icon, text) {
  return `<div class="empty-state"><i class="bi ${icon}"></i>${esc(text)}</div>`;
}

// Converts a <input type="datetime-local"> value (local time) into an ISO string with timezone.
function localInputToIso(value) {
  return value ? new Date(value).toISOString() : null;
}

function defaultFollowUpInput(daysAhead = 1) {
  const d = new Date(Date.now() + daysAhead * 864e5);
  d.setMinutes(0, 0, 0);
  d.setHours(10);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function formToObject(form) {
  const obj = {};
  for (const [k, v] of new FormData(form).entries()) {
    const val = typeof v === "string" ? v.trim() : v;
    obj[k] = val === "" ? null : val;
  }
  return obj;
}
