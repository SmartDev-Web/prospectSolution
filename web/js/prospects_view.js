// Prospect list with filters, statistics and bulk actions.
import { buildQueryString, requestJson } from "./api.js";
import { createElement, formatDate, readableHost, showToast } from "./dom.js";
import { OPPORTUNITY_LABELS, SOURCE_LABELS, STATUS_LABELS } from "./labels.js";
import { renderScoreBadge } from "./components.js";
import { liveEvents } from "./live.js";
import { openProspectDetail } from "./prospect_detail.js";
import { createCoalescedRefresher, isSectionVisible, referenceData, settingsEvents } from "./store.js";

const FILTER_FIELDS = {
  search_text: "filter-search",
  sector_key: "filter-sector",
  opportunity_level: "filter-opportunity",
  status: "filter-status",
  website: "filter-website",
  source: "filter-source",
};
// Each sortable column names the server sort key; clicking a header twice reverses the order
const TABLE_COLUMNS = [
  { key: "selection" },
  { key: "score", label: "Score", sort: "score" },
  { key: "name", label: "Entreprise", sort: "name" },
  { key: "city", label: "Ville", sort: "city" },
  { key: "employees", label: "Effectif", sort: "employees", setting: "sheet_show_employees" },
  { key: "phone", label: "Téléphone", sort: "phone" },
  { key: "website", label: "Site web", sort: "website" },
  { key: "opportunity", label: "Opportunité", sort: "opportunity" },
  { key: "status", label: "Statut", sort: "status" },
  { key: "follow_up", label: "Relance", sort: "follow_up" },
  { key: "actions" },
];
const NATURAL_SORT_DIRECTIONS = { employees: "desc", recent: "desc" };
const sortState = { key: "opportunity", direction: "asc" };
const selectedProspectIdentifiers = new Set();
let displayedProspects = [];
let viewIsVisible = true;
let listIsStale = false;

function visibleColumns() {
  return TABLE_COLUMNS.filter((column) => !column.setting || isSectionVisible(column.setting));
}

function readFilters() {
  const filters = Object.fromEntries(Object.entries(FILTER_FIELDS).map(([filterName, elementIdentifier]) => [filterName, document.getElementById(elementIdentifier).value]));
  return { ...filters, sort: sortState.key, sort_direction: sortState.direction };
}

function changeSort(sortKey) {
  if (sortState.key === sortKey) sortState.direction = sortState.direction === "asc" ? "desc" : "asc";
  else Object.assign(sortState, { key: sortKey, direction: NATURAL_SORT_DIRECTIONS[sortKey] || "asc" });
  requestProspectRefresh();
}

function refreshSelectionControls() {
  const mergeButton = document.getElementById("merge-selection");
  mergeButton.hidden = selectedProspectIdentifiers.size < 2;
  mergeButton.textContent = `🔗 Fusionner la sélection (${selectedProspectIdentifiers.size})`;
  const headerCheckbox = document.getElementById("select-all-prospects");
  if (headerCheckbox) {
    const selectedDisplayedCount = displayedProspects.filter((prospect) => selectedProspectIdentifiers.has(prospect.id)).length;
    headerCheckbox.checked = displayedProspects.length > 0 && selectedDisplayedCount === displayedProspects.length;
    headerCheckbox.indeterminate = selectedDisplayedCount > 0 && selectedDisplayedCount < displayedProspects.length;
  }
}

