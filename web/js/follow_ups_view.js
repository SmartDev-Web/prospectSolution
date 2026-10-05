// Daily call list: due follow-ups and suggested first calls.
import { buildQueryString, requestJson } from "./api.js";
import { renderScoreBadge } from "./components.js";
import { createElement, formatDate } from "./dom.js";
import { OPPORTUNITY_LABELS, STATUS_LABELS } from "./labels.js";
import { liveEvents } from "./live.js";
import { openProspectDetail } from "./prospect_detail.js";
import { createCoalescedRefresher } from "./store.js";

const SUGGESTED_CALL_LIMIT = 24;

function renderCallCard(prospect) {
  return createElement("div", { className: "call-card", onClick: () => openProspectDetail(prospect.id) }, [
    createElement("div", { className: "call-card-header" }, [
      renderScoreBadge(prospect),
      createElement("div", {}, [
        createElement("div", { className: "prospect-name", text: prospect.name }),
        createElement("div", { className: "prospect-category", text: [prospect.category_label, prospect.city].filter(Boolean).join(" · ") }),
      ]),
    ]),
    prospect.phone
      ? createElement("p", {}, createElement("a", { href: `tel:${prospect.phone.replace(/\s/g, "")}`, text: `📞 ${prospect.phone}`, onClick: (clickEvent) => clickEvent.stopPropagation() }))
      : createElement("p", { className: "muted", text: "Pas de numéro connu" }),
    createElement("div", {}, [
      createElement("span", { className: "tag", text: STATUS_LABELS[prospect.status] }),
      " ",
      prospect.opportunity_level ? createElement("span", { className: `tag ${prospect.opportunity_level}`, text: OPPORTUNITY_LABELS[prospect.opportunity_level] }) : null,
      prospect.next_follow_up ? createElement("span", { className: "muted", text: ` · relance ${formatDate(prospect.next_follow_up)}` }) : null,
    ]),
  ]);
}

async function refreshFollowUps() {
  const [dueFollowUps, newProspects] = await Promise.all([
    requestJson("/api/follow-ups"),
    requestJson(`/api/prospects${buildQueryString({ status: "new", sort: "opportunity" })}`),
  ]);
  const suggestedCalls = newProspects.filter((prospect) => prospect.phone && ["no_website", "hot", "warm"].includes(prospect.opportunity_level)).slice(0, SUGGESTED_CALL_LIMIT);
  document.getElementById("due-follow-ups").replaceChildren(...(dueFollowUps.length ? dueFollowUps.map(renderCallCard) : [createElement("p", { className: "muted", text: "Aucune relance prévue aujourd'hui." })]));
  document.getElementById("suggested-calls").replaceChildren(...(suggestedCalls.length ? suggestedCalls.map(renderCallCard) : [createElement("p", { className: "muted", text: "Analysez vos prospects pour obtenir des suggestions." })]));
  const followUpCount = document.getElementById("follow-up-count");
  followUpCount.textContent = dueFollowUps.length;
  followUpCount.hidden = dueFollowUps.length === 0;
}

// The tab badge must stay accurate, so the call list refreshes even while hidden
export const requestFollowUpRefresh = createCoalescedRefresher(refreshFollowUps);

export function initializeFollowUpsView() {
  ["prospect.updated", "prospect.deleted", "scan.completed", "connected"].forEach((eventName) => liveEvents.addEventListener(eventName, requestFollowUpRefresh));
  requestFollowUpRefresh();
}
