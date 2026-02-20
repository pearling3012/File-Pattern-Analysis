// ── State ────────────────────────────────────────────────
let currentPath = "";
let navHistory = [];
let historyIndex = -1;
let viewMode = "list";       // "list" | "icon" | "column" | "gallery"
let currentView = "files";   // "files" | "duplicates" | "search"
let currentItems = [];
let selectedIndex = -1;

let columns = [];            // column view: [{ path, items, selectedIdx }]
let galleryIdx = 0;          // gallery view selection
let quickLookVisible = false;
let quickLookItem = null;
let contextItem = null;
let activeFilter = "all";
let springLoadTimer = null;

// ── Icons ────────────────────────────────────────────────
const FOLDER_SVG = `<svg viewBox="0 0 48 48" class="icon-folder"><path d="M4 8c0-2.2 1.8-4 4-4h10l4 4h18c2.2 0 4 1.8 4 4v4H4V8z" fill="#5AC8FA"/><path d="M4 16h40v22c0 2.2-1.8 4-4 4H8c-2.2 0-4-1.8-4-4V16z" fill="#60BFFF"/><path d="M4 16h40v3c0 0-8 1-20 1S4 19 4 19V16z" fill="#8DD4FF" opacity="0.5"/></svg>`;

const ICONS = {
  folder: FOLDER_SVG,
  pdf: "📕", image: "🖼️", doc: "📘",
  text: "📄", archive: "📦", app: "⚙️", video: "🎬",
  audio: "🎵", file: "📃", desktop: "🖥️", download: "⬇️",
  document: "📄",
};


// ── Init ─────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  loadFavorites();
  loadDrives();
  initCollapsibleSections();
  initSearchFilters();
  initDeduplicator();
  navigateTo("C:\\Users\\admin\\Downloads");

  document.addEventListener("keydown", handleKeyDown);

  // Toolbar filter
  const searchInput = document.getElementById("search-input");
  searchInput.addEventListener("input", () => quickSearch(searchInput.value));
  searchInput.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { searchInput.value = ""; quickSearch(""); searchInput.blur(); }
  });

  // Smart search Enter
  document.getElementById("smart-search-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") smartSearch();
  });

  // View toggle buttons
  document.getElementById("btn-icon-view").addEventListener("click",    () => setViewMode("icon"));
  document.getElementById("btn-list-view").addEventListener("click",    () => setViewMode("list"));
  document.getElementById("btn-column-view").addEventListener("click",  () => setViewMode("column"));
  document.getElementById("btn-gallery-view").addEventListener("click", () => setViewMode("gallery"));

  document.getElementById("btn-back").addEventListener("click", goBack);
  document.getElementById("btn-forward").addEventListener("click", goForward);

  // Traffic lights
  document.querySelector(".sidebar .dot-red")?.addEventListener("click", () => window.pywebview?.api.close());
  document.querySelector(".sidebar .dot-yellow")?.addEventListener("click", () => window.pywebview?.api.minimize());
  document.querySelector(".sidebar .dot-green")?.addEventListener("click", (e) => {
    e.altKey ? window.pywebview?.api.zoom() : window.pywebview?.api.fullscreen();
  });

  window.addEventListener("blur",  () => document.querySelector(".sidebar .traffic-lights")?.classList.add("inactive"));
  window.addEventListener("focus", () => document.querySelector(".sidebar .traffic-lights")?.classList.remove("inactive"));

  // Dismiss context menu on click-away
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".context-menu")) hideContextMenu();
  });

  // Quick Look controls
  document.getElementById("ql-close")?.addEventListener("click", hideQuickLook);
  document.getElementById("quicklook-overlay")?.addEventListener("click", (e) => {
    if (e.target === e.currentTarget) hideQuickLook();
  });
  document.getElementById("ql-open")?.addEventListener("click", () => {
    if (quickLookItem) openFile(quickLookItem.path);
    hideQuickLook();
  });

  // Context menu item handlers
  document.querySelectorAll(".ctx-item[data-action]").forEach(el => {
    el.addEventListener("click", () => handleContextAction(el.dataset.action));
  });

  // Suppress browser right-click on the app
  document.getElementById("app").addEventListener("contextmenu", (e) => e.preventDefault());
});


