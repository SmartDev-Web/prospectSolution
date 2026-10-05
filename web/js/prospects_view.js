// Prospect list with filters, statistics and bulk actions.
import { buildQueryString, requestJson } from "./api.js";
import { createElement, formatDate, readableHost, showToast } from "./dom.js";
import { OPPORTUNITY_LABELS, STATUS_LABELS } from "./labels.js";
import { renderScoreBadge } from "./components.js";
import { liveEvents } from "./live.js";
import { openProspectDetail } from "./prospect_detail.js";
import { createCoalescedRefresher, referenceData } from "./store.js";

const FILTER_FIELDS = {
  search_text: "filter-search",
  sector_key: "filter-sector",
  opportunity_level: "filter-opportunity",
  status: "filter-status",
  website: "filter-website",
  source: "filter-source",
  sort: "filter-sort",
};
let viewIsVisible = true;
let listIsStale = false;

function readFilters() {
  return Object.fromEntries(Object.entries(FILTER_FIELDS).map(([filterName, elementIdentifier]) => [filterName, document.getElementById(elementIdentifier).value]));
}

function renderProspectRow(prospect) {
  const phoneCell = prospect.phone ? createElement("a", { href: `tel:${prospect.phone.replace(/\s/g, "")}`, text: prospect.phone, onClick: (clickEvent) => clickEvent.stopPropagation() }) : "";
  const websiteCell = prospect.website_url
    ? createElement("a", { className: "website-link", href: prospect.website_url, target: "_blank", rel: "noopener", text: readableHost(prospect.website_url), onClick: (clickEvent) => clickEvent.stopPropagation() })
    : createElement("span", { className: "muted", text: "—" });
  const scanButton = createElement("button", {
    className: "button ghost small",
    text: prospect.last_scan_at ? "Ré-analyser" : "Analyser",
    onClick: async (clickEvent) => {
      clickEvent.stopPropagation();
      await requestJson("/api/scans", { method: "POST", body: { prospect_ids: [prospect.id] } });
    },
  });
  return createElement("tr", { onClick: () => openProspectDetail(prospect.id) }, [
    createElement("td", {}, renderScoreBadge(prospect)),
    createElement("td", {}, [
      createElement("div", { className: "prospect-name", text: prospect.name }),
      createElement("div", { className: "prospect-category", text: prospect.category_label || "" }),
    ]),
    createElement("td", { text: prospect.city || "" }),
    createElement("td", {}, phoneCell),
    createElement("td", {}, websiteCell),
    createElement("td", {}, prospect.opportunity_level ? createElement("span", { className: `tag ${prospect.opportunity_level}`, text: OPPORTUNITY_LABELS[prospect.opportunity_level] }) : createElement("span", { className: "muted", text: "Non analysé" })),
    createElement("td", {}, createElement("span", { className: "tag", text: STATUS_LABELS[prospect.status] || prospect.status })),
    createElement("td", { text: formatDate(prospect.next_follow_up) }),
    createElement("td", {}, scanButton),
  ]);
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
      Object.values(FILTER_FIELDS).forEach((elementIdentifier) => {
        if (elementIdentifier !== "filter-sort") document.getElementById(elementIdentifier).value = "";
      });
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
  document.getElementById("prospect-rows").replaceChildren(...prospects.map(renderProspectRow));
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
  const sectorSelects = [document.getElementById("filter-sector"), document.getElementById("add-prospect-form").elements.sector_key];
  sectorSelects.forEach((sectorSelect) => referenceData.sectors.forEach((sector) => sectorSelect.append(createElement("option", { value: sector.key, text: sector.label }))));
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
