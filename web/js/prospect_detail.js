// Prospect sheet: quick actions, origin, website verification, pipeline, synthesis, diagnosis, script, email and technical data.
import { requestJson } from "./api.js";
import { renderScoreBadge } from "./components.js";
import { copyToClipboard, createElement, formatDate, formatDateTime, isoDateInDays, readableHost, showToast } from "./dom.js";
import {
  CALL_OUTCOMES,
  CONFIDENCE_LABELS,
  METRIC_LABELS,
  OPPORTUNITY_LABELS,
  SEVERITY_LABELS,
  SOURCE_LONG_LABELS,
  STATUS_LABELS,
  WEBSITE_ORIGIN_LABELS,
} from "./labels.js";
import { liveEvents } from "./live.js";
import { isSectionVisible, settingsEvents } from "./store.js";

// Each tab can be hidden from the settings, to keep the sheet focused on what the user works with
const SUB_TABS = [
  { key: "synthesis", label: "🎯 Synthèse", setting: "sheet_show_synthesis" },
  { key: "diagnosis", label: "🩺 Diagnostic", setting: "sheet_show_diagnosis" },
  { key: "script", label: "📞 Script d'appel", setting: "sheet_show_script" },
  { key: "email", label: "✉️ E-mail", setting: "sheet_show_email" },
  { key: "technical", label: "🔧 Technique", setting: "sheet_show_technical" },
  { key: "history", label: "🕘 Historique", setting: "sheet_show_history" },
];

function visibleSubTabs() {
  return SUB_TABS.filter((subTab) => isSectionVisible(subTab.setting));
}
const detailState = { prospect: null, activeSubTab: "synthesis", renderPendingUntilBlur: false };

function drawerElement() {
  return document.getElementById("prospect-drawer");
}

function externalLink(url, text, className = "") {
  return createElement("a", { href: url, target: "_blank", rel: "noopener", text, className });
}

function googleSearchUrl(prospect) {
  const searchTerms = [prospect.name, prospect.city || prospect.postal_code].filter(Boolean).join(" ");
  return `https://www.google.com/search?q=${encodeURIComponent(searchTerms)}`;
}

function googleMapsUrl(prospect) {
  if (prospect.google_maps_url) return prospect.google_maps_url;
  const searchTerms = [prospect.name, prospect.address || prospect.city].filter(Boolean).join(" ");
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(searchTerms)}`;
}

function officialRegistryUrl(prospect) {
  if (prospect.siret) return `https://annuaire-entreprises.data.gouv.fr/etablissement/${prospect.siret}`;
  return `https://annuaire-entreprises.data.gouv.fr/rechercher?terme=${encodeURIComponent(prospect.legal_name || prospect.name)}`;
}

// Actions answering with the prospect refresh the sheet; actions starting a job leave it to live events
async function runProspectAction(actionPromise, successMessage, answersWithProspect = true) {
  try {
    const actionResult = await actionPromise;
    if (answersWithProspect && actionResult) detailState.prospect = actionResult;
    if (successMessage) showToast(successMessage);
    renderDetail();
  } catch (error) {
    showToast(error.message, "error");
  }
}

function updateProspect(changes) {
  return runProspectAction(requestJson(`/api/prospects/${detailState.prospect.id}`, { method: "PATCH", body: changes }));
}

function startScan(prospect) {
  return runProspectAction(requestJson("/api/scans", { method: "POST", body: { prospect_ids: [prospect.id] } }), "Analyse lancée : la fiche se mettra à jour automatiquement.", false);
}

async function markAsChain(prospect) {
  const suggestedBrand = prospect.name.replace(/\s+(saint|st|ste|le|la|les|de|du)\b.*$/i, "").trim() || prospect.name;
  const brand = window.prompt("Nom de l'enseigne à exclure (tous les prospects qui la contiennent seront supprimés) :", suggestedBrand);
  if (!brand || brand.trim().length < 2) return;
  try {
    const result = await requestJson(`/api/prospects/${prospect.id}/mark-chain`, { method: "POST", body: { brand: brand.trim() } });
    closeProspectDetail();
    showToast(`« ${result.brand} » ajoutée aux chaînes : ${result.removed} prospect(s) retiré(s).`);
  } catch (error) {
    showToast(error.message, "error");
  }
}

