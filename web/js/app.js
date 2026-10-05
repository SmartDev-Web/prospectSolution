// Application bootstrap: navigation and module initialization.
import { requestJson } from "./api.js";
import { createElement, showToast } from "./dom.js";
import { requestFollowUpRefresh, initializeFollowUpsView } from "./follow_ups_view.js";
import { initializeJobsView } from "./jobs_view.js";
import { connectLiveEvents, liveEvents } from "./live.js";
import { initializeProspectDetail } from "./prospect_detail.js";
import { initializeProspectsView, setProspectsViewVisibility } from "./prospects_view.js";
import { initializeSearchViews, refreshMapLayout } from "./search_views.js";
import { initializeSettingsView } from "./settings_view.js";
import { applySettings, loadReferenceData } from "./store.js";
import { API_VERSION } from "./version.js";

const MAP_VIEWS = { "open-data": "open-data", "google-maps": "google-maps" };

function showView(viewName) {
  document.querySelectorAll("#main-tabs .tab").forEach((tabButton) => tabButton.classList.toggle("active", tabButton.dataset.view === viewName));
  document.querySelectorAll(".view").forEach((viewSection) => viewSection.classList.toggle("active", viewSection.id === `view-${viewName}`));
  setProspectsViewVisibility(viewName === "prospects");
  if (viewName === "follow-ups") requestFollowUpRefresh();
  if (MAP_VIEWS[viewName]) refreshMapLayout(MAP_VIEWS[viewName]);
  window.location.hash = viewName;
}

// The page and the server must come from the same release; a server left running during an update answers with an older contract
async function verifyServerVersion() {
  let serverVersion = null;
  try {
    serverVersion = (await requestJson("/api/health")).api_version;
  } catch {
    serverVersion = null;
  }
  const versionBanner = document.getElementById("version-banner");
  versionBanner.hidden = serverVersion === API_VERSION;
  if (serverVersion === API_VERSION) return;
  const serverIsNewer = typeof serverVersion === "number" && serverVersion > API_VERSION;
  versionBanner.replaceChildren(...[
    createElement("strong", { text: serverIsNewer ? "Une nouvelle version de l'application est installée." : "Le serveur exécute une ancienne version de l'application." }),
    createElement("span", { text: serverIsNewer ? " Rechargez la page pour l'utiliser." : " Fermez la fenêtre du serveur puis relancez start.bat : la liste et les filtres ne peuvent pas fonctionner tant que le serveur n'est pas redémarré." }),
    serverIsNewer ? createElement("button", { type: "button", className: "button secondary small", text: "Recharger", onClick: () => window.location.reload() }) : null,
  ].filter(Boolean));
}

async function startApplication() {
  initializeJobsView();
  liveEvents.addEventListener("settings.updated", (settingsEvent) => applySettings(settingsEvent.detail));
  liveEvents.addEventListener("connected", verifyServerVersion);
  connectLiveEvents();
  await loadReferenceData();
  initializeProspectDetail();
  initializeProspectsView();
  initializeFollowUpsView();
  initializeSearchViews();
  document.querySelectorAll("#main-tabs .tab").forEach((tabButton) => tabButton.addEventListener("click", () => showView(tabButton.dataset.view)));
  const requestedView = window.location.hash.replace("#", "");
  if (document.getElementById(`view-${requestedView}`)) showView(requestedView);
  await initializeSettingsView();
}

startApplication().catch((error) => showToast(`Erreur au démarrage : ${error.message}`, "error"));
