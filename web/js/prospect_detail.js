// Prospect sheet: facts, pipeline actions, diagnosis, phone script, email and technical data.
import { requestJson } from "./api.js";
import { renderScoreBadge } from "./components.js";
import { copyToClipboard, createElement, formatDate, formatDateTime, isoDateInDays, readableHost, showToast } from "./dom.js";
import { CALL_OUTCOMES, METRIC_LABELS, OPPORTUNITY_LABELS, SEVERITY_LABELS, SOURCE_LABELS, STATUS_LABELS, WEBSITE_ORIGIN_LABELS } from "./labels.js";
import { liveEvents } from "./live.js";

const SUB_TABS = [
  { key: "diagnosis", label: "🩺 Diagnostic" },
  { key: "script", label: "📞 Script d'appel" },
  { key: "email", label: "✉️ E-mail" },
  { key: "screenshots", label: "🖼️ Captures" },
  { key: "technical", label: "🔧 Données techniques" },
  { key: "history", label: "🕘 Historique" },
];
const detailState = { prospect: null, activeSubTab: "diagnosis", renderPendingUntilBlur: false };

function drawerElement() {
  return document.getElementById("prospect-drawer");
}

function renderFact(label, value) {
  if (value === null || value === undefined || value === "") return null;
  return createElement("div", { className: "fact" }, [createElement("div", { className: "fact-label", text: label }), createElement("div", {}, value)]);
}

function renderFacts(prospect) {
  const externalLink = (url, text) => createElement("a", { href: url, target: "_blank", rel: "noopener", text });
  const websiteValue = prospect.website_url
    ? createElement("span", {}, [externalLink(prospect.website_url, readableHost(prospect.website_url)), createElement("span", { className: "muted", text: prospect.website_origin ? ` (${WEBSITE_ORIGIN_LABELS[prospect.website_origin] || prospect.website_origin})` : "" })])
    : createElement("span", { className: "muted", text: "Aucun site connu" });
  return createElement("div", { className: "fact-grid" }, [
    renderFact("Téléphone", prospect.phone ? createElement("a", { href: `tel:${prospect.phone.replace(/\s/g, "")}`, text: `📞 ${prospect.phone}` }) : null),
    renderFact("E-mail", prospect.email ? createElement("a", { href: `mailto:${prospect.email}`, text: prospect.email }) : null),
    renderFact("Site web", websiteValue),
    renderFact("Réseau social", prospect.social_url ? externalLink(prospect.social_url, readableHost(prospect.social_url)) : null),
    renderFact("Adresse", prospect.address),
    renderFact("Google Maps", prospect.google_maps_url ? externalLink(prospect.google_maps_url, `Voir la fiche${prospect.google_rating ? ` (★ ${prospect.google_rating} · ${prospect.google_review_count || 0} avis)` : ""}`) : null),
    renderFact("Raison sociale", prospect.legal_name !== prospect.name ? prospect.legal_name : null),
    renderFact("SIRET", prospect.siret ? externalLink(`https://annuaire-entreprises.data.gouv.fr/etablissement/${prospect.siret}`, prospect.siret) : null),
    renderFact("Création", formatDate(prospect.creation_date)),
    renderFact("Effectif", prospect.employee_range),
    renderFact("Sources", (prospect.sources || []).map((source) => SOURCE_LABELS[source] || source).join(", ")),
  ]);
}