function renderActionBar(prospect) {
  const actionLinks = [
    prospect.phone ? createElement("a", { className: "button primary small", href: `tel:${prospect.phone.replace(/\s/g, "")}`, text: `📞 ${prospect.phone}` }) : null,
    prospect.phone ? createElement("button", { className: "button secondary small", text: "📋 Copier le numéro", onClick: () => copyToClipboard(prospect.phone) }) : null,
    externalLink(googleSearchUrl(prospect), "🔎 Rechercher sur Google", "button secondary small"),
    externalLink(googleMapsUrl(prospect), prospect.google_maps_url ? "🗺️ Fiche Google Maps" : "🗺️ Chercher sur Maps", "button secondary small"),
    prospect.website_url ? externalLink(prospect.website_url, "🌐 Ouvrir le site", "button secondary small") : null,
    externalLink(officialRegistryUrl(prospect), "🏛️ Fiche officielle", "button secondary small"),
    createElement("button", {
      className: "button secondary small",
      text: "🏬 C'est une chaîne",
      title: "Classe ce prospect comme chaîne ou franchise : il est supprimé, ainsi que tous ceux de la même enseigne, et l'enseigne sera ignorée aux prochaines recherches",
      onClick: () => markAsChain(prospect),
    }),
    (prospect.sources || []).includes("google_maps") ? null : createElement("button", {
      className: "button secondary small",
      text: prospect.google_maps_checked ? "🗺️ Recompléter via Google Maps" : "🗺️ Compléter via Google Maps",
      title: "Cherche la fiche Google Maps de l'entreprise pour récupérer téléphone, site, note et avis",
      onClick: () => runProspectAction(requestJson("/api/google-maps-enrichment", { method: "POST", body: { prospect_ids: [prospect.id] } }), "Recherche sur Google Maps lancée.", false),
    }),
  ];
  return createElement("div", { className: "action-bar" }, actionLinks);
}

function renderOrigin(prospect) {
  const [creationSource, ...enrichmentSources] = prospect.sources || [];
  return createElement("div", { className: "origin-line" }, [
    createElement("span", { className: "origin-badge", text: `Fiche créée depuis : ${SOURCE_LONG_LABELS[creationSource] || creationSource || "inconnu"}` }),
    enrichmentSources.length ? createElement("span", { className: "muted", text: ` · complétée par : ${enrichmentSources.map((source) => SOURCE_LONG_LABELS[source] || source).join(", ")}` }) : null,
    createElement("span", { className: "muted", text: ` · ajoutée le ${formatDate(prospect.created_at)}` }),
  ]);
}

