// Filter button opening a searchable checkbox list; selected values are combined with OR by the server.
import { createElement } from "./dom.js";
import { createPopover } from "./popover.js";

function normalizeForSearch(text) {
  return text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

export function createMultiSelectFilter({ label, getOptions, getSelectedValues, onChange, searchPlaceholder }) {
  const trigger = createElement("button", { type: "button", className: "filter-button" });
  function describeSelection() {
    const selectedValues = getSelectedValues();
    const optionLabels = new Map(getOptions().map((option) => [option.value, option.label]));
    trigger.classList.toggle("active", selectedValues.length > 0);
    const summary = selectedValues.length === 1 ? optionLabels.get(selectedValues[0]) || selectedValues[0] : `${selectedValues.length}`;
    trigger.replaceChildren(...[
      createElement("span", { className: "filter-button-label", text: label }),
      selectedValues.length ? createElement("span", { className: "filter-button-value", text: summary }) : null,
      createElement("span", { className: "filter-button-caret", text: "▾" }),
    ].filter(Boolean));
  }
  function buildContent() {
    const options = getOptions();
    const selectedValues = new Set(getSelectedValues());
    const optionCheckboxes = [];
    const groupCheckboxes = [];
    function publishSelection() {
      onChange(optionCheckboxes.filter((checkbox) => checkbox.checked).map((checkbox) => checkbox.value));
      groupCheckboxes.forEach(({ checkbox, members }) => {
        const checkedCount = members.filter((member) => member.checked).length;
        checkbox.checked = checkedCount === members.length;
        checkbox.indeterminate = checkedCount > 0 && checkedCount < members.length;
      });
      describeSelection();
    }
    function renderOption(option) {
      const checkbox = createElement("input", { type: "checkbox", value: option.value, checked: selectedValues.has(option.value), onChange: publishSelection });
      optionCheckboxes.push(checkbox);
      return createElement("label", { className: "choice", dataset: { search: normalizeForSearch(`${option.label} ${option.group || ""} ${option.keywords || ""}`) } }, [
        checkbox,
        createElement("span", { className: "choice-label", text: option.label }),
        option.count !== undefined ? createElement("span", { className: "choice-count", text: option.count }) : null,
      ]);
    }
    const groupLabels = [...new Set(options.map((option) => option.group).filter(Boolean))];
    const listChildren = groupLabels.length
      ? groupLabels.map((groupLabel) => {
        const groupOptionElements = options.filter((option) => option.group === groupLabel).map(renderOption);
        const members = groupOptionElements.map((optionElement) => optionElement.querySelector("input"));
        const groupCheckbox = createElement("input", {
          type: "checkbox",
          onChange: (changeEvent) => {
            members.filter((member) => !member.closest(".choice").hidden).forEach((member) => { member.checked = changeEvent.target.checked; });
            publishSelection();
          },
        });
        groupCheckboxes.push({ checkbox: groupCheckbox, members });
        return createElement("div", { className: "choice-group" }, [
          createElement("label", { className: "choice-group-header" }, [groupCheckbox, createElement("span", { text: groupLabel })]),
          ...groupOptionElements,
        ]);
      })
      : options.map(renderOption);
    const choiceList = createElement("div", { className: "choice-list" }, listChildren);
    const searchInput = options.length > 8 ? createElement("input", {
      type: "search",
      className: "choice-search",
      placeholder: searchPlaceholder || "Rechercher…",
      onInput: () => {
        const searchedText = normalizeForSearch(searchInput.value.trim());
        choiceList.querySelectorAll(".choice").forEach((choiceElement) => { choiceElement.hidden = Boolean(searchedText) && !choiceElement.dataset.search.includes(searchedText); });
        choiceList.querySelectorAll(".choice-group").forEach((groupElement) => { groupElement.hidden = !groupElement.querySelector(".choice:not([hidden])"); });
      },
    }) : null;
    const footer = createElement("div", { className: "choice-actions" }, [
      createElement("button", {
        type: "button",
        className: "link-button",
        text: "Cocher les éléments affichés",
        onClick: () => {
          optionCheckboxes.filter((checkbox) => !checkbox.closest(".choice").hidden).forEach((checkbox) => { checkbox.checked = true; });
          publishSelection();
        },
      }),
      createElement("button", {
        type: "button",
        className: "link-button",
        text: "Tout décocher",
        onClick: () => {
          optionCheckboxes.forEach((checkbox) => { checkbox.checked = false; });
          publishSelection();
        },
      }),
    ]);
    groupCheckboxes.forEach(({ checkbox, members }) => {
      const checkedCount = members.filter((member) => member.checked).length;
      checkbox.checked = checkedCount === members.length;
      checkbox.indeterminate = checkedCount > 0 && checkedCount < members.length;
    });
    return [searchInput, choiceList, footer].filter(Boolean);
  }
  const element = createPopover({ trigger, buildContent, panelClassName: "choice-panel" });
  describeSelection();
  return { element, refresh: describeSelection };
}
