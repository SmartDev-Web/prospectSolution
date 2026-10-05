// Prospect list filters: single state object, filter bar, active filter chips and saved views.
import { requestJson } from "./api.js";
import { createElement, showToast } from "./dom.js";
import { OPPORTUNITY_LABELS, SOURCE_LONG_LABELS, STATUS_LABELS } from "./labels.js";
import { createMultiSelectFilter } from "./multi_select.js";
import { createPopover } from "./popover.js";
import { createPlaceAutocomplete } from "./place_autocomplete.js";
import { referenceData } from "./store.js";

const STORAGE_KEY = "prospect-list-filters";
const UNCLASSIFIED_SECTOR = "unclassified";
const UNSCANNED_OPPORTUNITY = "unscanned";
const RADIUS_PRESETS_KM = [1, 2, 5, 10, 20, 50];
const PRESENCE_LABELS = { with: "avec", without: "sans" };
const FOLLOW_UP_LABELS = { due: "En retard ou aujourd'hui", planned: "Planifiée plus tard", none: "Aucune relance" };
const EMPLOYEE_MINIMUM_OPTIONS = [1, 3, 6, 10, 20, 50, 100];
const RATING_MINIMUM_OPTIONS = [3, 3.5, 4, 4.5];
const filterEvents = new EventTarget();
let facets = { sector_key: {}, opportunity_level: {}, status: {}, source: {}, city: [] };
const refreshers = [];

function createDefaultFilterState() {
  return {
    search_text: "",
    sector_key: [],
    city: [],
    opportunity_level: [],
    status: [],
    source: [],
    website: "",
    phone: "",
    email: "",
    follow_up: "",
    score_min: "",
    score_max: "",
    employees_min: "",
    rating_min: "",
    created_after: "",
    area: { active: false, latitude: null, longitude: null, radiusKm: 5, label: "", city: "" },
  };
}

export const filterState = createDefaultFilterState();

function isScalarFilterValue(value) {
  return typeof value === "string" || typeof value === "number";
}

// Each multiple choice filter lists its options with the number of prospects behind each value
const MULTI_CHOICE_FILTERS = [
  {
    key: "sector_key",
    label: "Secteur",
    searchPlaceholder: "Restaurant, fleuriste, taxi…",
    getOptions: () => [
      ...referenceData.sectors.map((sector) => ({ value: sector.key, label: sector.label, group: sector.group, keywords: sector.google_maps_queries.join(" "), count: facets.sector_key[sector.key] || 0 })),
      { value: UNCLASSIFIED_SECTOR, label: "Non classé", group: "Autres", count: facets.sector_key[UNCLASSIFIED_SECTOR] || 0 },
    ],
  },
  {
    key: "city",
    label: "Ville",
    searchPlaceholder: "Nom de la ville…",
    getOptions: () => {
      const knownCities = facets.city.map((cityFacet) => ({ value: cityFacet.city, label: cityFacet.city, count: cityFacet.total }));
      const knownValues = new Set(knownCities.map((option) => option.value.toLowerCase()));
      return [...knownCities, ...filterState.city.filter((city) => !knownValues.has(city.toLowerCase())).map((city) => ({ value: city, label: city, count: 0 }))];
    },
  },
  {
    key: "opportunity_level",
    label: "Opportunité",
    getOptions: () => [
      ...Object.entries(OPPORTUNITY_LABELS).map(([levelKey, levelLabel]) => ({ value: levelKey, label: levelLabel, count: facets.opportunity_level[levelKey] || 0 })),
      { value: UNSCANNED_OPPORTUNITY, label: "Non analysé", count: facets.opportunity_level[UNSCANNED_OPPORTUNITY] || 0 },
    ],
  },
  {
    key: "status",
    label: "Statut",
    getOptions: () => Object.entries(STATUS_LABELS).map(([statusKey, statusLabel]) => ({ value: statusKey, label: statusLabel, count: facets.status[statusKey] || 0 })),
  },
  {
    key: "source",
    label: "Source",
    getOptions: () => Object.entries(SOURCE_LONG_LABELS).map(([sourceKey, sourceLabel]) => ({ value: sourceKey, label: sourceLabel, count: facets.source[sourceKey] || 0 })),
  },
];

