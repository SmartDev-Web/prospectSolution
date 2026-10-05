// Search forms (open data and Google Maps) with a shared map based area picker.
import { buildQueryString, requestJson } from "./api.js";
import { createElement, isoDateInDays, showToast } from "./dom.js";
import { referenceData } from "./store.js";

const DEFAULT_AREA = { label: "Montpellier", latitude: 43.6108, longitude: 3.8767, radius_km: 5 };
const searchAreas = {};
const areaMaps = {};

function refreshGroupState(groupElement) {
  const sectorCheckboxes = [...groupElement.querySelectorAll('input[name="sector_keys"]')];
  const checkedCount = sectorCheckboxes.filter((checkbox) => checkbox.checked).length;
  const groupCheckbox = groupElement.querySelector(".group-checkbox");
  groupCheckbox.checked = checkedCount === sectorCheckboxes.length;
  groupCheckbox.indeterminate = checkedCount > 0 && checkedCount < sectorCheckboxes.length;
  groupElement.querySelector(".group-count").textContent = checkedCount ? `${checkedCount}/${sectorCheckboxes.length}` : "";
}

function renderSectorCheckboxes(container, defaultCheckedKeys) {
  const sectorsByGroup = new Map();
  referenceData.sectors.forEach((sector) => {
    if (!sectorsByGroup.has(sector.group)) sectorsByGroup.set(sector.group, []);
    sectorsByGroup.get(sector.group).push(sector);
  });
  const filterInput = createElement("input", { type: "search", className: "sector-filter", placeholder: "Filtrer les secteurs (ex. avocat, plombier, logiciel…)" });
  const groupElements = [...sectorsByGroup.entries()].map(([groupLabel, groupSectors]) => {
    const groupCheckbox = createElement("input", { type: "checkbox", className: "group-checkbox" });
    const groupElement = createElement("details", { className: "sector-group", open: groupSectors.some((sector) => defaultCheckedKeys.includes(sector.key)) }, [
      createElement("summary", {}, [
        createElement("label", { className: "checkbox group-label", onClick: (clickEvent) => clickEvent.stopPropagation() }, [groupCheckbox, groupLabel]),
        createElement("span", { className: "group-count muted" }),
      ]),
      ...groupSectors.map((sector) => createElement("label", { className: "checkbox sector-option", dataset: { search: `${sector.label} ${sector.google_maps_queries.join(" ")}`.toLowerCase() } }, [
        createElement("input", { type: "checkbox", name: "sector_keys", value: sector.key, checked: defaultCheckedKeys.includes(sector.key) }),
        sector.label,
      ])),
    ]);
    groupCheckbox.addEventListener("change", () => {
      groupElement.querySelectorAll('input[name="sector_keys"]').forEach((checkbox) => { checkbox.checked = groupCheckbox.checked; });
      refreshGroupState(groupElement);
    });
    groupElement.addEventListener("change", (changeEvent) => {
      if (changeEvent.target.name === "sector_keys") refreshGroupState(groupElement);
    });
    refreshGroupState(groupElement);
    return groupElement;
  });
  filterInput.addEventListener("input", () => {
    const filterText = filterInput.value.trim().toLowerCase();
    groupElements.forEach((groupElement) => {
      const options = [...groupElement.querySelectorAll(".sector-option")];
      options.forEach((option) => { option.hidden = Boolean(filterText) && !option.dataset.search.includes(filterText); });
      groupElement.hidden = options.every((option) => option.hidden);
      groupElement.open = filterText ? true : Boolean(groupElement.querySelector('input[name="sector_keys"]:checked'));
    });
  });
  container.replaceChildren(filterInput, ...groupElements);
}

function updateMap(pickerKey) {
  const areaMap = areaMaps[pickerKey];
  const searchArea = searchAreas[pickerKey];
  if (!areaMap) return;
  const center = [searchArea.latitude, searchArea.longitude];
  areaMap.marker.setLatLng(center);
  areaMap.circle.setLatLng(center).setRadius(searchArea.radius_km * 1000);
  areaMap.map.fitBounds(areaMap.circle.getBounds(), { padding: [20, 20] });
}

function createMap(pickerKey, onCenterPicked) {
  const mapContainer = document.querySelector(`[data-map="${pickerKey}"]`);
  if (!window.L) {
    mapContainer.replaceChildren(createElement("p", { className: "muted", text: "Carte indisponible (pas de connexion au serveur de cartes). La recherche par adresse fonctionne quand même." }));
    return;
  }
  const searchArea = searchAreas[pickerKey];
  const map = window.L.map(mapContainer).setView([searchArea.latitude, searchArea.longitude], 12);
  window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap" }).addTo(map);
  const marker = window.L.marker([searchArea.latitude, searchArea.longitude]).addTo(map);
  const circle = window.L.circle([searchArea.latitude, searchArea.longitude], { radius: searchArea.radius_km * 1000, color: "#3b5bdb" }).addTo(map);
  map.on("click", (mapClickEvent) => onCenterPicked(mapClickEvent.latlng.lat, mapClickEvent.latlng.lng));
  areaMaps[pickerKey] = { map, marker, circle };
  updateMap(pickerKey);
}