function renderWebsiteBlock(prospect) {
  const websiteInput = createElement("input", { type: "url", value: prospect.website_url || "", placeholder: "Coller l'adresse du site (https://…)" });
  const editorRow = createElement("div", { className: "inline-fields" }, [
    websiteInput,
    createElement("button", { className: "button secondary small", text: prospect.website_url ? "Corriger" : "Enregistrer", onClick: () => updateProspect({ website_url: websiteInput.value.trim() || null }) }),
  ]);
  if (!prospect.website_url) {
    return createElement("div", { className: "panel website-block" }, [
      createElement("div", { className: "website-title" }, [createElement("strong", { text: "🌐 Aucun site connu" }), prospect.website_check_done ? createElement("span", { className: "muted", text: " · la recherche automatique n'a rien trouvé de fiable" }) : null]),
      createElement("div", { className: "action-bar" }, [
        externalLink(googleSearchUrl(prospect), "🔎 Vérifier sur Google", "button secondary small"),
        createElement("button", {
          className: "button secondary small",
          text: "🤖 Relancer la recherche automatique",
          onClick: () => runProspectAction(requestJson("/api/website-discovery", { method: "POST", body: { prospect_ids: [prospect.id] } }), "Recherche du site lancée.", false),
        }),
        createElement("button", { className: "button primary small", text: "⚡ Générer la fiche « sans site »", onClick: () => startScan(prospect) }),
      ]),
      editorRow,
    ]);
  }
  const confidence = CONFIDENCE_LABELS[prospect.website_confidence];
  return createElement("div", { className: "panel website-block" }, [
    createElement("div", { className: "website-title" }, [
      createElement("strong", {}, ["🌐 ", externalLink(prospect.website_url, readableHost(prospect.website_url))]),
      confidence ? createElement("span", { className: `confidence ${confidence.className}`, text: confidence.label }) : null,
      createElement("span", { className: "muted", text: ` · ${WEBSITE_ORIGIN_LABELS[prospect.website_origin] || prospect.website_origin || "source inconnue"}` }),
    ]),
    prospect.website_evidence ? createElement("div", { className: "muted small-text", text: `Preuves : ${prospect.website_evidence}` }) : null,
    createElement("div", { className: "action-bar" }, [
      createElement("button", { className: "button primary small", text: prospect.last_scan_at ? "🔄 Ré-analyser" : "⚡ Analyser le site", onClick: () => startScan(prospect) }),
      createElement("button", {
        className: "button secondary small",
        text: "❌ Ce n'est pas le bon site",
        onClick: () => runProspectAction(requestJson(`/api/prospects/${prospect.id}/reject-website`, { method: "POST" }), "Site écarté : il ne sera plus proposé pour ce prospect."),
      }),
    ]),
    editorRow,
  ]);
}

function renderFact(label, value) {
  if (value === null || value === undefined || value === "") return null;
  return createElement("div", { className: "fact" }, [createElement("div", { className: "fact-label", text: label }), createElement("div", {}, value)]);
}

function renderFactSection(title, facts) {
  const presentFacts = facts.filter(Boolean);
  if (!presentFacts.length) return null;
  return createElement("div", { className: "fact-section" }, [createElement("h3", { text: title }), createElement("div", { className: "fact-grid" }, presentFacts)]);
}

function renderContacts(prospect) {
  if (!isSectionVisible("sheet_show_contacts")) return null;
  return renderFactSection("📇 Coordonnées", [
    renderFact("Téléphone", prospect.phone ? createElement("a", { href: `tel:${prospect.phone.replace(/\s/g, "")}`, text: prospect.phone }) : createElement("span", { className: "muted", text: "Non renseigné" })),
    renderFact("E-mail", prospect.email ? createElement("a", { href: `mailto:${prospect.email}`, text: prospect.email }) : createElement("span", { className: "muted", text: "Non renseigné" })),
    renderFact("Adresse", prospect.address || [prospect.postal_code, prospect.city].filter(Boolean).join(" ")),
    renderFact("Site web", prospect.website_url ? externalLink(prospect.website_url, readableHost(prospect.website_url)) : createElement("span", { className: "muted", text: "Aucun site détecté" })),
    renderFact("Réseau social", prospect.social_url ? externalLink(prospect.social_url, readableHost(prospect.social_url)) : null),
  ]);
}

function renderCompanyFacts(prospect) {
  return renderFactSection("🏢 Entreprise", [
    renderFact("Dirigeant", prospect.manager_name ? `👤 ${prospect.manager_name}` : null),
    isSectionVisible("sheet_show_employees") ? renderFact("Effectif recensé", prospect.employee_range || createElement("span", { className: "muted", text: "Non communiqué" })) : null,
    renderFact("Avis Google", prospect.google_rating ? `★ ${String(prospect.google_rating).replace(".", ",")} (${prospect.google_review_count || 0} avis)` : null),
    renderFact("Raison sociale", prospect.legal_name !== prospect.name ? prospect.legal_name : null),
    renderFact("SIRET", prospect.siret),
    renderFact("Création", formatDate(prospect.creation_date)),
  ]);
}