// ── Keyboard ─────────────────────────────────────────────
function handleKeyDown(e) {
  if (document.activeElement.tagName === "INPUT") return;

  // Spacebar → Quick Look toggle
  if (e.key === " ") {
    e.preventDefault();
    if (quickLookVisible) { hideQuickLook(); return; }
    const item = getSelectedItem();
    if (item && !item.is_dir) showQuickLook(item);
    return;
  }

  if (e.key === "Escape") {
    if (quickLookVisible) { hideQuickLook(); return; }
    hideContextMenu();
    return;
  }

  if (e.key === "Backspace") { goUp(); e.preventDefault(); return; }
  if (e.altKey && e.key === "ArrowLeft")  { goBack();    return; }
  if (e.altKey && e.key === "ArrowRight") { goForward(); return; }

  if (viewMode === "gallery" && currentView === "files") {
    if (e.key === "ArrowLeft")  { galleryPrev(); e.preventDefault(); return; }
    if (e.key === "ArrowRight") { galleryNext(); e.preventDefault(); return; }
  }

  if (e.key === "ArrowDown")  { selectNext(); e.preventDefault(); }
  if (e.key === "ArrowUp")    { selectPrev(); e.preventDefault(); }
  if (e.key === "Enter" && selectedIndex >= 0) openSelected();
}

function getSelectedItem() {
  if (viewMode === "column") {
    for (let i = columns.length - 1; i >= 0; i--) {
      if (columns[i].selectedIdx >= 0) return columns[i].items[columns[i].selectedIdx];
    }
    return null;
  }
  if (viewMode === "gallery") return currentItems[galleryIdx] || null;
  return (selectedIndex >= 0 && currentItems[selectedIndex]) ? currentItems[selectedIndex] : null;
}


// ── Navigation ───────────────────────────────────────────
function navigateTo(path) {
  if (historyIndex < navHistory.length - 1) {
    navHistory = navHistory.slice(0, historyIndex + 1);
  }
  navHistory.push(path);
  historyIndex = navHistory.length - 1;
  currentPath = path;
  selectedIndex = -1;

  switchToFileView();

  updatePathBar(path);
  updateNavButtons();
  updateToolbarTitle(path);
  highlightSidebar(path);
}

function reloadCurrentView() {
  if (viewMode === "column")       loadColumnView(currentPath);
  else if (viewMode === "gallery") loadGalleryView(currentPath);
  else                             loadFiles(currentPath);
}

function updateToolbarTitle(path) {
  const parts = path.replace(/\\/g, "/").split("/").filter(Boolean);
  document.getElementById("toolbar-title").textContent =
    parts.length > 0 ? parts[parts.length - 1] : path;
}

function goBack() {
  if (historyIndex > 0) {
    historyIndex--;
    currentPath = navHistory[historyIndex];
    selectedIndex = -1;
    reloadCurrentView();
    updatePathBar(currentPath);
    updateNavButtons();
    updateToolbarTitle(currentPath);
    highlightSidebar(currentPath);
  }
}

function goForward() {
  if (historyIndex < navHistory.length - 1) {
    historyIndex++;
    currentPath = navHistory[historyIndex];
    selectedIndex = -1;
    reloadCurrentView();
    updatePathBar(currentPath);
    updateNavButtons();
    updateToolbarTitle(currentPath);
    highlightSidebar(currentPath);
  }
}

function goUp() {
  fetch(`/api/files?path=${encodeURIComponent(currentPath)}`)
    .then(r => r.json())
    .then(data => { if (data.parent) navigateTo(data.parent); });
}

function updateNavButtons() {
  document.getElementById("btn-back").disabled    = historyIndex <= 0;
  document.getElementById("btn-forward").disabled = historyIndex >= navHistory.length - 1;
}

function highlightSidebar(path) {
  document.querySelectorAll(".sidebar-item").forEach(i => i.classList.remove("active"));
  document.querySelectorAll(".sidebar-item[data-path]").forEach(i => {
    if (normPath(i.dataset.path) === normPath(path)) i.classList.add("active");
  });
}

function normPath(p) {
  return (p || "").replace(/\\/g, "/").replace(/\/+$/, "").toLowerCase();
}


// ── Path bar ─────────────────────────────────────────────
let pathbarPaths = [];

