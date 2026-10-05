// Shared reference data and coalesced refresh helper.
import { requestJson } from "./api.js";
import { showToast } from "./dom.js";

export const referenceData = { sectors: [], sectorsByKey: new Map(), settings: {} };
// Raised whenever the settings change, so that views depending on display options re-render
export const settingsEvents = new EventTarget();

export function applySettings(settings) {
  referenceData.settings = settings;
  settingsEvents.dispatchEvent(new CustomEvent("changed", { detail: settings }));
}

export function isSectionVisible(settingKey) {
  return referenceData.settings[settingKey] !== false;
}

export async function loadReferenceData() {
  const [sectors, settings] = await Promise.all([requestJson("/api/sectors"), requestJson("/api/settings")]);
  referenceData.sectors = sectors;
  referenceData.sectorsByKey = new Map(sectors.map((sector) => [sector.key, sector]));
  referenceData.settings = settings;
}

// Collapse bursts of change notifications into sequential refreshes: at most one running, one pending.
// A failing refresh is reported to the user and leaves the refresher ready for the next notification.
export function createCoalescedRefresher(refreshFunction) {
  let refreshRunning = false;
  let refreshRequestedDuringRun = false;
  return async function requestRefresh() {
    if (refreshRunning) {
      refreshRequestedDuringRun = true;
      return;
    }
    refreshRunning = true;
    try {
      do {
        refreshRequestedDuringRun = false;
        try {
          await refreshFunction();
        } catch (error) {
          console.error(error);
          showToast(`Actualisation impossible : ${error.message}`, "error");
        }
      } while (refreshRequestedDuringRun);
    } finally {
      refreshRunning = false;
    }
  };
}