async function logCall(callOutcome) {
  let nextFollowUp = callOutcome.followUpDays === null ? "" : isoDateInDays(callOutcome.followUpDays || 0);
  if (callOutcome.askDate) {
    const chosenDate = window.prompt("Date (AAAA-MM-JJ) :", isoDateInDays(callOutcome.followUpDays || 2));
    if (chosenDate === null) return;
    nextFollowUp = chosenDate;
  }
  const noteText = window.prompt("Note sur l'appel (facultatif) :", "") || "";
  await runProspectAction(requestJson(`/api/prospects/${detailState.prospect.id}/activities`, {
    method: "POST",
    body: { kind: "call", outcome: callOutcome.outcome, content: noteText, next_follow_up: nextFollowUp },
  }), `Appel enregistré : ${callOutcome.label}`);
}

function renderPipelineBlock(prospect) {
  const statusSelect = createElement("select", { onChange: (changeEvent) => updateProspect({ status: changeEvent.target.value }) },
    Object.entries(STATUS_LABELS).map(([statusKey, statusLabel]) => createElement("option", { value: statusKey, text: statusLabel, selected: statusKey === prospect.status })));
  const followUpInput = createElement("input", { type: "date", value: prospect.next_follow_up || "", onChange: (changeEvent) => updateProspect({ next_follow_up: changeEvent.target.value || null }) });
  const notesInput = createElement("textarea", { rows: 2, placeholder: "Notes libres…", onChange: (changeEvent) => updateProspect({ notes: changeEvent.target.value }) }, prospect.notes || "");
  return createElement("div", { className: "panel" }, [
    createElement("div", { className: "call-buttons" }, CALL_OUTCOMES.map((callOutcome) => createElement("button", { className: "button secondary small", text: callOutcome.label, onClick: () => logCall(callOutcome) }))),
    createElement("div", { className: "crm-block" }, [
      createElement("label", {}, ["Statut", statusSelect]),
      createElement("label", {}, ["Prochaine relance", followUpInput]),
    ]),
    createElement("label", {}, ["Notes", notesInput]),
  ]);
}

function renderScoreBreakdown(scoreBreakdown) {
  if (!scoreBreakdown) return null;
  return createElement("div", { className: "score-breakdown" }, Object.values(scoreBreakdown).map((bucket) => {
    if (bucket.measured === false) {
      return createElement("div", { className: "breakdown-row" }, [
        createElement("span", { className: "breakdown-label", text: bucket.label }),
        createElement("span", { className: "muted small-text", text: "non mesuré (page non affichée)" }),
        createElement("span", { className: "breakdown-value", text: "—" }),
      ]);
    }
    const ratio = bucket.weight ? bucket.score / bucket.weight : 0;
    const level = ratio >= 0.75 ? "good" : ratio >= 0.4 ? "average" : "bad";
    return createElement("div", { className: "breakdown-row" }, [
      createElement("span", { className: "breakdown-label", text: bucket.label }),
      createElement("div", { className: "breakdown-track" }, createElement("div", { className: `breakdown-bar ${level}`, style: `width: ${Math.round(ratio * 100)}%` })),
      createElement("span", { className: "breakdown-value", text: `${Math.round(bucket.score)}/${bucket.weight}` }),
    ]);
  }));
}

function renderScreenshots(scan) {
  if (!scan || (!scan.desktop_screenshot && !scan.mobile_screenshot)) return null;
  return createElement("div", { className: "screenshots" }, [
    scan.desktop_screenshot ? createElement("a", { href: `/screenshots/${scan.desktop_screenshot}`, target: "_blank" }, createElement("img", { src: `/screenshots/${scan.desktop_screenshot}`, alt: "Capture ordinateur", loading: "lazy" })) : null,
    scan.mobile_screenshot ? createElement("a", { href: `/screenshots/${scan.mobile_screenshot}`, target: "_blank" }, createElement("img", { src: `/screenshots/${scan.mobile_screenshot}`, alt: "Capture mobile", loading: "lazy" })) : null,
  ]);
}

