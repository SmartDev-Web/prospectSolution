// DOM creation helpers and shared formatting functions.
// Link targets coming from scraped data are only rendered when they are web, mail, phone or local addresses
const SAFE_LINK_PATTERN = /^(https?:|mailto:|tel:|\/(?!\/)|#)/i;
const LINK_ATTRIBUTES = new Set(["href", "src", "action", "formaction"]);

export function createElement(tagName, attributes = {}, children = []) {
  const element = document.createElement(tagName);
  for (const [attributeName, attributeValue] of Object.entries(attributes)) {
    if (attributeValue === undefined || attributeValue === null || attributeValue === false) continue;
    if (attributeName === "className") element.className = attributeValue;
    else if (attributeName === "text") element.textContent = attributeValue;
    else if (attributeName.startsWith("on") && typeof attributeValue === "function") element.addEventListener(attributeName.slice(2).toLowerCase(), attributeValue);
    else if (attributeName === "dataset") Object.assign(element.dataset, attributeValue);
    else if (LINK_ATTRIBUTES.has(attributeName) && !SAFE_LINK_PATTERN.test(String(attributeValue).trim())) continue;
    else if (attributeValue === true) element.setAttribute(attributeName, "");
    else element.setAttribute(attributeName, attributeValue);
  }
  for (const child of [].concat(children)) {
    if (child === null || child === undefined || child === false) continue;
    element.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return element;
}

export function showToast(message, kind = "info") {
  const toast = createElement("div", { className: `toast ${kind}`, text: message });
  toast.addEventListener("animationend", () => toast.remove());
  document.getElementById("toasts").append(toast);
}

export function formatDate(isoDate) {
  if (!isoDate) return "";
  const parsedDate = new Date(isoDate.length === 10 ? `${isoDate}T00:00:00` : isoDate);
  return parsedDate.toLocaleDateString("fr-FR", { day: "2-digit", month: "short", year: "numeric" });
}

export function formatDateTime(isoDate) {
  if (!isoDate) return "";
  return new Date(isoDate).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
}

export function isoDateInDays(dayCount) {
  const targetDate = new Date();
  targetDate.setDate(targetDate.getDate() + dayCount);
  return targetDate.toLocaleDateString("sv-SE");
}

export function readableHost(url) {
  try {
    return new URL(url).host.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export async function copyToClipboard(text) {
  await navigator.clipboard.writeText(text);
  showToast("Copié dans le presse-papiers");
}
