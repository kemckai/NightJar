const PAGE_SIZE = 60;

const els = {
  search: document.getElementById("search"),
  country: document.getElementById("country"),
  era: document.getElementById("era"),
  minVictims: document.getElementById("min-victims"),
  sort: document.getElementById("sort"),
  reset: document.getElementById("reset"),
  results: document.getElementById("results"),
  status: document.getElementById("status"),
  more: document.getElementById("more"),
  total: document.getElementById("total-count"),
  dialog: document.getElementById("dossier"),
  dialogBody: document.getElementById("dossier-body"),
};

let records = [];
let filtered = [];
let shown = 0;

const escapeHtml = (s) =>
  String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const escapeRegex = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

function highlight(text, terms) {
  const safe = escapeHtml(text);
  if (!terms.length) return safe;
  const re = new RegExp(`(${terms.map((t) => escapeRegex(escapeHtml(t))).join("|")})`, "gi");
  return safe.replace(re, "<mark>$1</mark>");
}

function stampFor(r) {
  if (/unidentified|unknown|unsolved/i.test(r.name + " " + r.notes)) return "UNSOLVED";
  if (/executed/i.test(r.notes)) return "EXECUTED";
  if (/suicide/i.test(r.notes)) return "DECEASED";
  if (/convicted|sentenced|life imprisonment/i.test(r.notes)) return "CONVICTED";
  return "ON FILE";
}

function caseNo(r) {
  return `CASE ${String(r.id).padStart(4, "0")}-${(r.start ?? "????").toString().slice(-2)}`;
}