function renderSynthesis(report, scan) {
  const offer = report.offer;
  const strengths = report.strengths || [];
  const criticalCount = (report.problems || []).filter((problem) => problem.severity === "critical").length;
  const majorCount = (report.problems || []).filter((problem) => problem.severity === "major").length;
  return [
    offer ? createElement("div", { className: "offer-card" }, [
      createElement("div", { className: "offer-label", text: "Offre à proposer" }),
      createElement("div", { className: "offer-title", text: offer.title }),
      createElement("div", { text: offer.pitch }),
    ]) : null,
    renderEditedBadge(report),
    renderSummaryEditor(report),
    (report.call_arguments || []).length ? createElement("div", { className: "panel" }, [
      createElement("strong", { text: "🎯 Vos 3 meilleurs arguments au téléphone" }),
      createElement("ol", {}, report.call_arguments.map((argument) => createElement("li", { text: argument }))),
    ]) : null,
    createElement("div", { className: "synthesis-columns" }, [
      createElement("div", {}, [
        createElement("h3", { text: `Score par catégorie` }),
        renderScoreBreakdown(report.score_breakdown) || createElement("p", { className: "muted", text: "Pas de site à noter." }),
        createElement("p", { className: "muted", text: `${criticalCount} problème(s) critique(s), ${majorCount} important(s).` }),
      ]),
      createElement("div", {}, [
        createElement("h3", { text: `Points forts (${strengths.length})` }),
        strengths.length
          ? createElement("ul", { className: "strength-list" }, strengths.map((strength) => createElement("li", { text: `✅ ${strength.label}` })))
          : createElement("p", { className: "muted", text: "Aucun point fort notable." }),
      ]),
    ]),
    renderScreenshots(scan),
  ];
}

const CATEGORY_OPTIONS = {
  design: "Design", mobile: "Mobile", performance: "Vitesse", conversion: "Conversion", seo: "Référencement Google",
  security: "Sécurité", legal: "Légal", content: "Contenu", technology: "Technique", sector: "Métier", availability: "Disponibilité",
};

function currentOverrides() {
  const overrides = detailState.prospect.diagnosis_overrides || {};
  return { dismissed_codes: [...(overrides.dismissed_codes || [])], custom_findings: [...(overrides.custom_findings || [])], summary: overrides.summary || null };
}

// Every correction goes through this call: the server stores it, then rebuilds score and report from it
function saveDiagnosisOverrides(overrides, successMessage) {
  return runProspectAction(requestJson(`/api/prospects/${detailState.prospect.id}/diagnosis`, { method: "PUT", body: overrides }), successMessage);
}

function renderEditedBadge(report) {
  return report.manually_edited ? createElement("div", { className: "edited-badge", text: "✏️ Diagnostic corrigé manuellement : vos corrections sont conservées lors des prochaines analyses." }) : null;
}

function renderSummaryEditor(report) {
  const summaryText = createElement("p", { text: report.summary });
  const editButton = createElement("button", { className: "button ghost small", text: "✏️ Modifier le résumé" });
  const container = createElement("div", { className: "summary-block" }, [summaryText, editButton]);
  editButton.addEventListener("click", () => {
    const summaryInput = createElement("textarea", { rows: 4 }, report.summary || "");
    container.replaceChildren(summaryInput, createElement("div", { className: "action-bar" }, [
      createElement("button", { className: "button primary small", text: "Enregistrer", onClick: () => saveDiagnosisOverrides({ ...currentOverrides(), summary: summaryInput.value.trim() || null }, "Résumé enregistré.") }),
      createElement("button", { className: "button ghost small", text: "Revenir au résumé automatique", onClick: () => saveDiagnosisOverrides({ ...currentOverrides(), summary: null }, "Résumé automatique rétabli.") }),
    ]));
    summaryInput.focus();
  });
  return container;
}