function renderTableHeader() {
  const headerCells = visibleColumns().map((column) => {
    if (column.key === "selection") {
      const selectAllCheckbox = createElement("input", {
        type: "checkbox",
        id: "select-all-prospects",
        title: "Tout sélectionner",
        onChange: (changeEvent) => {
          displayedProspects.forEach((prospect) => {
            if (changeEvent.target.checked) selectedProspectIdentifiers.add(prospect.id);
            else selectedProspectIdentifiers.delete(prospect.id);
          });
          document.querySelectorAll(".row-checkbox").forEach((checkbox) => { checkbox.checked = changeEvent.target.checked; });
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
    }, [column.label, createElement("span", { className: "sort-arrow", text: isActive ? (sortState.direction === "asc" ? " ▲" : " ▼") : " ↕" })]);
  });
  document.getElementById("prospect-table-head").replaceChildren(createElement("tr", {}, headerCells));
}

function renderProspectRow(prospect) {
  const phoneCell = prospect.phone ? createElement("a", { href: `tel:${prospect.phone.replace(/\s/g, "")}`, text: prospect.phone, onClick: (clickEvent) => clickEvent.stopPropagation() }) : "";
  const websiteCell = prospect.website_url
    ? createElement("a", { className: "website-link", href: prospect.website_url, target: "_blank", rel: "noopener", text: readableHost(prospect.website_url), onClick: (clickEvent) => clickEvent.stopPropagation() })
    : createElement("a", {
      className: "search-link",
      href: `https://www.google.com/search?q=${encodeURIComponent([prospect.name, prospect.city].filter(Boolean).join(" "))}`,
      target: "_blank",
      rel: "noopener",
      text: "🔎 Chercher sur Google",
      onClick: (clickEvent) => clickEvent.stopPropagation(),
    });
  const scanButton = createElement("button", {
    className: "button ghost small",
    text: prospect.last_scan_at ? "Ré-analyser" : "Analyser",
    onClick: async (clickEvent) => {
      clickEvent.stopPropagation();
      await requestJson("/api/scans", { method: "POST", body: { prospect_ids: [prospect.id] } });
    },
  });
  const selectionCheckbox = createElement("input", {
    type: "checkbox",
    className: "row-checkbox",
    checked: selectedProspectIdentifiers.has(prospect.id),
    onClick: (clickEvent) => clickEvent.stopPropagation(),
    onChange: (changeEvent) => {
      if (changeEvent.target.checked) selectedProspectIdentifiers.add(prospect.id);
      else selectedProspectIdentifiers.delete(prospect.id);
      refreshSelectionControls();
    },
  });
  const cellsByColumn = {
    selection: createElement("td", { className: "selection-cell", onClick: (clickEvent) => clickEvent.stopPropagation() }, selectionCheckbox),
    score: createElement("td", {}, renderScoreBadge(prospect)),
    name: createElement("td", {}, [
      createElement("div", { className: "prospect-name", text: prospect.name }),
      createElement("div", { className: "prospect-category", text: prospect.category_label || "" }),
      createElement("div", { className: "source-hint", text: `via ${(prospect.sources || []).map((source) => SOURCE_LABELS[source] || source).join(" + ")}` }),
    ]),
    city: createElement("td", { text: prospect.city || "" }),
    employees: createElement("td", { className: "employees-cell", text: prospect.employee_range || "—" }),
    phone: createElement("td", {}, phoneCell),
    website: createElement("td", {}, websiteCell),
    opportunity: createElement("td", {}, prospect.opportunity_level ? createElement("span", { className: `tag ${prospect.opportunity_level}`, text: OPPORTUNITY_LABELS[prospect.opportunity_level] }) : createElement("span", { className: "muted", text: "Non analysé" })),
    status: createElement("td", {}, createElement("span", { className: "tag", text: STATUS_LABELS[prospect.status] || prospect.status })),
    follow_up: createElement("td", { text: formatDate(prospect.next_follow_up) }),
    actions: createElement("td", {}, scanButton),
  };
  return createElement("tr", { onClick: () => openProspectDetail(prospect.id) }, visibleColumns().map((column) => cellsByColumn[column.key]));
}

function renderStatistics(statistics) {
  const statisticCards = [
    { label: "Prospects", value: statistics.total, filter: {} },
    { label: "Sans site web 🔥🔥", value: statistics.by_opportunity.no_website || 0, filter: { "filter-opportunity": "no_website" } },
    { label: "Sites en mauvais état 🔥", value: statistics.by_opportunity.hot || 0, filter: { "filter-opportunity": "hot" } },
    { label: "Sites vieillissants", value: statistics.by_opportunity.warm || 0, filter: { "filter-opportunity": "warm" } },
    { label: "Non analysés", value: (statistics.by_opportunity.unscanned || 0) + (statistics.by_opportunity.unknown_website || 0), filter: {} },
    { label: "Intéressés / RDV", value: (statistics.by_status.interested || 0) + (statistics.by_status.meeting || 0), filter: { "filter-status": "interested" } },
    { label: "Signés 🎉", value: statistics.by_status.won || 0, filter: { "filter-status": "won" } },
  ];
  document.getElementById("statistics").replaceChildren(...statisticCards.map((statisticCard) => createElement("div", {
    className: "stat-card",
    onClick: () => {
      Object.values(FILTER_FIELDS).forEach((elementIdentifier) => { document.getElementById(elementIdentifier).value = ""; });
      Object.entries(statisticCard.filter).forEach(([elementIdentifier, filterValue]) => { document.getElementById(elementIdentifier).value = filterValue; });
      requestProspectRefresh();
    },
  }, [
    createElement("div", { className: "stat-value", text: statisticCard.value }),
    createElement("div", { className: "stat-label", text: statisticCard.label }),
  ])));
}

async function refreshProspects() {
  const [prospects, statistics] = await Promise.all([
    requestJson(`/api/prospects${buildQueryString(readFilters())}`),
    requestJson("/api/statistics"),
  ]);
  renderStatistics(statistics);
  displayedProspects = prospects;
  const existingIdentifiers = new Set(prospects.map((prospect) => prospect.id));
  [...selectedProspectIdentifiers].forEach((identifier) => { if (!existingIdentifiers.has(identifier)) selectedProspectIdentifiers.delete(identifier); });
  renderTableHeader();
  document.getElementById("prospect-rows").replaceChildren(...prospects.map(renderProspectRow));
  refreshSelectionControls();
  document.getElementById("prospects-empty").hidden = statistics.total > 0;
  document.getElementById("prospect-count").textContent = `${prospects.length} prospect${prospects.length > 1 ? "s" : ""} affiché${prospects.length > 1 ? "s" : ""}`;
  listIsStale = false;
}

export const requestProspectRefresh = createCoalescedRefresher(refreshProspects);

function handleProspectChange() {
  if (viewIsVisible) requestProspectRefresh();
  else listIsStale = true;
}

function populateFilterOptions() {
  const sectorGroups = [...new Set(referenceData.sectors.map((sector) => sector.group))];
  const sectorSelects = [document.getElementById("filter-sector"), document.getElementById("add-prospect-form").elements.sector_key];
  sectorSelects.forEach((sectorSelect) => sectorGroups.forEach((groupLabel) => sectorSelect.append(createElement("optgroup", { label: groupLabel },
    referenceData.sectors.filter((sector) => sector.group === groupLabel).map((sector) => createElement("option", { value: sector.key, text: sector.label }))))));
  document.getElementById("filter-opportunity").replaceChildren(
    createElement("option", { value: "", text: "Toutes les opportunités" }),
    ...Object.entries(OPPORTUNITY_LABELS).map(([levelKey, levelLabel]) => createElement("option", { value: levelKey, text: levelLabel })),
  );
  document.getElementById("filter-status").replaceChildren(
    createElement("option", { value: "", text: "Tous les statuts" }),
    ...Object.entries(STATUS_LABELS).map(([statusKey, statusLabel]) => createElement("option", { value: statusKey, text: statusLabel })),
  );
}

export function setProspectsViewVisibility(isVisible) {
  viewIsVisible = isVisible;
  if (isVisible && listIsStale) requestProspectRefresh();
}

export function initializeProspectsView() {
  populateFilterOptions();
  Object.values(FILTER_FIELDS).forEach((elementIdentifier) => {
    const filterElement = document.getElementById(elementIdentifier);
    filterElement.addEventListener(filterElement.tagName === "INPUT" ? "input" : "change", requestProspectRefresh);
  });
  document.getElementById("export-csv").addEventListener("click", () => {
    window.location.href = `/api/prospects/export.csv${buildQueryString(readFilters())}`;
  });
  const addProspectForm = document.getElementById("add-prospect-form");
  document.getElementById("add-prospect-toggle").addEventListener("click", () => { addProspectForm.hidden = !addProspectForm.hidden; });
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
  document.getElementById("discover-missing-websites").addEventListener("click", async () => {
    try {
      const job = await requestJson("/api/website-discovery", { method: "POST", body: { all_without_website: true } });
      showToast(`${job.label} lancée`);
    } catch (error) {
      showToast(error.message, "error");
    }
  });
  document.getElementById("enrich-phones").addEventListener("click", async () => {
    if (!window.confirm("Chercher sur Google Maps les 30 meilleurs prospects sans téléphone ? (scraping modéré, même précautions que l'onglet Google Maps)")) return;
    try {
      const job = await requestJson("/api/google-maps-enrichment", { method: "POST", body: { all_without_phone: true, limit: 30 } });
      showToast(`${job.label} lancée`);
    } catch (error) {
      showToast(error.message, "error");
    }
  });
  document.getElementById("merge-duplicates").addEventListener("click", async () => {
    const mergeResult = await requestJson("/api/prospects/merge-duplicates", { method: "POST" });
    showToast(mergeResult.merged ? `${mergeResult.merged} doublon(s) fusionné(s).` : "Aucun doublon trouvé.");
  });
  document.getElementById("merge-selection").addEventListener("click", async () => {
    const selectedNames = displayedProspects.filter((prospect) => selectedProspectIdentifiers.has(prospect.id)).map((prospect) => prospect.name);
    if (!window.confirm(`Fusionner ces ${selectedProspectIdentifiers.size} prospects en une seule fiche ?\n\n${selectedNames.join("\n")}\n\nLa fiche la plus ancienne est conservée et complétée par les autres (coordonnées, notes, appels, analyses).`)) return;
    try {
      const mergedProspect = await requestJson("/api/prospects/merge", { method: "POST", body: { prospect_ids: [...selectedProspectIdentifiers] } });
      selectedProspectIdentifiers.clear();
      showToast(`Prospects fusionnés dans « ${mergedProspect.name} ».`);
      openProspectDetail(mergedProspect.id);
    } catch (error) {
      showToast(error.message, "error");
    }
  });
  settingsEvents.addEventListener("changed", requestProspectRefresh);
  document.getElementById("remove-chains").addEventListener("click", async () => {
    if (!window.confirm("Supprimer tous les prospects reconnus comme chaînes ou franchises (McDonald's, Subway, Leclerc…) ?")) return;
    const removal = await requestJson("/api/prospects/remove-chains", { method: "POST" });
    showToast(removal.removed ? `${removal.removed} chaîne(s) retirée(s) : ${removal.names.slice(0, 6).join(", ")}${removal.removed > 6 ? "…" : ""}` : "Aucune chaîne trouvée.");
  });
  document.getElementById("refresh-all").addEventListener("click", async () => {
    if (!window.confirm("Analyser tous les prospects ?\n\n1. Les sites manquants sont recherchés à nouveau.\n2. Toutes les fiches sont réanalysées (les corrections de diagnostic sont conservées).\n3. Les doublons révélés sont fusionnés.\n\nCela peut prendre du temps sur une grosse base.")) return;
    try {
      const job = await requestJson("/api/prospects/refresh-all", { method: "POST" });
      showToast(`${job.label} lancée`);
    } catch (error) {
      showToast(error.message, "error");
    }
  });
  document.getElementById("scan-unscanned").addEventListener("click", async () => {
    try {
      const job = await requestJson("/api/scans", { method: "POST", body: { only_unscanned: true } });
      showToast(`${job.label} lancée`);
    } catch (error) {
      showToast(error.message, "error");
    }
  });
  ["prospect.upserted", "prospect.updated", "prospect.deleted", "connected"].forEach((eventName) => liveEvents.addEventListener(eventName, handleProspectChange));
  requestProspectRefresh();
}