// Single value criteria grouped in the "more criteria" panel, each able to describe itself as a chip
const CRITERIA_FILTERS = [
  { key: "website", label: "Site web", describe: (value) => `${PRESENCE_LABELS[value]} site` },
  { key: "phone", label: "Téléphone", describe: (value) => `${PRESENCE_LABELS[value]} téléphone` },
  { key: "email", label: "E-mail", describe: (value) => `${PRESENCE_LABELS[value]} e-mail` },
  { key: "follow_up", label: "Relance", describe: (value) => `Relance : ${FOLLOW_UP_LABELS[value].toLowerCase()}` },
  { key: "score_min", label: "Score minimum", describe: (value) => `Score ≥ ${value}` },
  { key: "score_max", label: "Score maximum", describe: (value) => `Score ≤ ${value}` },
  { key: "employees_min", label: "Effectif minimum", describe: (value) => `${value} salarié${value > 1 ? "s" : ""} ou plus` },
  { key: "rating_min", label: "Note Google minimum", describe: (value) => `Note Google ≥ ${String(value).replace(".", ",")}` },
  { key: "created_after", label: "Créée après le", describe: (value) => `Créée après le ${new Date(value).toLocaleDateString("fr-FR")}` },
];

function saveFilterState() {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(filterState));
  } catch {
    // Browser storage is a convenience only: the filters still work without it
  }
}

function restoreFilterState() {
  try {
    const storedState = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "null");
    if (storedState) applyFilterValues(storedState);
  } catch {
    // Unreadable stored filters are ignored and the defaults stay in place
  }
}

function applyFilterValues(filterValues) {
  const defaults = createDefaultFilterState();
  for (const filterKey of Object.keys(defaults)) {
    if (filterKey === "area") filterState.area = { ...defaults.area, ...(filterValues.area || {}) };
    else if (Array.isArray(defaults[filterKey])) filterState[filterKey] = Array.isArray(filterValues[filterKey]) ? filterValues[filterKey].filter(isScalarFilterValue).map(String) : [];
    else filterState[filterKey] = isScalarFilterValue(filterValues[filterKey]) ? String(filterValues[filterKey]) : defaults[filterKey];
  }
}

function publishFilterChange() {
  saveFilterState();
  refreshers.forEach((refresh) => refresh());
  filterEvents.dispatchEvent(new Event("changed"));
}

export function onFiltersChanged(listener) {
  filterEvents.addEventListener("changed", listener);
}

export function updateFilters(changes) {
  Object.assign(filterState, changes);
  publishFilterChange();
}

export function resetFilters(changes = {}) {
  applyFilterValues({ ...createDefaultFilterState(), search_text: filterState.search_text, area: filterState.area, ...changes });
  publishFilterChange();
}

export function clearAllFilters() {
  applyFilterValues({ ...createDefaultFilterState(), area: { ...createDefaultFilterState().area, radiusKm: filterState.area.radiusKm } });
  publishFilterChange();
}

export function isAreaFilterActive() {
  return filterState.area.active;
}

export function readFilterQuery() {
  const { area, ...simpleFilters } = filterState;
  const areaQuery = area.active ? { center_latitude: area.latitude, center_longitude: area.longitude, radius_km: area.radiusKm, area_city: area.city } : {};
  return { ...simpleFilters, ...areaQuery };
}

export function setFacets(updatedFacets) {
  facets = updatedFacets;
}