function renderCustomFindingForm() {
  const titleInput = createElement("input", { placeholder: "Ex. : quelques défauts d'affichage sur mobile" });
  const impactInput = createElement("textarea", { rows: 2, placeholder: "Pourquoi c'est un problème pour l'entreprise (facultatif)" });
  const severitySelect = createElement("select", {}, Object.entries(SEVERITY_LABELS).map(([severityKey, severityLabel]) => createElement("option", { value: severityKey, text: severityLabel, selected: severityKey === "minor" })));
  const categorySelect = createElement("select", {}, Object.entries(CATEGORY_OPTIONS).map(([categoryKey, categoryLabel]) => createElement("option", { value: categoryKey, text: categoryLabel })));
  return createElement("details", { className: "panel custom-finding-form" }, [
    createElement("summary", { text: "➕ Ajouter un point au diagnostic" }),
    createElement("label", {}, ["Titre", titleInput]),
    createElement("label", {}, ["Explication", impactInput]),
    createElement("div", { className: "crm-block" }, [createElement("label", {}, ["Gravité", severitySelect]), createElement("label", {}, ["Catégorie", categorySelect])]),
    createElement("button", {
      className: "button primary small",
      text: "Ajouter",
      onClick: () => {
        if (titleInput.value.trim().length < 2) {
          showToast("Donnez un titre au point à ajouter.", "error");
          return;
        }
        const overrides = currentOverrides();
        overrides.custom_findings.push({ title: titleInput.value.trim(), impact: impactInput.value.trim(), severity: severitySelect.value, category: categorySelect.value });
        saveDiagnosisOverrides(overrides, "Point ajouté au diagnostic.");
      },
    }),
  ]);
}

function renderProblem(problem) {
  const removeButton = createElement("button", {
    className: "problem-action",
    title: problem.custom ? "Supprimer ce point" : "Retirer ce point : l'analyse s'est trompée",
    text: problem.custom ? "🗑️ Supprimer" : "✖ Retirer",
    onClick: () => {
      const overrides = currentOverrides();
      if (problem.custom) overrides.custom_findings.splice(Number(problem.code.replace("custom_", "")), 1);
      else overrides.dismissed_codes.push(problem.code);
      saveDiagnosisOverrides(overrides, "Diagnostic mis à jour, score recalculé.");
    },
  });
  return createElement("div", { className: `problem ${problem.severity}` }, [
    createElement("div", { className: "problem-title" }, [
      createElement("span", { className: `tag ${problem.severity}`, text: SEVERITY_LABELS[problem.severity] }), " ",
      createElement("span", { className: "tag", text: problem.category_label }), " ",
      problem.custom ? createElement("span", { className: "tag", text: "Ajouté par vous" }) : null, " ",
      problem.title,
      removeButton,
    ]),
    problem.impact ? createElement("div", { text: problem.impact }) : null,
    problem.recommendation ? createElement("div", { className: "muted small-text", text: `➜ ${problem.recommendation}` }) : null,
  ]);
}