function updatePathBar(path) {
  const el = document.getElementById("pathbar");
  const parts = path.replace(/\\/g, "/").split("/").filter(Boolean);
  pathbarPaths = [];
  let cumPath = "";
  let html = "";

  parts.forEach((part, i) => {
    cumPath += part + (i === 0 && part.endsWith(":") ? "\\" : "\\");
    pathbarPaths.push(cumPath);
    const PF = `<svg viewBox="0 0 48 48" style="width:12px;height:12px;vertical-align:-1px"><path d="M4 8c0-2.2 1.8-4 4-4h10l4 4h18c2.2 0 4 1.8 4 4v4H4V8z" fill="#5AC8FA"/><path d="M4 16h40v22c0 2.2-1.8 4-4 4H8c-2.2 0-4-1.8-4-4V16z" fill="#60BFFF"/></svg>`;
    const icon = i === 0 ? "💾" : PF;
    if (i > 0) html += '<span class="pathbar-sep">›</span>';
    html += `<span class="pathbar-part" data-idx="${i}"><span class="pathbar-icon">${icon}</span>${escapeHtml(part)}</span>`;
  });

  el.innerHTML = html;
  el.querySelectorAll(".pathbar-part").forEach(span => {
    span.addEventListener("click", () => navigateTo(pathbarPaths[parseInt(span.dataset.idx)]));
  });
}


// ── View mode management ─────────────────────────────────
function setViewMode(mode) {
  const prev = viewMode;
  viewMode = mode;

  document.querySelectorAll(".view-btn").forEach(b => b.classList.remove("active"));
  document.getElementById(`btn-${mode}-view`).classList.add("active");

  if (currentView !== "files") return;

  // Lightweight toggle between list ↔ icon
  if ((prev === "list" || prev === "icon") && (mode === "list" || mode === "icon")) {
    document.getElementById("file-list").classList.toggle("grid-view", mode === "icon");
    document.getElementById("file-header").style.display = mode === "list" ? "" : "none";
    return;
  }

  switchToFileView();
}

function switchToFileView() {
  currentView = "files";
  document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
  document.querySelectorAll(".tool-item").forEach(t => t.classList.remove("active"));

  if (viewMode === "column") {
    document.getElementById("view-columns").classList.add("active");
    loadColumnView(currentPath);
  } else if (viewMode === "gallery") {
    document.getElementById("view-gallery").classList.add("active");
    loadGalleryView(currentPath);
  } else {
    document.getElementById("view-files").classList.add("active");
    document.getElementById("file-list").classList.toggle("grid-view", viewMode === "icon");
    document.getElementById("file-header").style.display = viewMode === "list" ? "" : "none";
    loadFiles(currentPath);
  }
}

function switchView(name) {
  if (name === "files") { switchToFileView(); return; }
  currentView = name;
  document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
  document.getElementById(`view-${name}`).classList.add("active");
  document.querySelectorAll(".tool-item").forEach(t => t.classList.remove("active"));
  const tb = document.getElementById(`tool-${name}`);
  if (tb) tb.classList.add("active");
}

function openTool(name) {
  if (name === "duplicates") {
    document.getElementById("scan-path-input").value = currentPath;
  }
  switchView(name);
}


// ── Load files (list / icon) ─────────────────────────────
async function loadFiles(path) {
  const list = document.getElementById("file-list");
  list.innerHTML = '<div class="empty-state"><div class="spinner"></div><p>Loading...</p></div>';

  try {
    const res = await fetch(`/api/files?path=${encodeURIComponent(path)}`);
    const data = await res.json();

    if (data.error) {
      list.innerHTML = `<div class="empty-state"><div class="empty-icon">⚠️</div><p>${escapeHtml(data.error)}</p></div>`;
      return;
    }
    if (data.items.length === 0) {
      list.innerHTML = '<div class="empty-state"><div class="empty-icon">📂</div><p>This folder is empty</p></div>';
      setStatus("0 items");
      return;
    }

    currentItems = data.items;
    list.innerHTML = data.items.map((item, idx) => `
      <div class="file-row" data-idx="${idx}">
        <div class="col-name">
          <div class="file-icon">${ICONS[item.icon] || ICONS.file}</div>
          <span class="file-name">${escapeHtml(item.name)}</span>
        </div>
        <div class="col-size">${item.is_dir ? "--" : item.size_human}</div>
        <div class="col-modified">${item.modified}</div>
        <div class="col-type">${item.is_dir ? "Folder" : (item.extension || "")}</div>
      </div>
    `).join("");

    attachRowHandlers(list);
    setStatus(`${data.count} items`);
  } catch (err) {
    list.innerHTML = `<div class="empty-state"><div class="empty-icon">❌</div><p>Failed to load: ${escapeHtml(err.message)}</p></div>`;
  }
}