function listActiveFilterChips() {
  const chips = [];
  if (filterState.area.active) {
    chips.push({ label: `📍 ${filterState.area.label} · ${String(filterState.area.radiusKm).replace(".", ",")} km`, clear: () => updateFilters({ area: { ...createDefaultFilterState().area, radiusKm: filterState.area.radiusKm } }) });
  }
  MULTI_CHOICE_FILTERS.forEach((filterDefinition) => {
    const selectedValues = filterState[filterDefinition.key];
    if (!selectedValues.length) return;
    const optionLabels = new Map(filterDefinition.getOptions().map((option) => [option.value, option.label]));
    chips.push({ label: `${filterDefinition.label} : ${selectedValues.map((value) => optionLabels.get(value) || value).join(", ")}`, clear: () => updateFilters({ [filterDefinition.key]: [] }) });
  });
  CRITERIA_FILTERS.forEach((criterion) => {
    if (filterState[criterion.key] !== "" && filterState[criterion.key] !== null) {
      const description = criterion.describe(filterState[criterion.key]);
      chips.push({ label: description.charAt(0).toUpperCase() + description.slice(1), clear: () => updateFilters({ [criterion.key]: "" }) });
    }
  });
  return chips;
}

function renderActiveFilterChips(chipsContainer) {
  const chips = listActiveFilterChips();
  chipsContainer.hidden = chips.length === 0;
  chipsContainer.replaceChildren(
    ...chips.map((chip) => createElement("span", { className: "filter-chip" }, [
      createElement("span", { text: chip.label }),
      createElement("button", { type: "button", className: "filter-chip-remove", title: "Retirer ce filtre", "aria-label": `Retirer le filtre ${chip.label}`, text: "✕", onClick: chip.clear }),
    ])),
    ...(chips.length > 1 ? [createElement("button", { type: "button", className: "link-button", text: "Tout effacer", onClick: clearAllFilters })] : []),
  );
}

function buildSegmentedControl(filterKey, choices) {
  return createElement("div", { className: "segmented" }, choices.map(([choiceValue, choiceLabel]) => createElement("button", {
    type: "button",
    className: `segment ${filterState[filterKey] === choiceValue ? "active" : ""}`,
    text: choiceLabel,
    onClick: (clickEvent) => {
      updateFilters({ [filterKey]: choiceValue });
      clickEvent.currentTarget.parentElement.querySelectorAll(".segment").forEach((segment) => segment.classList.toggle("active", segment === clickEvent.currentTarget));
    },
  })));
}

function buildSelectControl(filterKey, choices, emptyLabel) {
  return createElement("select", { onChange: (changeEvent) => updateFilters({ [filterKey]: changeEvent.target.value }) }, [
    createElement("option", { value: "", text: emptyLabel }),
    ...choices.map(([choiceValue, choiceLabel]) => createElement("option", { value: choiceValue, text: choiceLabel, selected: String(filterState[filterKey]) === String(choiceValue) })),
  ]);
}

function buildNumberControl(filterKey, placeholder) {
  return createElement("input", {
    type: "number",
    min: 0,
    max: 100,
    placeholder,
    value: filterState[filterKey],
    onChange: (changeEvent) => updateFilters({ [filterKey]: changeEvent.target.value }),
  });
}

function buildCriteriaPanel() {
  const presenceChoices = [["", "Indifférent"], ["with", "Avec"], ["without", "Sans"]];
  const criteriaRow = (rowLabel, control) => createElement("div", { className: "criteria-row" }, [createElement("span", { className: "criteria-label", text: rowLabel }), control]);
  return [
    criteriaRow("Site web", buildSegmentedControl("website", presenceChoices)),
    criteriaRow("Téléphone", buildSegmentedControl("phone", presenceChoices)),
    criteriaRow("E-mail", buildSegmentedControl("email", presenceChoices)),
    criteriaRow("Score du site", createElement("div", { className: "range-inputs" }, [buildNumberControl("score_min", "min"), createElement("span", { text: "à" }), buildNumberControl("score_max", "max")])),
    criteriaRow("Effectif", buildSelectControl("employees_min", EMPLOYEE_MINIMUM_OPTIONS.map((minimum) => [minimum, `${minimum} salarié${minimum > 1 ? "s" : ""} ou plus`]), "Indifférent")),
    criteriaRow("Note Google", buildSelectControl("rating_min", RATING_MINIMUM_OPTIONS.map((minimum) => [minimum, `${String(minimum).replace(".", ",")} ★ ou plus`]), "Indifférente")),
    criteriaRow("Relance", buildSelectControl("follow_up", Object.entries(FOLLOW_UP_LABELS), "Indifférente")),
    criteriaRow("Créée après le", createElement("input", { type: "date", value: filterState.created_after, onChange: (changeEvent) => updateFilters({ created_after: changeEvent.target.value }) })),
  ];
}

