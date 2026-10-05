// Application bootstrap: navigation and module initialization.
import { showToast } from "./dom.js";
import { requestFollowUpRefresh, initializeFollowUpsView } from "./follow_ups_view.js";
import { initializeJobsView } from "./jobs_view.js";
import { connectLiveEvents } from "./live.js";
import { initializeProspectDetail } from "./prospect_detail.js";
import { initializeProspectsView, setProspectsViewVisibility } from "./prospects_view.js";
import { initializeSearchViews, refreshMapLayout } from "./search_views.js";
import { initializeSettingsView } from "./settings_view.js";
import { loadReferenceData } from "./store.js";

const MAP_VIEWS = { "open-data": "open-data", "google-maps": "google-maps" };

function showView(viewName) {
  document.querySelectorAll("#main-tabs .tab").forEach((tabButton) => tabButton.classList.toggle("active", tabButton.dataset.view === viewName));
  document.querySelectorAll(".view").forEach((viewSection) => viewSection.classList.toggle("active", viewSection.id === `view-${viewName}`));
  setProspectsViewVisibility(viewName === "prospects");
  if (viewName === "follow-ups") requestFollowUpRefresh();
  if (MAP_VIEWS[viewName]) refreshMapLayout(MAP_VIEWS[viewName]);
  window.location.hash = viewName;
}

async function startApplication() {
  initializeJobsView();
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