function attachRowHandlers(container) {
  container.querySelectorAll(".file-row").forEach(row => {
    const idx = parseInt(row.dataset.idx);
    const item = currentItems[idx];

    row.addEventListener("click", () => selectRow(idx));
    row.addEventListener("dblclick", () => {
      item.is_dir ? navigateTo(item.path) : openFile(item.path);
    });
    row.addEventListener("contextmenu", (e) => { selectRow(idx); showContextMenu(e, item); });

    // Spring-loading: drag over folder → opens after 1s
    if (item.is_dir) {
      row.addEventListener("dragover", (e) => {
        e.preventDefault();
        row.classList.add("spring-hover");
        if (!springLoadTimer) {
          springLoadTimer = setTimeout(() => { navigateTo(item.path); springLoadTimer = null; }, 1000);
        }
      });
      row.addEventListener("dragleave", () => { row.classList.remove("spring-hover"); clearTimeout(springLoadTimer); springLoadTimer = null; });
      row.addEventListener("drop", (e) => { e.preventDefault(); row.classList.remove("spring-hover"); clearTimeout(springLoadTimer); springLoadTimer = null; });
    }
  });
}


// ── Column view ──────────────────────────────────────────
async function loadColumnView(path) {
  const res = await fetch(`/api/files?path=${encodeURIComponent(path)}`);
  const data = await res.json();
  columns = [{ path, items: data.items || [], selectedIdx: -1 }];
  renderColumns();
}

function renderColumns() {
  const container = document.getElementById("column-container");
  container.innerHTML = "";

  columns.forEach((col, colIdx) => {
    const pane = document.createElement("div");
    pane.className = "column-pane";

    col.items.forEach((item, idx) => {
      const row = document.createElement("div");
      row.className = "col-item" + (idx === col.selectedIdx ? " selected" : "");
      row.innerHTML = `
        <span class="col-item-icon">${ICONS[item.icon] || ICONS.file}</span>
        <span class="col-item-name">${escapeHtml(item.name)}</span>
        ${item.is_dir ? '<span class="col-item-arrow">›</span>' : ''}
      `;
      row.addEventListener("click", () => columnItemClick(colIdx, idx, item));
      row.addEventListener("dblclick", () => { if (!item.is_dir) openFile(item.path); });
      row.addEventListener("contextmenu", (e) => showContextMenu(e, item));

      if (item.is_dir) {
        row.addEventListener("dragover", (e) => {
          e.preventDefault(); row.classList.add("spring-hover");
          if (!springLoadTimer) {
            springLoadTimer = setTimeout(() => { columnItemClick(colIdx, idx, item); springLoadTimer = null; }, 1000);
          }
        });
        row.addEventListener("dragleave", () => { row.classList.remove("spring-hover"); clearTimeout(springLoadTimer); springLoadTimer = null; });
      }

      pane.appendChild(row);
    });

    container.appendChild(pane);
  });

  // If the last column has a selected file (not dir), show preview pane
  const lastCol = columns[columns.length - 1];
  if (lastCol.selectedIdx >= 0) {
    const selItem = lastCol.items[lastCol.selectedIdx];
    if (selItem && !selItem.is_dir) {
      const preview = document.createElement("div");
      preview.className = "column-preview";
      preview.innerHTML = `
        <div class="column-preview-icon">${ICONS[selItem.icon] || ICONS.file}</div>
        <div class="column-preview-name">${escapeHtml(selItem.name)}</div>
        <div class="column-preview-meta">
          ${selItem.size_human || "--"}<br>${selItem.modified}<br>${selItem.extension || ""}
        </div>
      `;
      container.appendChild(preview);
    }
  }

  container.scrollLeft = container.scrollWidth;
}

async function columnItemClick(colIdx, itemIdx, item) {
  columns[colIdx].selectedIdx = itemIdx;
  columns = columns.slice(0, colIdx + 1);

  if (item.is_dir) {
    const res = await fetch(`/api/files?path=${encodeURIComponent(item.path)}`);
    const data = await res.json();
    if (!data.error) {
      columns.push({ path: item.path, items: data.items || [], selectedIdx: -1 });
      currentPath = item.path;
      updatePathBar(currentPath);
      updateToolbarTitle(currentPath);
    }
  }

  renderColumns();
}


// ── Gallery view ─────────────────────────────────────────
async function loadGalleryView(path) {
  const res = await fetch(`/api/files?path=${encodeURIComponent(path)}`);
  const data = await res.json();

  if (data.error || !data.items || data.items.length === 0) {
    document.getElementById("gallery-preview").innerHTML =
      '<div class="empty-state"><div class="empty-icon">📂</div><p>This folder is empty</p></div>';
    document.getElementById("gallery-strip").innerHTML = "";
    currentItems = [];
    return;
  }

  currentItems = data.items;
  galleryIdx = 0;
  renderGallery();
  setStatus(`${data.items.length} items`);
}