function createCriteriaButton() {
  const trigger = createElement("button", { type: "button", className: "filter-button" });
  const describeCriteria = () => {
    const activeCount = CRITERIA_FILTERS.filter((criterion) => filterState[criterion.key] !== "").length;
    trigger.classList.toggle("active", activeCount > 0);
    trigger.replaceChildren(...[
      createElement("span", { className: "filter-button-label", text: "Plus de critères" }),
      activeCount ? createElement("span", { className: "filter-button-value", text: activeCount }) : null,
      createElement("span", { className: "filter-button-caret", text: "▾" }),
    ].filter(Boolean));
  };
  refreshers.push(describeCriteria);
  describeCriteria();
  return createPopover({ trigger, buildContent: buildCriteriaPanel, panelClassName: "criteria-panel" });
}

function createAreaButton() {
  const trigger = createElement("button", { type: "button", className: "filter-button" });
  const describeArea = () => {
    trigger.classList.toggle("active", filterState.area.active);
    trigger.replaceChildren(...[
      createElement("span", { className: "filter-button-label", text: "📍 Autour de" }),
      filterState.area.active ? createElement("span", { className: "filter-button-value", text: `${filterState.area.city || filterState.area.label} · ${String(filterState.area.radiusKm).replace(".", ",")} km` }) : null,
      createElement("span", { className: "filter-button-caret", text: "▾" }),
    ].filter(Boolean));
  };
  refreshers.push(describeArea);
  describeArea();
  const changeRadius = (radiusKm) => updateFilters({ area: { ...filterState.area, radiusKm: Math.min(200, Math.max(0.5, Number(radiusKm) || 5)) } });
  return createPopover({
    trigger,
    panelClassName: "area-panel",
    buildContent: (closePopover) => {
      const { input, suggestionList } = createPlaceAutocomplete({
        initialValue: filterState.area.label,
        placeholder: "Ville ou adresse…",
        onPick: (place) => {
          filterEvents.dispatchEvent(new Event("area-picked"));
          updateFilters({ area: { ...filterState.area, active: true, latitude: place.latitude, longitude: place.longitude, label: place.label, city: place.city || "" } });
          closePopover();
        },
      });
      const radiusInput = createElement("input", { type: "number", min: 0.5, max: 200, step: 0.5, value: filterState.area.radiusKm, onChange: (changeEvent) => changeRadius(changeEvent.target.value) });
      return [
        createElement("div", { className: "autocomplete" }, [input, suggestionList]),
        createElement("div", { className: "criteria-label", text: "Rayon" }),
        createElement("div", { className: "radius-presets" }, [
          ...RADIUS_PRESETS_KM.map((radiusKm) => createElement("button", {
            type: "button",
            className: `segment ${filterState.area.radiusKm === radiusKm ? "active" : ""}`,
            text: `${radiusKm} km`,
            onClick: (clickEvent) => {
              radiusInput.value = radiusKm;
              changeRadius(radiusKm);
              clickEvent.currentTarget.parentElement.querySelectorAll(".segment").forEach((segment) => segment.classList.toggle("active", segment === clickEvent.currentTarget));
            },
          })),
          createElement("label", { className: "radius-custom" }, [radiusInput, " km"]),
        ]),
        filterState.area.active ? createElement("button", {
          type: "button",
          className: "link-button",
          text: "Retirer le filtre de lieu",
          onClick: () => {
            updateFilters({ area: { ...createDefaultFilterState().area, radiusKm: filterState.area.radiusKm } });
            closePopover();
          },
        }) : null,
      ];
    },
  });
}

