// Settings form, GPU selection and local language model controls.
import { requestJson } from "./api.js";
import { createElement, showToast } from "./dom.js";
import { liveEvents } from "./live.js";

const LLM_STATUS_LABELS = { stopped: "Arrêté", starting: "Démarrage…", running: "En marche ✅", error: "Erreur ❌", external: "Serveur externe", disabled: "Désactivé" };

function settingsForm() {
  return document.getElementById("settings-form");
}

function fillSettingsForm(settings) {
  for (const [settingKey, settingValue] of Object.entries(settings)) {
    const field = settingsForm().elements[settingKey];
    if (!field) continue;
    if (field.type === "checkbox") field.checked = Boolean(settingValue);
    else field.value = settingValue ?? "";
  }
}

function readSettingsForm() {
  const settingsChanges = {};
  for (const field of settingsForm().elements) {
    if (!field.name) continue;
    if (field.type === "checkbox") settingsChanges[field.name] = field.checked;
    else if (field.type === "number") settingsChanges[field.name] = Number(field.value);
    else settingsChanges[field.name] = field.value;
  }
  return settingsChanges;
}

function renderLanguageModelStatus(languageModelStatus) {
  const statusLines = [
    `État : ${LLM_STATUS_LABELS[languageModelStatus.status] || languageModelStatus.status}`,
    `Serveur : ${languageModelStatus.base_url}`,
    `Modèle : ${languageModelStatus.model}${languageModelStatus.installed_models ? (languageModelStatus.installed_models.some((modelName) => modelName.startsWith(languageModelStatus.model)) ? " (installé)" : " (à télécharger)") : ""}`,
    languageModelStatus.inference_device ? `Carte utilisée par Ollama : ${languageModelStatus.inference_device}` : null,
    languageModelStatus.last_error ? `Erreur : ${languageModelStatus.last_error}` : null,
    languageModelStatus.recent_log_lines && languageModelStatus.recent_log_lines.length ? `\nDerniers logs :\n${languageModelStatus.recent_log_lines.slice(-6).join("\n")}` : null,
  ];
  document.getElementById("llm-status").textContent = statusLines.filter(Boolean).join("\n");
}

async function refreshLanguageModelStatus() {
  renderLanguageModelStatus(await requestJson("/api/llm/status"));
}

async function loadSystemCapabilities(selectedGpuUuid) {
  const systemCapabilities = await requestJson("/api/system");
  document.getElementById("lighthouse-availability").textContent = systemCapabilities.lighthouse_installed ? "(installé)" : "(non installé : npm install -g lighthouse)";
  const gpuSelect = document.getElementById("gpu-select");
  const graphicsCards = systemCapabilities.graphics_cards;
  const automaticLabel = graphicsCards.length
    ? `Choix automatique (Ollama répartit sur : ${graphicsCards.map((graphicsCard) => graphicsCard.name.replace(/^NVIDIA (GeForce )?/, "")).join(" + ")})`
    : "Aucune carte NVIDIA utilisable détectée";
  gpuSelect.replaceChildren(
    createElement("option", { value: "", text: automaticLabel }),
    ...graphicsCards.map((graphicsCard, cardPosition) => createElement("option", {
      value: graphicsCard.uuid,
      selected: graphicsCard.uuid === selectedGpuUuid,
      text: [
        `Carte ${cardPosition + 1} : ${graphicsCard.name}`,
        graphicsCard.memory_total_megabytes ? `${Math.round(graphicsCard.memory_total_megabytes / 1024)} Go` : null,
        graphicsCard.memory_used_megabytes !== null ? `${graphicsCard.memory_used_megabytes} Mo utilisés` : null,
      ].filter(Boolean).join(" · "),
    })),
  );
  const ignoredCards = systemCapabilities.ignored_graphics_cards || [];
  document.getElementById("gpu-diagnosis").replaceChildren(...ignoredCards.map((ignoredCard) => createElement("div", { className: "callout warning" }, [
    createElement("strong", { text: `⚠️ ${ignoredCard.name} n'est pas utilisable : ` }),
    ignoredCard.problem,
  ])));
}

async function runLanguageModelAction(actionPath) {
  try {
    renderLanguageModelStatus(await requestJson(actionPath, { method: "POST" }));
  } catch (error) {
    showToast(error.message, "error");
  }
}

export async function initializeSettingsView() {
  const settings = await requestJson("/api/settings");
  fillSettingsForm(settings);
  await loadSystemCapabilities(settings.llm_gpu_uuid);
  settingsForm().addEventListener("submit", async (submitEvent) => {
    submitEvent.preventDefault();
    try {
      fillSettingsForm(await requestJson("/api/settings", { method: "PUT", body: readSettingsForm() }));
      showToast("Réglages enregistrés");
      refreshLanguageModelStatus();
    } catch (error) {
      showToast(error.message, "error");
    }
  });
  document.getElementById("llm-start").addEventListener("click", () => runLanguageModelAction("/api/llm/start"));
  document.getElementById("llm-stop").addEventListener("click", () => runLanguageModelAction("/api/llm/stop"));
  document.getElementById("llm-pull").addEventListener("click", async () => {
    try {
      await requestJson("/api/llm/pull", { method: "POST" });
      showToast("Téléchargement lancé : suivez la progression dans le panneau des tâches.");
    } catch (error) {
      showToast(error.message, "error");
    }
  });
  liveEvents.addEventListener("llm.status", () => refreshLanguageModelStatus());
  liveEvents.addEventListener("job.finished", (jobEvent) => {
    if (jobEvent.detail.kind === "llm_pull") refreshLanguageModelStatus();
  });
  refreshLanguageModelStatus();
}