function renderGallery() {
  const preview = document.getElementById("gallery-preview");
  const strip = document.getElementById("gallery-strip");
  const item = currentItems[galleryIdx];
  if (!item) return;

  selectedIndex = galleryIdx;

  const isImage = item.icon === "image";
  preview.innerHTML = `
    ${isImage
      ? `<img src="/api/file-content?path=${encodeURIComponent(item.path)}" class="gallery-image" />`
      : `<div class="gallery-big-icon">${ICONS[item.icon] || ICONS.file}</div>`
    }
    <div class="gallery-name">${escapeHtml(item.name)}</div>
    <div class="gallery-meta">${item.size_human || "--"} — ${item.modified}</div>
  `;

  strip.innerHTML = currentItems.map((it, idx) => {
    const isImg = it.icon === "image";
    return `
      <div class="gallery-thumb ${idx === galleryIdx ? 'selected' : ''}" data-idx="${idx}">
        ${isImg
          ? `<img src="/api/file-content?path=${encodeURIComponent(it.path)}" class="gallery-thumb-img" />`
          : `<div class="gallery-thumb-icon">${ICONS[it.icon] || ICONS.file}</div>`
        }
      </div>
    `;
  }).join("");

  strip.querySelectorAll(".gallery-thumb").forEach(thumb => {
    const idx = parseInt(thumb.dataset.idx);
    thumb.addEventListener("click", () => { galleryIdx = idx; renderGallery(); });
    thumb.addEventListener("dblclick", () => {
      const it = currentItems[idx];
      it.is_dir ? navigateTo(it.path) : openFile(it.path);
    });
    thumb.addEventListener("contextmenu", (e) => {
      galleryIdx = idx; renderGallery();
      showContextMenu(e, currentItems[idx]);
    });
  });

  // Scroll selected thumb into view
  const selThumb = strip.querySelector(".gallery-thumb.selected");
  if (selThumb) selThumb.scrollIntoView({ block: "nearest", inline: "center" });
}

function galleryPrev() {
  if (galleryIdx > 0) { galleryIdx--; renderGallery(); }
}
function galleryNext() {
  if (galleryIdx < currentItems.length - 1) { galleryIdx++; renderGallery(); }
}


// ── Row selection ────────────────────────────────────────
function selectRow(idx) {
  selectedIndex = idx;
  document.querySelectorAll(".file-row").forEach((row, i) => {
    row.classList.toggle("selected", i === idx);
  });
}

function selectNext() {
  if (currentItems.length === 0) return;
  selectRow(Math.min(selectedIndex + 1, currentItems.length - 1));
  scrollRowIntoView(selectedIndex);
}

function selectPrev() {
  if (currentItems.length === 0) return;
  selectRow(Math.max(selectedIndex - 1, 0));
  scrollRowIntoView(selectedIndex);
}

function scrollRowIntoView(idx) {
  const rows = document.querySelectorAll(".file-row");
  if (rows[idx]) rows[idx].scrollIntoView({ block: "nearest" });
}

function openSelected() {
  if (selectedIndex < 0 || selectedIndex >= currentItems.length) return;
  const item = currentItems[selectedIndex];
  item.is_dir ? navigateTo(item.path) : openFile(item.path);
}


// ── Sidebar ──────────────────────────────────────────────
async function loadFavorites() {
  const res = await fetch("/api/favorites");
  const favs = await res.json();
  const el = document.getElementById("favorites");
  el.innerHTML = favs.map((f, i) => `
    <button class="sidebar-item" data-fav="${i}" data-path="${escapeAttr(f.path)}">
      <span class="sidebar-icon">${ICONS[f.icon] || "📁"}</span> ${escapeHtml(f.name)}
    </button>
  `).join("");
  el.querySelectorAll(".sidebar-item").forEach(btn => {
    btn.addEventListener("click", () => navigateTo(btn.dataset.path));
  });
}

async function loadDrives() {
  const res = await fetch("/api/drives");
  const drives = await res.json();
  const el = document.getElementById("drives");
  el.innerHTML = drives.map((d, i) => `
    <button class="sidebar-item" data-drv="${i}" data-path="${escapeAttr(d.path)}">
      <span class="sidebar-icon">💾</span> ${escapeHtml(d.name)}
      ${d.free_human ? `<span style="margin-left:auto;font-size:10px;color:#86868b">${d.free_human}</span>` : ""}
    </button>
  `).join("");
  el.querySelectorAll(".sidebar-item").forEach(btn => {
    btn.addEventListener("click", () => navigateTo(btn.dataset.path));
  });
}