function savedViews() {
  return referenceData.settings.saved_prospect_views || [];
}

async function storeSavedViews(views) {
  try {
    await requestJson("/api/settings", { method: "PUT", body: { saved_prospect_views: views } });
  } catch (error) {
    showToast(error.message, "error");
  }
}

function createSavedViewsMenu(readSort, applySort) {
  const trigger = createElement("button", { type: "button", className: "button secondary menu-trigger", text: "⭐ Vues" });
  return createPopover({
    trigger,
    alignment: "end",
    panelClassName: "menu-panel views-panel",
    buildContent: (closePopover) => [
      ...(savedViews().length ? savedViews().map((savedView, viewPosition) => createElement("div", { className: "saved-view" }, [
        createElement("button", {
          type: "button",
          className: "menu-item",
          text: savedView.name,
          onClick: () => {
            closePopover();
            applyFilterValues(savedView.filters);
            if (savedView.sort) applySort(savedView.sort);
            publishFilterChange();
          },
        }),
        createElement("button", {
          type: "button",
          className: "filter-chip-remove",
          title: "Supprimer cette vue",
          text: "✕",
          onClick: () => {
            closePopover();
            if (window.confirm(`Supprimer la vue « ${savedView.name} » ?`)) storeSavedViews(savedViews().filter((_view, position) => position !== viewPosition));
          },
        }),
      ])) : [createElement("p", { className: "menu-empty", text: "Aucune vue enregistrée. Réglez vos filtres puis enregistrez-les pour les retrouver en un clic." })]),
      createElement("div", { className: "menu-separator" }),
      createElement("button", {
        type: "button",
        className: "menu-item",
        text: "💾 Enregistrer les filtres actuels…",
        onClick: () => {
          closePopover();
          const viewName = (window.prompt("Nom de la vue (ex. « Restaurants sans site à Lattes ») :") || "").trim();
          if (!viewName) return;
          const otherViews = savedViews().filter((savedView) => savedView.name !== viewName);
          storeSavedViews([...otherViews, { name: viewName, filters: JSON.parse(JSON.stringify(filterState)), sort: readSort() }]);
          showToast(`Vue « ${viewName} » enregistrée`);
        },
      }),
    ],
  });
}

export function initializeFilterBar({ searchInput, filterContainer, chipsContainer, viewsContainer, readSort, applySort }) {
  restoreFilterState();
  searchInput.value = filterState.search_text;
  searchInput.addEventListener("input", () => updateFilters({ search_text: searchInput.value.trim() }));
  const multiChoiceButtons = MULTI_CHOICE_FILTERS.map((filterDefinition) => {
    const multiSelect = createMultiSelectFilter({
      label: filterDefinition.label,
      searchPlaceholder: filterDefinition.searchPlaceholder,
      getOptions: filterDefinition.getOptions,
      getSelectedValues: () => filterState[filterDefinition.key],
      onChange: (selectedValues) => updateFilters({ [filterDefinition.key]: selectedValues }),
    });
    refreshers.push(multiSelect.refresh);
    return multiSelect.element;
  });
  filterContainer.replaceChildren(createAreaButton(), ...multiChoiceButtons, createCriteriaButton());
  viewsContainer.replaceChildren(createSavedViewsMenu(readSort, applySort));
  refreshers.push(() => renderActiveFilterChips(chipsContainer));
  refreshers.push(() => { if (searchInput.value.trim() !== filterState.search_text) searchInput.value = filterState.search_text; });
  refreshers.forEach((refresh) => refresh());
}

export function refreshFilterBar() {
  refreshers.forEach((refresh) => refresh());
}

export function onAreaPicked(listener) {
  filterEvents.addEventListener("area-picked", listener);
}
