// Prospect list: statistics, filter bar, configurable table, selection and bulk actions.
import { buildQueryString, requestJson } from "./api.js";
import { createElement, formatDate, readableHost, showToast } from "./dom.js";
import { OPPORTUNITY_LABELS, SOURCE_LABELS, STATUS_LABELS } from "./labels.js";
import { renderScoreBadge } from "./components.js";
import { liveEvents } from "./live.js";
import { openProspectDetail } from "./prospect_detail.js";
import { createActionMenu, createPopover } from "./popover.js";
import { clearAllFilters, initializeFilterBar, isAreaFilterActive, onAreaPicked, onFiltersChanged, readFilterQuery, refreshFilterBar, resetFilters, setFacets } from "./prospect_filters.js";
import { createCoalescedRefresher, isSectionVisible, referenceData, settingsEvents } from "./store.js";

const SORT_STORAGE_KEY = "prospect-list-sort";
const COLUMNS_STORAGE_KEY = "prospect-list-columns";
// Each sortable column names the server sort key; clicking a header twice reverses the order
const TABLE_COLUMNS = [
  { key: "selection", fixed: true },
  { key: "score", label: "Score", sort: "score", visibleByDefault: true },
  { key: "name", label: "Entreprise", sort: "name", fixed: true },
  { key: "sector", label: "Secteur", sort: "sector" },
  { key: "city", label: "Ville", sort: "city", visibleByDefault: true },
  { key: "postal_code", label: "Code postal", sort: "postal_code" },
  { key: "distance", label: "Distance", sort: "distance", requiresArea: true, visibleByDefault: true },
  { key: "employees", label: "Effectif", sort: "employees", setting: "sheet_show_employees", visibleByDefault: true },
  { key: "manager", label: "Dirigeant", sort: "manager" },
  { key: "phone", label: "Téléphone", sort: "phone", visibleByDefault: true },
  { key: "email", label: "E-mail", sort: "email" },
  { key: "website", label: "Site web", sort: "website", visibleByDefault: true },
  { key: "rating", label: "Note Google", sort: "rating" },
  { key: "creation", label: "Création", sort: "creation" },
  { key: "opportunity", label: "Opportunité", sort: "opportunity", visibleByDefault: true },
  { key: "status", label: "Statut", sort: "status", visibleByDefault: true },
  { key: "follow_up", label: "Relance", sort: "follow_up", visibleByDefault: true },
  { key: "actions", fixed: true },
];
const NATURAL_SORT_DIRECTIONS = { employees: "desc", recent: "desc", rating: "desc", creation: "desc" };
const sortState = readStoredJson(SORT_STORAGE_KEY, { key: "opportunity", direction: "asc" });
const chosenColumnKeys = new Set(readStoredJson(COLUMNS_STORAGE_KEY, TABLE_COLUMNS.filter((column) => column.visibleByDefault).map((column) => column.key)));
const selectedProspectIdentifiers = new Set();
let displayedProspects = [];
let viewIsVisible = true;
let listIsStale = false;

function readStoredJson(storageKey, fallbackValue) {
  try {
    return JSON.parse(window.localStorage.getItem(storageKey) || "null") ?? fallbackValue;
  } catch {
    return fallbackValue;
  }
}

function storeJson(storageKey, value) {
  try {
    window.localStorage.setItem(storageKey, JSON.stringify(value));
  } catch {
    // Browser storage only remembers display preferences; the list works without it
  }
}

function visibleColumns() {
  return TABLE_COLUMNS.filter((column) => {
    if (column.setting && !isSectionVisible(column.setting)) return false;
    if (column.requiresArea) return isAreaFilterActive() && chosenColumnKeys.has(column.key);
    return column.fixed || chosenColumnKeys.has(column.key);
  });
}

function applySort(sort) {
  Object.assign(sortState, sort);
  storeJson(SORT_STORAGE_KEY, sortState);
}

function changeSort(sortKey) {
  if (sortState.key === sortKey) applySort({ direction: sortState.direction === "asc" ? "desc" : "asc" });
  else applySort({ key: sortKey, direction: NATURAL_SORT_DIRECTIONS[sortKey] || "asc" });
  requestProspectRefresh();
}