// ── Collapsible sidebar sections ─────────────────────────
function initCollapsibleSections() {
  document.querySelectorAll(".sidebar-label[data-section]").forEach(label => {
    label.addEventListener("click", () => {
      label.closest(".sidebar-section").classList.toggle("collapsed");
    });
  });
}


// ── Search filters ───────────────────────────────────────
function initSearchFilters() {
  const input = document.getElementById("search-input");
  const filters = document.getElementById("search-filters");

  input.addEventListener("focus", () => filters.classList.add("visible"));
  input.addEventListener("blur",  () => setTimeout(() => filters.classList.remove("visible"), 150));

  filters.querySelectorAll(".search-filter").forEach(btn => {
    btn.addEventListener("mousedown", (e) => {
      e.preventDefault();
      filters.querySelectorAll(".search-filter").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      activeFilter = btn.dataset.filter;
      quickSearch(input.value);
    });
  });
}


// ── Quick filter ─────────────────────────────────────────
function quickSearch(query) {
  const rows = document.querySelectorAll(".file-row");
  if (!query.trim() && activeFilter === "all") { rows.forEach(r => r.style.display = ""); return; }
  const q = query.toLowerCase();
  rows.forEach(row => {
    const idx = parseInt(row.dataset.idx);
    const item = currentItems[idx];
    if (!item) return;
    const nameMatch = !q || item.name.toLowerCase().includes(q);
    let filterMatch = true;
    if (activeFilter === "folders")   filterMatch = item.is_dir;
    if (activeFilter === "documents") filterMatch = ["text", "pdf", "doc"].includes(item.icon);
    if (activeFilter === "images")    filterMatch = item.icon === "image";
    if (activeFilter === "archives")  filterMatch = item.icon === "archive";
    row.style.display = (nameMatch && filterMatch) ? "" : "none";
  });
}


// ── Deduplicator ─────────────────────────────────────────

function initDeduplicator() {
  const pathInput = document.getElementById("scan-path-input");
  pathInput.value = currentPath;

  // "Current Folder" button fills input with the actively-browsed path
  document.getElementById("btn-use-current").addEventListener("click", () => {
    pathInput.value = currentPath;
    pathInput.focus();
  });

  // Enter in path input starts scan
  pathInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") startScan();
  });

  // Populate quick-access path chips
  loadDeduplicatorQuickPaths();
}

async function loadDeduplicatorQuickPaths() {
  const el = document.getElementById("dedup-quick-paths");
  const home = await fetch("/api/favorites").then(r => r.json());
  const drives = await fetch("/api/drives").then(r => r.json());

  const paths = [
    ...home.map(f => ({ name: f.name, icon: "📁", path: f.path })),
    ...drives.map(d => ({ name: d.name, icon: "💾", path: d.path })),
  ];

  el.innerHTML = paths.map(p =>
    `<button class="dedup-quick-btn" data-path="${escapeAttr(p.path)}"><span class="qp-icon">${p.icon}</span>${escapeHtml(p.name)}</button>`
  ).join("");

  el.querySelectorAll(".dedup-quick-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.getElementById("scan-path-input").value = btn.dataset.path;
    });
  });
}

async function startScan() {
  const pathInput = document.getElementById("scan-path-input");
  const scanPath = pathInput.value.trim();
  if (!scanPath) { pathInput.focus(); return; }

  const btn = document.getElementById("btn-scan");
  const status = document.getElementById("scan-status");
  const results = document.getElementById("scan-results");
  btn.disabled = true;
  status.innerHTML = '<span class="spinner"></span> Scanning...';
  results.innerHTML = "";

  try {
    const res = await fetch("/api/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: scanPath }),
    });
    const data = await res.json();
    if (data.error) { status.textContent = `Error: ${data.error}`; btn.disabled = false; return; }
    status.textContent = `Done — scanned ${data.total_files.toLocaleString()} files`;
    renderScanResults(data, scanPath);
  } catch (err) { status.textContent = `Error: ${err.message}`; }
  btn.disabled = false;
}