function renderDiagnosis(report) {
  const dismissedFindings = report.dismissed_findings || [];
  return [
    renderEditedBadge(report),
    createElement("h3", { text: `Ce qui ne va pas (${(report.problems || []).length})` }),
    createElement("p", { className: "muted small-text", text: "L'analyse s'est trompée ? Retirez le point concerné : le score et la fiche sont recalculés, et la correction reste valable aux prochaines analyses." }),
    ...(report.problems || []).map(renderProblem),
    renderCustomFindingForm(),
    dismissedFindings.length ? createElement("div", { className: "dismissed-block" }, [
      createElement("h3", { text: `Points retirés (${dismissedFindings.length})` }),
      ...dismissedFindings.map((finding) => createElement("div", { className: "dismissed-finding" }, [
        createElement("span", { text: finding.title }),
        createElement("button", {
          className: "problem-action",
          text: "↩ Rétablir",
          onClick: () => {
            const overrides = currentOverrides();
            overrides.dismissed_codes = overrides.dismissed_codes.filter((code) => code !== finding.code);
            saveDiagnosisOverrides(overrides, "Point rétabli.");
          },
        }),
      ])),
    ]) : null,
    createElement("h3", { text: "Plan d'amélioration" }),
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

function formatMetricValue(metricValue) {
  if (metricValue === true) return "Oui";
  if (metricValue === false) return "Non";
  if (Array.isArray(metricValue)) return metricValue.join(", ") || "Aucun";
  if (metricValue && typeof metricValue === "object") return Object.entries(metricValue).map(([metricKey, value]) => `${metricKey} : ${formatMetricValue(value)}`).join(" · ");
  return metricValue === null || metricValue === undefined ? "—" : String(metricValue);
}

function renderTechnicalData(scan) {
  if (!scan) return [createElement("p", { className: "muted", text: "Pas encore analysé." })];
  const contacts = scan.contacts || {};
  const metricRows = Object.entries(scan.metrics || {}).map(([metricKey, metricValue]) => createElement("tr", {}, [
    createElement("td", { text: METRIC_LABELS[metricKey] || metricKey }),
    createElement("td", { text: formatMetricValue(metricValue) }),
  ]));
  const generator = (scan.report || {}).generator;
  return [
    createElement("p", { className: "muted", text: `Analyse du ${formatDateTime(scan.scanned_at)} · rédaction : ${generator === "rules" ? "moteur de règles" : generator}` }),
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
  if (detailState.activeSubTab === "technical") return renderTechnicalData(scan);
  if (!report) return [createElement("p", { className: "muted", text: "Lancez l'analyse pour générer la synthèse, le diagnostic, le script d'appel et l'e-mail." })];
  if (detailState.activeSubTab === "diagnosis") return renderDiagnosis(report);
  if (detailState.activeSubTab === "script") return renderCallScript(report);
  if (detailState.activeSubTab === "email") return renderEmail(report, prospect);
  return renderSynthesis(report, scan);
}

function renderDetail() {
  const prospect = detailState.prospect;
  if (!prospect) return;
  const subTabs = visibleSubTabs();
  if (subTabs.length && !subTabs.some((subTab) => subTab.key === detailState.activeSubTab)) detailState.activeSubTab = subTabs[0].key;
  const subTabButtons = subTabs.map((subTab) => createElement("button", {
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
      createElement("button", { className: "button ghost drawer-close", text: "✕", "aria-label": "Fermer", onClick: closeProspectDetail }),
    ]),
    renderOrigin(prospect),
    renderActionBar(prospect),
    renderWebsiteBlock(prospect),
    renderContacts(prospect),
    renderCompanyFacts(prospect),
    renderPipelineBlock(prospect),
    subTabs.length ? createElement("div", { className: "sub-tabs" }, subTabButtons) : null,
    subTabs.length ? createElement("div", { className: "sub-view" }, renderSubView(prospect)) : null,
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
  detailState.activeSubTab = (visibleSubTabs()[0] || SUB_TABS[0]).key;
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
  settingsEvents.addEventListener("changed", () => renderDetail());
  liveEvents.addEventListener("scan.completed", (scanEvent) => {
    if (detailState.prospect && scanEvent.detail.prospect_id === detailState.prospect.id) reloadOpenProspect();
  });
  liveEvents.addEventListener("prospect.updated", (updateEvent) => {
    if (detailState.prospect && updateEvent.detail && updateEvent.detail.id === detailState.prospect.id) reloadOpenProspect();
  });
  liveEvents.addEventListener("prospect.deleted", (deleteEvent) => {
    if (detailState.prospect && (deleteEvent.detail.id === detailState.prospect.id || deleteEvent.detail.id === null)) reloadOpenProspectOrClose();
  });
}

async function reloadOpenProspectOrClose() {
  try {
    await reloadOpenProspect();
  } catch {
    closeProspectDetail();
  }
}