function createAreaPicker(pickerKey) {
  searchAreas[pickerKey] = { ...DEFAULT_AREA };
  const pickerContainer = document.querySelector(`[data-area-picker="${pickerKey}"]`);
  const addressInput = createElement("input", { type: "search", value: DEFAULT_AREA.label, placeholder: "Ville ou adresse (ex. Montpellier, 34000…)", autocomplete: "off" });
  const suggestionList = createElement("div", { className: "suggestions", hidden: true });
  const radiusValue = createElement("strong", { text: `${DEFAULT_AREA.radius_km} km` });
  const radiusInput = createElement("input", { type: "range", min: 0.5, max: 50, step: 0.5, value: DEFAULT_AREA.radius_km });
  const coordinatesHint = createElement("div", { className: "muted" });
  let pendingGeocodeRequest = null;
  const refreshCoordinatesHint = () => {
    const searchArea = searchAreas[pickerKey];
    coordinatesHint.textContent = `Centre : ${searchArea.latitude.toFixed(4)}, ${searchArea.longitude.toFixed(4)} · cliquez sur la carte pour déplacer le centre`;
  };
  const setCenter = (latitude, longitude, label) => {
    Object.assign(searchAreas[pickerKey], { latitude, longitude });
    if (label !== undefined) searchAreas[pickerKey].label = label;
    refreshCoordinatesHint();
    updateMap(pickerKey);
  };
  addressInput.addEventListener("input", async () => {
    const query = addressInput.value.trim();
    if (pendingGeocodeRequest) pendingGeocodeRequest.abort();
    if (query.length < 3) {
      suggestionList.hidden = true;
      return;
    }
    pendingGeocodeRequest = new AbortController();
    try {
      const places = await requestJson(`/api/geocode${buildQueryString({ query })}`, { signal: pendingGeocodeRequest.signal });
      suggestionList.replaceChildren(...places.map((place) => createElement("button", {
        type: "button",
        text: place.label,
        onClick: () => {
          addressInput.value = place.label;
          suggestionList.hidden = true;
          setCenter(place.latitude, place.longitude, place.city || place.label);
        },
      })));
      suggestionList.hidden = places.length === 0;
    } catch (error) {
      if (error.name !== "AbortError") showToast(error.message, "error");
    }
  });
  addressInput.addEventListener("blur", (blurEvent) => {
    if (!suggestionList.contains(blurEvent.relatedTarget)) suggestionList.hidden = true;
  });
  radiusInput.addEventListener("input", () => {
    searchAreas[pickerKey].radius_km = Number(radiusInput.value);
    radiusValue.textContent = `${radiusInput.value} km`;
    updateMap(pickerKey);
  });
  pickerContainer.replaceChildren(
    createElement("label", {}, ["Centre de la recherche", addressInput]),
    suggestionList,
    createElement("label", {}, ["Rayon ", radiusValue, createElement("div", { className: "radius-row" }, radiusInput)]),
    coordinatesHint,
  );
  refreshCoordinatesHint();
  createMap(pickerKey, (latitude, longitude) => setCenter(latitude, longitude, ""));
}

function readCheckedSectors(form) {
  return [...form.querySelectorAll('input[name="sector_keys"]:checked')].map((checkbox) => checkbox.value);
}

async function submitSearch(endpointPath, requestBody, submitButton) {
  submitButton.disabled = true;
  try {
    const job = await requestJson(endpointPath, { method: "POST", body: requestBody });
    showToast(`🚀 ${job.label} : lancée. Les prospects apparaissent au fur et à mesure.`);
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    submitButton.disabled = false;
  }
}

function initializeOpenDataForm() {
  const form = document.getElementById("open-data-form");
  renderSectorCheckboxes(form.querySelector("[data-sector-checkboxes]"), ["restaurant", "butcher", "bakery"]);
  form.querySelectorAll("[data-created-after-months]").forEach((shortcutButton) => shortcutButton.addEventListener("click", () => {
    form.elements.created_after.value = isoDateInDays(-30 * Number(shortcutButton.dataset.createdAfterMonths));
  }));
  form.addEventListener("submit", (submitEvent) => {
    submitEvent.preventDefault();
    submitSearch("/api/searches/open-data", {
      area: searchAreas["open-data"],
      sector_keys: readCheckedSectors(form),
      custom_naf_codes: form.elements.custom_naf_codes.value.split(",").map((nafCode) => nafCode.trim()).filter(Boolean),
      created_after: form.elements.created_after.value || null,
      use_government_registry: form.elements.use_government_registry.checked,
      use_openstreetmap: form.elements.use_openstreetmap.checked,
      discover_websites: form.elements.discover_websites.checked,
      exclude_large_companies: form.elements.exclude_large_companies.checked,
      exclude_chains: form.elements.exclude_chains.checked,
      auto_scan: form.elements.auto_scan.checked,
      max_results: Number(form.elements.max_results.value),
    }, form.querySelector('button[type="submit"]'));
  });
}

function initializeGoogleMapsForm() {
  const form = document.getElementById("google-maps-form");
  renderSectorCheckboxes(form.querySelector("[data-sector-checkboxes]"), ["hairdresser"]);
  form.addEventListener("submit", (submitEvent) => {
    submitEvent.preventDefault();
    submitSearch("/api/searches/google-maps", {
      area: searchAreas["google-maps"],
      sector_keys: readCheckedSectors(form),
      custom_queries: form.elements.custom_queries.value.split("\n").map((query) => query.trim()).filter(Boolean),
      max_results_per_query: Number(form.elements.max_results_per_query.value),
      headless: !form.elements.visible_browser.checked,
      exclude_chains: form.elements.exclude_chains.checked,
      auto_scan: form.elements.auto_scan.checked,
    }, form.querySelector('button[type="submit"]'));
  });
}

export function initializeSearchViews() {
  createAreaPicker("open-data");
  createAreaPicker("google-maps");
  initializeOpenDataForm();
  initializeGoogleMapsForm();
}

export function refreshMapLayout(pickerKey) {
  // Leaflet measures its container once: a map created in a hidden tab must be re-measured when shown
  if (areaMaps[pickerKey]) {
    areaMaps[pickerKey].map.invalidateSize();
    updateMap(pickerKey);
  }
}
