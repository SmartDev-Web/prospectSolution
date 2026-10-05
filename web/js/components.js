// Small rendering components shared by several views.
import { createElement } from "./dom.js";
import { OPPORTUNITY_LABELS } from "./labels.js";

export function renderScoreBadge(prospect, size = "") {
  const opportunityLevel = prospect.opportunity_level || "";
  let badgeText = "?";
  if (prospect.score !== null && prospect.score !== undefined) badgeText = String(prospect.score);
  else if (opportunityLevel === "no_website") badgeText = "∅";
  return createElement("span", { className: `score-badge ${opportunityLevel} ${size}`, text: badgeText, title: OPPORTUNITY_LABELS[opportunityLevel] || "Non analysé" });
}
