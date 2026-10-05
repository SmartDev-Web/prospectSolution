// Shared reference data and coalesced refresh helper.
import { requestJson } from "./api.js";

export const referenceData = { sectors: [], sectorsByKey: new Map() };

export async function loadReferenceData() {
  referenceData.sectors = await requestJson("/api/sectors");
  referenceData.sectorsByKey = new Map(referenceData.sectors.map((sector) => [sector.key, sector]));
}

// Collapse bursts of change notifications into sequential refreshes: at most one running, one pending.
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
        await refreshFunction();
      } while (refreshRequestedDuringRun);
    } finally {
      refreshRunning = false;
    }
  };
}