function renderScanResults(data, scanPath) {
  const el = document.getElementById("scan-results");
  let html = `
    <div class="scan-summary">
      <div class="stat-card"><div class="stat-value">${data.total_files.toLocaleString()}</div><div class="stat-label">Files Scanned</div></div>
      <div class="stat-card"><div class="stat-value ${data.duplicate_files > 0 ? 'danger' : 'success'}">${data.duplicate_files.toLocaleString()}</div><div class="stat-label">Duplicates</div></div>
      <div class="stat-card"><div class="stat-value">${data.duplicate_groups}</div><div class="stat-label">Groups</div></div>
      <div class="stat-card"><div class="stat-value danger">${data.wasted_human}</div><div class="stat-label">Space Wasted</div></div>
    </div>
  `;

  if (data.groups && data.groups.length > 0) {
    const sorted = [...data.groups].sort((a, b) => (b.length - 1) * b[0].size - (a.length - 1) * a[0].size);
    sorted.forEach((group, i) => {
      const waste = (group.length - 1) * group[0].size;
      const fileSize = humanSize(group[0].size);
      html += `
        <div class="dup-group">
          <div class="dup-group-header">
            <span class="dup-group-title">Group ${i + 1} — ${group.length} copies · ${fileSize} each</span>
            <span class="dup-group-waste">${humanSize(waste)} wasted</span>
          </div>
          ${group.map((f, fi) => {
            const name = f.path.replace(/\\/g, "/").split("/").pop();
            const dir = f.path.replace(/\\/g, "/").split("/").slice(0, -1).join("/");
            return `
              <div class="dup-file" data-dg="${i}" data-df="${fi}">
                <span class="dup-file-icon">📄</span>
                <span class="dup-file-info">
                  <span class="dup-file-name">${escapeHtml(name)}</span>
                  <span class="dup-file-dir">${escapeHtml(dir)}</span>
                </span>
                <button class="dup-file-action" data-action="reveal" data-path="${escapeAttr(f.path)}" title="Show in Explorer">📂</button>
                <button class="dup-file-action" data-action="open" data-path="${escapeAttr(f.path)}" title="Open file">↗</button>
              </div>
            `;
          }).join("")}
        </div>
      `;
    });

    el.innerHTML = html;

    el.querySelectorAll(".dup-file-action").forEach(btn => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const path = btn.dataset.path;
        if (btn.dataset.action === "reveal") {
          fetch("/api/reveal", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path }) });
        } else {
          openFile(path);
        }
      });
    });

    el.querySelectorAll(".dup-file").forEach(item => {
      item.addEventListener("dblclick", () => {
        const gi = parseInt(item.dataset.dg), fi = parseInt(item.dataset.df);
        openFile(sorted[gi][fi].path);
      });
    });
  } else {
    html += '<div class="empty-state"><div class="empty-icon">✅</div><p>No duplicates found in this folder!</p></div>';
    el.innerHTML = html;
  }
}


// ── Smart Search ─────────────────────────────────────────
let searchResults = [];

async function smartSearch() {
  const input = document.getElementById("smart-search-input");
  const resultsEl = document.getElementById("search-results");
  const query = input.value.trim();
  if (!query) return;

  resultsEl.innerHTML = '<div class="empty-state"><span class="spinner"></span><p>Searching...</p></div>';
  try {
    const res = await fetch("/api/search", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query, n_results: 8 }) });
    const data = await res.json();

    if (data.error) { resultsEl.innerHTML = `<div class="empty-state"><div class="empty-icon">⚠️</div><p>${escapeHtml(data.error)}</p></div>`; return; }
    if (!data.results || data.results.length === 0) { resultsEl.innerHTML = '<div class="empty-state"><div class="empty-icon">🔍</div><p>No results. Try indexing a folder first.</p></div>'; return; }

    searchResults = data.results;
    resultsEl.innerHTML = data.results.map((hit, i) => {
      const badge = hit.score >= 80 ? "badge-green" : hit.score >= 60 ? "badge-yellow" : "badge-blue";
      const preview = (hit.chunk_text || "").substring(0, 200).replace(/\n/g, " ");
      return `
        <div class="result-card" data-si="${i}">
          <div class="result-title"><span>${i + 1}. ${escapeHtml(hit.file_name)}</span><span class="result-badge ${badge}">${hit.score}%</span><span style="font-size:10px;color:#86868b">${(hit.file_type || "").toUpperCase()}</span></div>
          <div class="result-path">${escapeHtml(hit.path)}</div>
          <div class="result-preview">${escapeHtml(preview)}</div>
        </div>
      `;
    }).join("");

    resultsEl.querySelectorAll(".result-card").forEach(card => {
      card.addEventListener("dblclick", () => openFile(searchResults[parseInt(card.dataset.si)].path));
    });
  } catch (err) { resultsEl.innerHTML = `<div class="empty-state"><div class="empty-icon">❌</div><p>${escapeHtml(err.message)}</p></div>`; }
}