function populateFilters() {
  const countries = new Map();
  for (const r of records) countries.set(r.country, (countries.get(r.country) || 0) + 1);
  [...countries.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .forEach(([name, n]) => els.country.add(new Option(`${name} (${n})`, name)));

  const decades = new Set(records.filter((r) => r.start).map((r) => Math.floor(r.start / 10) * 10));
  const eras = [...decades].sort((a, b) => a - b);
  const pre1900 = eras.filter((d) => d < 1900);
  if (pre1900.length) els.era.add(new Option("Before 1900", "pre1900"));
  eras.filter((d) => d >= 1900).forEach((d) => els.era.add(new Option(`${d}s`, String(d))));
}

function currentTerms() {
  return els.search.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
}

function applyFilters() {
  const terms = currentTerms();
  const country = els.country.value;
  const era = els.era.value;
  const min = parseInt(els.minVictims.value, 10) || 0;

  filtered = records.filter((r) => {
    if (country && r.country !== country) return false;
    if (era === "pre1900" && !(r.start && r.start < 1900)) return false;
    if (era && era !== "pre1900") {
      const d = Number(era);
      if (!(r.start && r.start >= d && r.start < d + 10)) return false;
    }
    if (min && (r.provenN ?? 0) < min) return false;
    return terms.every((t) => r._haystack.includes(t));
  });

  const by = {
    "proven-desc": (a, b) => (b.provenN ?? -1) - (a.provenN ?? -1),
    "possible-desc": (a, b) => (b.possibleN ?? -1) - (a.possibleN ?? -1),
    "name-asc": (a, b) => a.name.localeCompare(b.name),
    "start-asc": (a, b) => (a.start ?? 9999) - (b.start ?? 9999),
    "start-desc": (a, b) => (b.start ?? 0) - (a.start ?? 0),
  }[els.sort.value];
  filtered.sort(by);

  shown = 0;
  els.results.innerHTML = "";
  renderMore();
  syncUrl();
}

function mugshotHtml(r, large = false) {
  const cls = `mugshot${large ? " mugshot-lg" : ""}`;
  if (!r.photo) {
    return `<div class="${cls} mugshot-empty" aria-hidden="true"><span>No photo<br>on file</span></div>`;
  }
  return `<div class="${cls}"><img src="${escapeHtml(r.photo)}" alt="Photo of ${escapeHtml(r.name)}" loading="lazy" referrerpolicy="no-referrer" onerror="this.parentNode.classList.add('mugshot-empty');this.remove()"></div>`;
}

function cardHtml(r, terms) {
  const tilt = ((r.id * 37) % 7) - 3;
  return `
    <button class="card" style="--tilt:${tilt * 0.4}deg" data-id="${r.id}">
      <div class="case-no"><span>${caseNo(r)}</span><span>${escapeHtml(r.years)}</span></div>
      <div class="card-head">
        <div>
          <h2>${highlight(r.name, terms)}</h2>
          <p class="meta">${highlight(r.country, terms)}</p>
        </div>
        ${mugshotHtml(r)}
      </div>
      <div class="counts">
        <div class="count"><strong>${escapeHtml(r.proven)}</strong><span>Proven</span></div>
        <div class="count"><strong>${escapeHtml(r.possible)}</strong><span>Possible</span></div>
        <span class="stamp">${stampFor(r)}</span>
      </div>
      <p class="notes">${highlight(r.notes || "No further notes on file.", terms)}</p>
    </button>`;
}

function renderMore() {
  const terms = currentTerms();
  const slice = filtered.slice(shown, shown + PAGE_SIZE);
  if (!filtered.length) {
    els.results.innerHTML = `<p class="empty">No matching files. The trail has gone cold.</p>`;
  } else {
    els.results.insertAdjacentHTML("beforeend", slice.map((r) => cardHtml(r, terms)).join(""));
  }
  shown += slice.length;
  els.more.hidden = shown >= filtered.length;
  els.status.textContent = filtered.length
    ? `Showing ${shown} of ${filtered.length} file${filtered.length === 1 ? "" : "s"}`
    : "";
}

function openDossier(id) {
  const r = records.find((x) => x.id === id);
  if (!r) return;
  const terms = currentTerms();
  els.dialogBody.innerHTML = `
    <div class="classified">CLASSIFIED &middot; ${caseNo(r)}</div>
    <span class="stamp">${stampFor(r)}</span>
    <div class="dossier-head">
      ${mugshotHtml(r, true)}
      <h2>${escapeHtml(r.name)}</h2>
    </div>
    <dl>
      <dt>Jurisdiction</dt><dd>${escapeHtml(r.country)}</dd>
      <dt>Years active</dt><dd>${escapeHtml(r.years)}</dd>
      <dt>Proven victims</dt><dd>${escapeHtml(r.proven)}</dd>
      <dt>Possible victims</dt><dd>${escapeHtml(r.possible)}</dd>
    </dl>
    <p class="report">${highlight(r.notes || "No further notes on file.", terms)}</p>
    ${r.wiki ? `<a class="wiki-link" href="${escapeHtml(r.wiki)}" target="_blank" rel="noopener">Read the full file on Wikipedia &rarr;</a>` : ""}`;
  els.dialog.showModal();
}

function syncUrl() {
  const p = new URLSearchParams();
  if (els.search.value.trim()) p.set("q", els.search.value.trim());
  if (els.country.value) p.set("country", els.country.value);
  if (els.era.value) p.set("era", els.era.value);
  if (els.minVictims.value) p.set("min", els.minVictims.value);
  if (els.sort.value !== "proven-desc") p.set("sort", els.sort.value);
  const qs = p.toString();
  history.replaceState(null, "", qs ? `?${qs}` : location.pathname);
}

function restoreFromUrl() {
  const p = new URLSearchParams(location.search);
  els.search.value = p.get("q") || "";
  els.country.value = p.get("country") || "";
  els.era.value = p.get("era") || "";
  els.minVictims.value = p.get("min") || "";
  els.sort.value = p.get("sort") || "proven-desc";
}

let debounce;
els.search.addEventListener("input", () => {
  clearTimeout(debounce);
  debounce = setTimeout(applyFilters, 120);
});
[els.country, els.era, els.sort].forEach((el) => el.addEventListener("change", applyFilters));
els.minVictims.addEventListener("input", applyFilters);
els.more.addEventListener("click", renderMore);
els.reset.addEventListener("click", () => {
  els.search.value = "";
  els.country.value = "";
  els.era.value = "";
  els.minVictims.value = "";
  els.sort.value = "proven-desc";
  applyFilters();
  els.search.focus();
});
els.results.addEventListener("click", (e) => {
  const card = e.target.closest(".card");
  if (card) openDossier(Number(card.dataset.id));
});
els.dialog.addEventListener("click", (e) => {
  if (e.target === els.dialog || e.target.closest(".close")) els.dialog.close();
});

fetch("data.json")
  .then((res) => res.json())
  .then((data) => {
    records = data.map((r) => ({
      ...r,
      _haystack: `${r.name} ${r.country} ${r.years} ${r.notes}`.toLowerCase(),
    }));
    els.total.textContent = records.length.toLocaleString();
    populateFilters();
    restoreFromUrl();
    applyFilters();
  })
  .catch(() => {
    els.status.textContent = "Failed to retrieve the files. Serve this folder over HTTP, e.g. `python3 -m http.server`.";
  });