async function updateProspect(changes) {
  try {
    detailState.prospect = await requestJson(`/api/prospects/${detailState.prospect.id}`, { method: "PATCH", body: changes });
    renderDetail();
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function logCall(callOutcome) {
  let nextFollowUp = callOutcome.followUpDays === null ? "" : isoDateInDays(callOutcome.followUpDays || 0);
  if (callOutcome.askDate) {
    const chosenDate = window.prompt("Date (AAAA-MM-JJ) :", isoDateInDays(callOutcome.followUpDays || 2));
    if (chosenDate === null) return;
    nextFollowUp = chosenDate;
  }
  const noteText = window.prompt("Note sur l'appel (facultatif) :", "") || "";
  detailState.prospect = await requestJson(`/api/prospects/${detailState.prospect.id}/activities`, {
    method: "POST",
    body: { kind: "call", outcome: callOutcome.outcome, content: noteText, next_follow_up: nextFollowUp },
  });
  showToast(`Appel enregistré : ${callOutcome.label}`);
  renderDetail();
}

function renderPipelineBlock(prospect) {
  const statusSelect = createElement("select", { onChange: (changeEvent) => updateProspect({ status: changeEvent.target.value }) },
    Object.entries(STATUS_LABELS).map(([statusKey, statusLabel]) => createElement("option", { value: statusKey, text: statusLabel, selected: statusKey === prospect.status })));
  const followUpInput = createElement("input", { type: "date", value: prospect.next_follow_up || "", onChange: (changeEvent) => updateProspect({ next_follow_up: changeEvent.target.value || null }) });
  const notesInput = createElement("textarea", { rows: 3, placeholder: "Notes libres…", onChange: (changeEvent) => updateProspect({ notes: changeEvent.target.value }) }, prospect.notes || "");
  return createElement("div", { className: "panel" }, [
    createElement("div", { className: "call-buttons" }, CALL_OUTCOMES.map((callOutcome) => createElement("button", { className: "button secondary small", text: callOutcome.label, onClick: () => logCall(callOutcome) }))),
    createElement("div", { className: "crm-block" }, [
      createElement("label", {}, ["Statut", statusSelect]),
      createElement("label", {}, ["Prochaine relance", followUpInput]),
    ]),
    createElement("label", {}, ["Notes", notesInput]),
  ]);
}

function renderWebsiteEditor(prospect) {
  const websiteInput = createElement("input", { type: "url", value: prospect.website_url || "", placeholder: "https://…" });
  return createElement("div", { className: "inline-fields" }, [
    websiteInput,
    createElement("button", { className: "button secondary small", text: "Corriger le site", onClick: () => updateProspect({ website_url: websiteInput.value.trim() || null }) }),
    createElement("button", {
      className: "button primary small",
      text: prospect.last_scan_at ? "🔄 Ré-analyser" : "⚡ Analyser",
      onClick: async () => {
        await requestJson("/api/scans", { method: "POST", body: { prospect_ids: [prospect.id] } });
        showToast("Analyse lancée : la fiche se mettra à jour automatiquement.");
      },
    }),
  ]);
}

function renderDiagnosis(report) {
  const problemsBySeverity = (report.problems || []).map((problem) => createElement("div", { className: `problem ${problem.severity}` }, [
    createElement("div", { className: "problem-title" }, [createElement("span", { className: `tag ${problem.severity}`, text: SEVERITY_LABELS[problem.severity] }), " ", createElement("span", { className: "tag", text: problem.category_label }), " ", problem.title]),
    createElement("div", { text: problem.impact }),
  ]));
  return [
    createElement("p", { text: report.summary }),
    createElement("h3", { text: `Ce qui ne va pas (${(report.problems || []).length})` }),
    ...problemsBySeverity,
    createElement("h3", { text: "Points à améliorer" }),
    createElement("ol", {}, (report.improvements || []).map((improvement) => createElement("li", { text: improvement }))),
  ];
}

function renderCallScript(report) {
  const scriptText = (report.call_script || []).map((section) => `${section.title}\n${section.lines.map((line) => `- ${line}`).join("\n")}`).join("\n\n");
  return [
    createElement("button", { className: "button secondary small", text: "📋 Copier le script", onClick: () => copyToClipboard(scriptText) }),
    ...(report.call_script || []).map((section) => createElement("div", { className: "script-section" }, [
      createElement("strong", { text: section.title }),
      createElement("ul", {}, section.lines.map((line) => createElement("li", { text: line }))),
    ])),
  ];
}

function renderEmail(report, prospect) {
  const email = report.email || { subject: "", body: "" };
  const mailtoLink = `mailto:${prospect.email || ""}?subject=${encodeURIComponent(email.subject)}&body=${encodeURIComponent(email.body)}`;
  return [
    createElement("div", { className: "toolbar" }, [
      createElement("button", { className: "button secondary small", text: "📋 Copier l'e-mail", onClick: () => copyToClipboard(`${email.subject}\n\n${email.body}`) }),
      createElement("a", { className: "button primary small", href: mailtoLink, text: "✉️ Ouvrir dans ma messagerie" }),
    ]),
    createElement("p", {}, [createElement("strong", { text: "Objet : " }), email.subject]),
    createElement("div", { className: "email-preview", text: email.body }),
  ];
}

function renderScreenshots(scan) {
  if (!scan || (!scan.desktop_screenshot && !scan.mobile_screenshot)) return [createElement("p", { className: "muted", text: "Aucune capture disponible." })];
  return [createElement("div", { className: "screenshots" }, [
    scan.desktop_screenshot ? createElement("a", { href: `/screenshots/${scan.desktop_screenshot}`, target: "_blank" }, createElement("img", { src: `/screenshots/${scan.desktop_screenshot}`, alt: "Capture ordinateur" })) : null,
    scan.mobile_screenshot ? createElement("a", { href: `/screenshots/${scan.mobile_screenshot}`, target: "_blank" }, createElement("img", { src: `/screenshots/${scan.mobile_screenshot}`, alt: "Capture mobile" })) : null,
  ])];
}

function formatMetricValue(metricValue) {
  if (metricValue === true) return "Oui";
  if (metricValue === false) return "Non";
  if (Array.isArray(metricValue)) return metricValue.join(", ") || "Aucun";
  if (metricValue && typeof metricValue === "object") return Object.entries(metricValue).map(([metricKey, value]) => `${metricKey} : ${value}`).join(" · ");
  return metricValue === null || metricValue === undefined ? "—" : String(metricValue);
}

function renderTechnicalData(scan) {
  if (!scan) return [createElement("p", { className: "muted", text: "Pas encore analysé." })];
  const contacts = scan.contacts || {};
  const metricRows = Object.entries(scan.metrics || {}).map(([metricKey, metricValue]) => createElement("tr", {}, [
    createElement("td", { text: METRIC_LABELS[metricKey] || metricKey }),
    createElement("td", { text: formatMetricValue(metricValue) }),
  ]));
  return [
    createElement("p", { className: "muted", text: `Analyse du ${formatDateTime(scan.scanned_at)} · rédaction : ${(scan.report || {}).generator === "rules" ? "moteur de règles" : (scan.report || {}).generator}` }),
    createElement("table", { className: "metrics-table" }, metricRows),
    createElement("h3", { text: "Coordonnées trouvées sur le site" }),
    createElement("p", { text: `Téléphones : ${formatMetricValue(contacts.phones || [])}` }),
    createElement("p", { text: `E-mails : ${formatMetricValue(contacts.emails || [])}` }),
    createElement("p", { text: `Réseaux sociaux : ${formatMetricValue(contacts.social_profiles || [])}` }),
  ];
}

function renderHistory(activities) {
  if (!activities.length) return [createElement("p", { className: "muted", text: "Aucune interaction enregistrée." })];
  const outcomeLabels = Object.fromEntries(CALL_OUTCOMES.map((callOutcome) => [callOutcome.outcome, callOutcome.label]));
  return activities.map((activity) => createElement("div", { className: "activity" }, [
    createElement("strong", { text: `${formatDateTime(activity.created_at)} · ${activity.kind === "call" ? "Appel" : activity.kind}` }),
    activity.outcome ? createElement("span", { text: ` · ${outcomeLabels[activity.outcome] || activity.outcome}` }) : null,
    activity.content ? createElement("div", { text: activity.content }) : null,
  ]));
}

function renderSubView(prospect) {
  const scan = prospect.latest_scan;
  const report = scan ? scan.report : null;
  if (detailState.activeSubTab === "history") return renderHistory(prospect.activities || []);
  if (detailState.activeSubTab === "screenshots") return renderScreenshots(scan);
  if (detailState.activeSubTab === "technical") return renderTechnicalData(scan);
  if (!report) return [createElement("p", { className: "muted", text: "Lancez l'analyse pour générer le diagnostic, le script d'appel et l'e-mail." })];
  if (detailState.activeSubTab === "script") return renderCallScript(report);
  if (detailState.activeSubTab === "email") return renderEmail(report, prospect);
  return renderDiagnosis(report);
}

function renderDetail() {
  const prospect = detailState.prospect;
  if (!prospect) return;
  const subTabButtons = SUB_TABS.map((subTab) => createElement("button", {
    className: `sub-tab ${subTab.key === detailState.activeSubTab ? "active" : ""}`,
    text: subTab.label,
    onClick: () => {
      detailState.activeSubTab = subTab.key;
      renderDetail();
    },
  }));
  document.getElementById("prospect-detail").replaceChildren(
    createElement("div", { className: "drawer-header" }, [
      renderScoreBadge(prospect, "large"),
      createElement("div", {}, [
        createElement("h2", { text: prospect.name }),
        createElement("div", { className: "muted", text: [prospect.category_label, prospect.city].filter(Boolean).join(" · ") }),
        prospect.opportunity_level ? createElement("span", { className: `tag ${prospect.opportunity_level}`, text: OPPORTUNITY_LABELS[prospect.opportunity_level] }) : null,
      ]),
      createElement("button", { className: "button ghost drawer-close", text: "✕", onClick: closeProspectDetail }),
    ]),
    renderFacts(prospect),
    renderWebsiteEditor(prospect),
    renderPipelineBlock(prospect),
    createElement("div", { className: "sub-tabs" }, subTabButtons),
    createElement("div", { className: "sub-view" }, renderSubView(prospect)),
    createElement("button", {
      className: "button ghost small",
      text: "🗑️ Supprimer ce prospect",
      onClick: async () => {
        if (!window.confirm(`Supprimer définitivement ${prospect.name} ?`)) return;
        await requestJson(`/api/prospects/${prospect.id}`, { method: "DELETE" });
        closeProspectDetail();
      },
    }),
  );
}

async function reloadOpenProspect() {
  if (!detailState.prospect) return;
  if (drawerElement().contains(document.activeElement) && ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) {
    detailState.renderPendingUntilBlur = true;
    return;
  }
  detailState.prospect = await requestJson(`/api/prospects/${detailState.prospect.id}`);
  renderDetail();
}

export async function openProspectDetail(prospectIdentifier) {
  detailState.prospect = await requestJson(`/api/prospects/${prospectIdentifier}`);
  detailState.activeSubTab = "diagnosis";
  drawerElement().hidden = false;
  document.getElementById("drawer-backdrop").hidden = false;
  renderDetail();
  drawerElement().scrollTop = 0;
}

export function closeProspectDetail() {
  detailState.prospect = null;
  drawerElement().hidden = true;
  document.getElementById("drawer-backdrop").hidden = true;
}

export function initializeProspectDetail() {
  document.getElementById("drawer-backdrop").addEventListener("click", closeProspectDetail);
  document.addEventListener("keydown", (keyboardEvent) => {
    if (keyboardEvent.key === "Escape" && detailState.prospect) closeProspectDetail();
  });
  drawerElement().addEventListener("focusout", () => {
    if (detailState.renderPendingUntilBlur) {
      detailState.renderPendingUntilBlur = false;
      reloadOpenProspect();
    }
  });
  liveEvents.addEventListener("scan.completed", (scanEvent) => {
    if (detailState.prospect && scanEvent.detail.prospect_id === detailState.prospect.id) reloadOpenProspect();
  });
  liveEvents.addEventListener("prospect.deleted", (deleteEvent) => {
    if (detailState.prospect && deleteEvent.detail.id === detailState.prospect.id) closeProspectDetail();
  });
}
