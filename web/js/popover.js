// Anchored popovers shared by filter buttons and action menus: one open at a time, closed by an outside click or Escape.
import { createElement } from "./dom.js";

let openPopover = null;

export function closeOpenPopover() {
  if (!openPopover) return;
  openPopover.panel.hidden = true;
  openPopover.trigger.setAttribute("aria-expanded", "false");
  openPopover.trigger.classList.remove("open");
  openPopover = null;
}

document.addEventListener("pointerdown", (pointerEvent) => {
  if (openPopover && !openPopover.wrapper.contains(pointerEvent.target)) closeOpenPopover();
});
document.addEventListener("keydown", (keyEvent) => {
  if (keyEvent.key === "Escape") closeOpenPopover();
});

// The content builder runs on every opening so that the panel always reflects the current state
export function createPopover({ trigger, buildContent, alignment = "start", panelClassName = "" }) {
  const panel = createElement("div", { className: `popover-panel align-${alignment} ${panelClassName}`, hidden: true, role: "dialog" });
  const wrapper = createElement("div", { className: "popover" }, [trigger, panel]);
  trigger.setAttribute("aria-haspopup", "true");
  trigger.setAttribute("aria-expanded", "false");
  trigger.addEventListener("click", () => {
    const wasOpen = openPopover && openPopover.panel === panel;
    closeOpenPopover();
    if (wasOpen) return;
    panel.replaceChildren(...[].concat(buildContent(closeOpenPopover)).filter(Boolean));
    panel.classList.remove("align-start", "align-end");
    panel.classList.add(`align-${alignment}`);
    panel.hidden = false;
    // A panel that would leave the window is anchored to the other side of its button
    const panelBounds = panel.getBoundingClientRect();
    if (alignment === "start" && panelBounds.right > window.innerWidth - 8) panel.classList.replace("align-start", "align-end");
    if (alignment === "end" && panelBounds.left < 8) panel.classList.replace("align-end", "align-start");
    trigger.setAttribute("aria-expanded", "true");
    trigger.classList.add("open");
    openPopover = { trigger, panel, wrapper };
    const firstInput = panel.querySelector("input[type=search]");
    if (firstInput) firstInput.focus();
  });
  return wrapper;
}

// Dropdown menu of actions; each item closes the menu before running
export function createActionMenu({ label, className = "button secondary", items, alignment = "end" }) {
  const trigger = createElement("button", { type: "button", className: `${className} menu-trigger`, text: label });
  return createPopover({
    trigger,
    alignment,
    panelClassName: "menu-panel",
    buildContent: (closePopover) => items.filter(Boolean).map((menuItem) => menuItem.separator
      ? createElement("div", { className: "menu-separator" })
      : createElement("button", {
        type: "button",
        className: `menu-item ${menuItem.danger ? "danger" : ""}`,
        title: menuItem.title,
        onClick: () => {
          closePopover();
          menuItem.onSelect();
        },
      }, [
        createElement("span", { className: "menu-item-label", text: menuItem.label }),
        menuItem.hint ? createElement("span", { className: "menu-item-hint", text: menuItem.hint }) : null,
      ])),
  });
}