async function startIndex() {
  const btn = document.getElementById("btn-index");
  const status = document.getElementById("index-status");
  btn.disabled = true;
  status.innerHTML = '<span class="spinner"></span> Indexing...';
  try {
    const res = await fetch("/api/index", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: currentPath }) });
    const data = await res.json();
    status.textContent = data.error ? `Error: ${data.error}` : `Indexed ${data.files_indexed} files (${data.total_chunks} chunks). Ready to search!`;
  } catch (err) { status.textContent = `Error: ${err.message}`; }
  btn.disabled = false;
}


// ── Quick Look ───────────────────────────────────────────
function showQuickLook(item) {
  quickLookVisible = true;
  quickLookItem = item;

  const overlay  = document.getElementById("quicklook-overlay");
  const filename = document.getElementById("ql-filename");
  const content  = document.getElementById("ql-content");
  const footer   = document.getElementById("ql-footer");

  overlay.classList.add("visible");
  filename.textContent = item.name;
  footer.textContent = `${item.size_human || "--"}  ·  ${item.modified}  ·  ${item.extension || "File"}`;

  if (item.icon === "image") {
    content.innerHTML = `<img src="/api/file-content?path=${encodeURIComponent(item.path)}" class="ql-image" />`;
  } else if (["text", "pdf", "doc"].includes(item.icon)) {
    content.innerHTML = '<div class="spinner"></div>';
    fetch(`/api/preview?path=${encodeURIComponent(item.path)}`)
      .then(r => r.json())
      .then(data => {
        content.innerHTML = data.preview_text
          ? `<pre class="ql-text">${escapeHtml(data.preview_text)}</pre>`
          : `<div class="ql-icon-large">${ICONS[item.icon] || ICONS.file}</div>`;
      })
      .catch(() => { content.innerHTML = `<div class="ql-icon-large">${ICONS[item.icon] || ICONS.file}</div>`; });
  } else {
    content.innerHTML = `<div class="ql-icon-large">${ICONS[item.icon] || ICONS.file}</div>`;
  }
}

function hideQuickLook() {
  quickLookVisible = false;
  quickLookItem = null;
  document.getElementById("quicklook-overlay").classList.remove("visible");
}


// ── Context menu ─────────────────────────────────────────
function showContextMenu(e, item) {
  e.preventDefault();
  e.stopPropagation();
  contextItem = item;

  const menu = document.getElementById("context-menu");
  menu.classList.add("visible");
  menu.style.left = e.clientX + "px";
  menu.style.top  = e.clientY + "px";

  requestAnimationFrame(() => {
    const rect = menu.getBoundingClientRect();
    if (rect.right  > window.innerWidth)  menu.style.left = (e.clientX - rect.width) + "px";
    if (rect.bottom > window.innerHeight) menu.style.top  = (e.clientY - rect.height) + "px";
  });
}

function hideContextMenu() {
  document.getElementById("context-menu").classList.remove("visible");
  contextItem = null;
}

function handleContextAction(action) {
  if (!contextItem) return;
  const item = contextItem;
  hideContextMenu();

  switch (action) {
    case "open":
      item.is_dir ? navigateTo(item.path) : openFile(item.path);
      break;
    case "quicklook":
      if (!item.is_dir) showQuickLook(item);
      break;
    case "getinfo":
      showQuickLook(item);
      break;
    case "copypath":
      navigator.clipboard?.writeText(item.path);
      break;
    case "reveal":
      fetch("/api/reveal", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: item.path }) });
      break;
  }
}


// ── File actions ─────────────────────────────────────────
async function openFile(path) {
  await fetch("/api/open", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path }) });
}


// ── Utilities ────────────────────────────────────────────
function setStatus(text) {
  let el = document.getElementById("status-text");
  if (!el) {
    el = document.createElement("span");
    el.id = "status-text";
    el.style.cssText = "margin-left:auto;font-size:11px;color:#86868b;white-space:nowrap;";
    document.getElementById("pathbar")?.appendChild(el);
  }
  el.textContent = text;
}

function escapeHtml(str) {
  const d = document.createElement("div");
  d.textContent = str;
  return d.innerHTML;
}

function escapeAttr(str) {
  return str.replace(/&/g,"&amp;").replace(/"/g,"&quot;").replace(/'/g,"&#39;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

function humanSize(bytes) {
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (bytes >= 1024 && i < u.length - 1) { bytes /= 1024; i++; }
  return `${bytes.toFixed(1)} ${u[i]}`;
}
