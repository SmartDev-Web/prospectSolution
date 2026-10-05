// Address input suggesting French places from the national geocoding service, shared by every location field.
import { buildQueryString, requestJson } from "./api.js";
import { createElement, showToast } from "./dom.js";

const MINIMUM_QUERY_LENGTH = 3;

export function createPlaceAutocomplete({ initialValue = "", placeholder, onPick }) {
  const input = createElement("input", { type: "search", value: initialValue, placeholder, autocomplete: "off" });
  const suggestionList = createElement("div", { className: "suggestions", hidden: true });
  let pendingGeocodeRequest = null;
  input.addEventListener("input", async () => {
    const query = input.value.trim();
    if (pendingGeocodeRequest) pendingGeocodeRequest.abort();
    if (query.length < MINIMUM_QUERY_LENGTH) {
      suggestionList.hidden = true;
      return;
    }
    pendingGeocodeRequest = new AbortController();
    try {
      const places = await requestJson(`/api/geocode${buildQueryString({ query })}`, { signal: pendingGeocodeRequest.signal });
      suggestionList.replaceChildren(...places.map((place) => createElement("button", {
        type: "button",
        text: place.label,
        onClick: () => {
          input.value = place.label;
          suggestionList.hidden = true;
          onPick(place);
        },
      })));
      suggestionList.hidden = places.length === 0;
    } catch (error) {
      if (error.name !== "AbortError") showToast(error.message, "error");
    }
  });
  input.addEventListener("blur", (blurEvent) => {
    if (!suggestionList.contains(blurEvent.relatedTarget)) suggestionList.hidden = true;
  });
  return { input, suggestionList };
}