function readListQuery() {
  const sortKey = sortState.key === "distance" && !isAreaFilterActive() ? "opportunity" : sortState.key;
  return { ...readFilterQuery(), sort: sortKey, sort_direction: sortState.direction };
}

async function runJobRequest(path, body) {
  try {
    const job = await requestJson(path, { method: "POST", body });
    showToast(`${job.label} lancée`);
  } catch (error) {
    showToast(error.message, "error");
  }
}

function selectedProspects() {
  return displayedProspects.filter((prospect) => selectedProspectIdentifiers.has(prospect.id));
}

function clearSelection() {
  selectedProspectIdentifiers.clear();
  document.querySelectorAll(".row-checkbox").forEach((checkbox) => { checkbox.checked = false; });
  document.querySelectorAll(".prospect-table tbody tr.selected").forEach((row) => row.classList.remove("selected"));
  refreshSelectionControls();
}

async function mergeSelection() {
  const selectedNames = selectedProspects().map((prospect) => prospect.name);
  if (!window.confirm(`Fusionner ces ${selectedProspectIdentifiers.size} prospects en une seule fiche ?\n\n${selectedNames.join("\n")}\n\nLa fiche la plus ancienne est conservée et complétée par les autres (coordonnées, notes, appels, analyses).`)) return;
  try {
    const mergedProspect = await requestJson("/api/prospects/merge", { method: "POST", body: { prospect_ids: [...selectedProspectIdentifiers] } });
    clearSelection();
    showToast(`Prospects fusionnés dans « ${mergedProspect.name} ».`);
    openProspectDetail(mergedProspect.id);
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function changeSelectionStatus(statusKey) {
  const bulkResult = await requestJson("/api/prospects/bulk-update", { method: "POST", body: { prospect_ids: [...selectedProspectIdentifiers], changes: { status: statusKey } } });
  showToast(`${bulkResult.updated} prospect(s) passé(s) en « ${STATUS_LABELS[statusKey]} »`);
}

async function deleteSelection() {
  if (!window.confirm(`Supprimer définitivement ${selectedProspectIdentifiers.size} prospect(s), avec leurs analyses et leur historique d'appels ?`)) return;
  const bulkResult = await requestJson("/api/prospects/bulk-delete", { method: "POST", body: { prospect_ids: [...selectedProspectIdentifiers] } });
  clearSelection();
  showToast(`${bulkResult.deleted} prospect(s) supprimé(s)`);
}

function renderBulkBar() {
  const selectionCount = selectedProspectIdentifiers.size;
  const bulkBar = document.getElementById("bulk-bar");
  bulkBar.hidden = selectionCount === 0;
  if (!selectionCount) return;
  bulkBar.replaceChildren(...[
    createElement("strong", { text: `${selectionCount} sélectionné${selectionCount > 1 ? "s" : ""}` }),
    createElement("button", { type: "button", className: "button secondary small", text: "⚡ Analyser", onClick: () => runJobRequest("/api/scans", { prospect_ids: [...selectedProspectIdentifiers] }) }),
    createActionMenu({
      label: "Changer le statut ▾",
      className: "button secondary small",
      alignment: "start",
      items: Object.entries(STATUS_LABELS).map(([statusKey, statusLabel]) => ({ label: statusLabel, onSelect: () => changeSelectionStatus(statusKey) })),
    }),
    selectionCount >= 2 ? createElement("button", { type: "button", className: "button secondary small", text: "🔗 Fusionner", onClick: mergeSelection }) : null,
    createElement("button", { type: "button", className: "button danger small", text: "🗑️ Supprimer", onClick: deleteSelection }),
    createElement("span", { className: "spacer" }),
    createElement("button", { type: "button", className: "link-button", text: "Tout désélectionner", onClick: clearSelection }),
  ].filter(Boolean));
}

function refreshSelectionControls() {
  renderBulkBar();
  const headerCheckbox = document.getElementById("select-all-prospects");
  if (headerCheckbox) {
    const selectedDisplayedCount = selectedProspects().length;
    headerCheckbox.checked = displayedProspects.length > 0 && selectedDisplayedCount === displayedProspects.length;
    headerCheckbox.indeterminate = selectedDisplayedCount > 0 && selectedDisplayedCount < displayedProspects.length;
  }
}

function toggleProspectSelection(prospectIdentifier, isSelected, rowElement) {
  if (isSelected) selectedProspectIdentifiers.add(prospectIdentifier);
  else selectedProspectIdentifiers.delete(prospectIdentifier);
  if (rowElement) rowElement.classList.toggle("selected", isSelected);
}

function renderTableHeader() {
  const headerCells = visibleColumns().map((column) => {
    if (column.key === "selection") {
      const selectAllCheckbox = createElement("input", {
        type: "checkbox",
        id: "select-all-prospects",
        title: "Tout sélectionner",
        onChange: (changeEvent) => {
          document.querySelectorAll(".prospect-table tbody tr").forEach((rowElement) => {
            toggleProspectSelection(Number(rowElement.dataset.prospectId), changeEvent.target.checked, rowElement);
            rowElement.querySelector(".row-checkbox").checked = changeEvent.target.checked;
          });
          refreshSelectionControls();
        },
      });
      return createElement("th", { className: "selection-cell" }, selectAllCheckbox);
    }
    if (!column.sort) return createElement("th", {});
    const isActive = sortState.key === column.sort;
    return createElement("th", {
      className: `sortable ${isActive ? "active" : ""}`,
      title: "Cliquer pour trier",
      "aria-sort": isActive ? (sortState.direction === "asc" ? "ascending" : "descending") : "none",
      onClick: () => changeSort(column.sort),
    }, [column.label, createElement("span", { className: "sort-arrow", text: isActive ? (sortState.direction === "asc" ? "▲" : "▼") : "↕" })]);
  });
  document.getElementById("prospect-table-head").replaceChildren(createElement("tr", {}, headerCells));
}

function stopPropagation(clickEvent) {
  clickEvent.stopPropagation();
}

function renderProspectRow(prospect) {
  const phoneCell = prospect.phone ? createElement("a", { className: "phone-link", href: `tel:${prospect.phone.replace(/\s/g, "")}`, text: prospect.phone, onClick: stopPropagation }) : createElement("span", { className: "muted", text: "—" });
  const websiteCell = prospect.website_url
    ? createElement("a", { className: "website-link", href: prospect.website_url, target: "_blank", rel: "noopener", text: readableHost(prospect.website_url), onClick: stopPropagation })
    : createElement("a", {
      className: "search-link",
      href: `https://www.google.com/search?q=${encodeURIComponent([prospect.name, prospect.city].filter(Boolean).join(" "))}`,
      target: "_blank",
      rel: "noopener",
      text: "🔎 Chercher",
      title: "Chercher l'entreprise sur Google",
      onClick: stopPropagation,
    });
  const scanButton = createElement("button", {
    type: "button",
    className: "button ghost small",
    text: prospect.last_scan_at ? "Ré-analyser" : "Analyser",
    onClick: async (clickEvent) => {
      clickEvent.stopPropagation();
      await requestJson("/api/scans", { method: "POST", body: { prospect_ids: [prospect.id] } });
    },
  });
  const isSelected = selectedProspectIdentifiers.has(prospect.id);
  const selectionCheckbox = createElement("input", {
    type: "checkbox",
    className: "row-checkbox",
    checked: isSelected,
    "aria-label": `Sélectionner ${prospect.name}`,
    onClick: stopPropagation,
    onChange: (changeEvent) => {
      toggleProspectSelection(prospect.id, changeEvent.target.checked, changeEvent.target.closest("tr"));
      refreshSelectionControls();
    },
  });
  const mutedCell = (text) => createElement("td", { className: `secondary-cell ${text ? "" : "empty-cell"}`, text: text || "—" });
  const cellsByColumn = {
    selection: () => createElement("td", { className: "selection-cell", onClick: stopPropagation }, selectionCheckbox),
    score: () => createElement("td", { className: "score-cell" }, renderScoreBadge(prospect)),
    name: () => createElement("td", { className: "name-cell" }, [
      createElement("div", { className: "prospect-name", text: prospect.name }),
      createElement("div", { className: "prospect-meta" }, [
        chosenColumnKeys.has("sector") ? null : createElement("span", { text: prospect.category_label || "" }),
        createElement("span", { className: "source-hint", text: (prospect.sources || []).map((source) => SOURCE_LABELS[source] || source).join(" + ") }),
      ]),
    ]),
    sector: () => mutedCell(prospect.category_label),
    city: () => createElement("td", { text: prospect.city || "—" }),
    postal_code: () => mutedCell(prospect.postal_code),
    distance: () => mutedCell(prospect.distance_km === null || prospect.distance_km === undefined ? "" : `${String(prospect.distance_km).replace(".", ",")} km`),
    employees: () => mutedCell(prospect.employee_range),
    manager: () => mutedCell(prospect.manager_name),
    phone: () => createElement("td", { className: `nowrap ${prospect.phone ? "" : "empty-cell"}` }, phoneCell),
    email: () => createElement("td", { className: prospect.email ? "" : "empty-cell" }, prospect.email ? createElement("a", { href: `mailto:${prospect.email}`, text: prospect.email, onClick: stopPropagation }) : createElement("span", { className: "muted", text: "—" })),
    website: () => createElement("td", {}, websiteCell),
    rating: () => mutedCell(prospect.google_rating ? `${String(prospect.google_rating).replace(".", ",")} ★ (${prospect.google_review_count || 0})` : ""),
    creation: () => mutedCell(formatDate(prospect.creation_date)),
    opportunity: () => createElement("td", {}, prospect.opportunity_level ? createElement("span", { className: `tag ${prospect.opportunity_level}`, text: OPPORTUNITY_LABELS[prospect.opportunity_level] }) : createElement("span", { className: "tag", text: "Non analysé" })),
    status: () => createElement("td", {}, createElement("span", { className: `tag status-${prospect.status}`, text: STATUS_LABELS[prospect.status] || prospect.status })),
    follow_up: () => mutedCell(formatDate(prospect.next_follow_up)),
    actions: () => createElement("td", { className: "actions-cell" }, scanButton),
  };
  return createElement("tr", { className: isSelected ? "selected" : "", dataset: { prospectId: prospect.id }, onClick: () => openProspectDetail(prospect.id) }, visibleColumns().map((column) => cellsByColumn[column.key]()));
}

function renderStatistics(statistics) {
  const statisticCards = [
    { label: "Prospects", value: statistics.total, filter: {}, tone: "neutral" },
    { label: "Sans site web", value: statistics.by_opportunity.no_website || 0, filter: { opportunity_level: ["no_website"] }, tone: "hot" },
    { label: "Sites en mauvais état", value: statistics.by_opportunity.hot || 0, filter: { opportunity_level: ["hot"] }, tone: "hot" },
    { label: "Sites vieillissants", value: statistics.by_opportunity.warm || 0, filter: { opportunity_level: ["warm"] }, tone: "warm" },
    { label: "Non analysés", value: (statistics.by_opportunity.unscanned || 0) + (statistics.by_opportunity.unknown_website || 0), filter: { opportunity_level: ["unscanned", "unknown_website"] }, tone: "neutral" },
    { label: "Intéressés / RDV", value: (statistics.by_status.interested || 0) + (statistics.by_status.meeting || 0), filter: { status: ["interested", "meeting"] }, tone: "good" },
    { label: "Signés", value: statistics.by_status.won || 0, filter: { status: ["won"] }, tone: "good" },
  ];
  document.getElementById("statistics").replaceChildren(...statisticCards.map((statisticCard) => createElement("button", {
    type: "button",
    className: `stat-card tone-${statisticCard.tone}`,
    title: "Afficher ces prospects",
    onClick: () => resetFilters(statisticCard.filter),
  }, [
    createElement("span", { className: "stat-value", text: statisticCard.value }),
    createElement("span", { className: "stat-label", text: statisticCard.label }),
  ])));
}

async function refreshProspects() {
  const [prospects, statistics, facets] = await Promise.all([
    requestJson(`/api/prospects${buildQueryString(readListQuery())}`),
    requestJson("/api/statistics"),
    requestJson("/api/prospects/facets"),
  ]);
  setFacets(facets);
  refreshFilterBar();
  renderStatistics(statistics);
  displayedProspects = prospects;
  const existingIdentifiers = new Set(prospects.map((prospect) => prospect.id));
  [...selectedProspectIdentifiers].forEach((identifier) => { if (!existingIdentifiers.has(identifier)) selectedProspectIdentifiers.delete(identifier); });
  renderTableHeader();
  document.getElementById("prospect-rows").replaceChildren(...prospects.map(renderProspectRow));
  refreshSelectionControls();
  const databaseIsEmpty = statistics.total === 0;
  document.getElementById("prospects-empty").hidden = !databaseIsEmpty;
  document.getElementById("prospects-no-match").hidden = databaseIsEmpty || prospects.length > 0;
  document.getElementById("prospect-count").textContent = prospects.length === statistics.total
    ? `${statistics.total} prospect${statistics.total > 1 ? "s" : ""}`
    : `${prospects.length} affiché${prospects.length > 1 ? "s" : ""} sur ${statistics.total}`;
  listIsStale = false;
}

export const requestProspectRefresh = createCoalescedRefresher(refreshProspects);

function handleProspectChange() {
  if (viewIsVisible) requestProspectRefresh();
  else listIsStale = true;
}

function createColumnChooser() {
  const trigger = createElement("button", { type: "button", className: "button secondary menu-trigger", text: "▦ Colonnes" });
  return createPopover({
    trigger,
    alignment: "end",
    panelClassName: "choice-panel",
    buildContent: () => [
      createElement("div", { className: "choice-list" }, TABLE_COLUMNS.filter((column) => !column.fixed).map((column) => createElement("label", { className: "choice" }, [
        createElement("input", {
          type: "checkbox",
          checked: chosenColumnKeys.has(column.key),
          onChange: (changeEvent) => {
            if (changeEvent.target.checked) chosenColumnKeys.add(column.key);
            else chosenColumnKeys.delete(column.key);
            storeJson(COLUMNS_STORAGE_KEY, [...chosenColumnKeys]);
            requestProspectRefresh();
          },
        }),
        createElement("span", { className: "choice-label", text: column.label }),
        column.requiresArea ? createElement("span", { className: "choice-count", text: "avec un lieu" }) : null,
      ]))),
    ],
  });
}

function populateAddFormSectors() {
  const sectorSelect = document.getElementById("add-prospect-form").elements.sector_key;
  const sectorGroups = [...new Set(referenceData.sectors.map((sector) => sector.group))];
  sectorGroups.forEach((groupLabel) => sectorSelect.append(createElement("optgroup", { label: groupLabel },
    referenceData.sectors.filter((sector) => sector.group === groupLabel).map((sector) => createElement("option", { value: sector.key, text: sector.label })))));
}

function renderPageActions() {
  const addProspectForm = document.getElementById("add-prospect-form");
  document.getElementById("prospect-page-actions").replaceChildren(
    createActionMenu({
      label: "⚡ Analyser ▾",
      items: [
        { label: "Analyser les prospects non analysés", hint: "Audite chaque site qui n'a jamais été analysé", onSelect: () => runJobRequest("/api/scans", { only_unscanned: true }) },
        {
          label: "Analyser tous les prospects",
          hint: "Sites manquants, nouvelle analyse de chaque fiche, fusion des doublons",
          onSelect: () => {
            if (!window.confirm("Analyser tous les prospects ?\n\n1. Les sites manquants sont recherchés à nouveau.\n2. Toutes les fiches sont réanalysées (les corrections de diagnostic sont conservées).\n3. Les doublons révélés sont fusionnés.\n\nCela peut prendre du temps sur une grosse base.")) return;
            runJobRequest("/api/prospects/refresh-all");
          },
        },
      ],
    }),
    createActionMenu({
      label: "🧰 Outils ▾",
      items: [
        { label: "🤖 Chercher les sites manquants", hint: "Nom de domaine, moteurs de recherche, vérification", onSelect: () => runJobRequest("/api/website-discovery", { all_without_website: true }) },
        {
          label: "📞 Compléter les téléphones",
          hint: "Google Maps, 30 fiches au maximum par passage",
          onSelect: () => {
            if (!window.confirm("Chercher sur Google Maps les 30 meilleurs prospects sans téléphone ? (scraping modéré, mêmes précautions que l'onglet Google Maps)")) return;
            runJobRequest("/api/google-maps-enrichment", { all_without_phone: true, limit: 30 });
          },
        },
        { separator: true },
        {
          label: "🔗 Fusionner les doublons",
          hint: "Même SIRET, site, téléphone ou nom à la même adresse",
          onSelect: async () => {
            const mergeResult = await requestJson("/api/prospects/merge-duplicates", { method: "POST" });
            showToast(mergeResult.merged ? `${mergeResult.merged} doublon(s) fusionné(s).` : "Aucun doublon trouvé.");
          },
        },
        {
          label: "🧹 Retirer les chaînes",
          hint: "Supprime les franchises et grandes enseignes",
          danger: true,
          onSelect: async () => {
            if (!window.confirm("Supprimer tous les prospects reconnus comme chaînes ou franchises (McDonald's, Subway, Leclerc…) ?")) return;
            const removal = await requestJson("/api/prospects/remove-chains", { method: "POST" });
            showToast(removal.removed ? `${removal.removed} chaîne(s) retirée(s) : ${removal.names.slice(0, 6).join(", ")}${removal.removed > 6 ? "…" : ""}` : "Aucune chaîne trouvée.");
          },
        },
        { separator: true },
        { label: "⬇️ Exporter la liste filtrée (CSV)", onSelect: () => { window.location.href = `/api/prospects/export.csv${buildQueryString(readListQuery())}`; } },
      ],
    }),
    createElement("button", { type: "button", className: "button primary", text: "➕ Ajouter", onClick: () => { addProspectForm.hidden = !addProspectForm.hidden; } }),
  );
}

export function setProspectsViewVisibility(isVisible) {
  viewIsVisible = isVisible;
  if (isVisible && listIsStale) requestProspectRefresh();
}

export function initializeProspectsView() {
  populateAddFormSectors();
  renderPageActions();
  initializeFilterBar({
    searchInput: document.getElementById("filter-search"),
    filterContainer: document.getElementById("filter-buttons"),
    chipsContainer: document.getElementById("filter-chips"),
    viewsContainer: document.getElementById("saved-views"),
    readSort: () => ({ ...sortState }),
    applySort,
  });
  document.getElementById("column-chooser").replaceChildren(createColumnChooser());
  onFiltersChanged(requestProspectRefresh);
  onAreaPicked(() => applySort({ key: "distance", direction: "asc" }));
  const addProspectForm = document.getElementById("add-prospect-form");
  addProspectForm.addEventListener("submit", async (submitEvent) => {
    submitEvent.preventDefault();
    const formValues = Object.fromEntries(new FormData(addProspectForm).entries());
    try {
      const createdProspect = await requestJson("/api/prospects", { method: "POST", body: formValues });
      addProspectForm.reset();
      addProspectForm.hidden = true;
      openProspectDetail(createdProspect.id);
    } catch (error) {
      showToast(error.message, "error");
    }
  });
  document.getElementById("add-prospect-cancel").addEventListener("click", () => { addProspectForm.hidden = true; });
  document.getElementById("reset-filters").addEventListener("click", clearAllFilters);
  settingsEvents.addEventListener("changed", requestProspectRefresh);
  ["prospect.upserted", "prospect.updated", "prospect.deleted", "connected"].forEach((eventName) => liveEvents.addEventListener(eventName, handleProspectChange));
  requestProspectRefresh();
}
