/** @odoo-module **/

import { registry } from "@web/core/registry";

function initChatroomPreview() {
    const preview = document.querySelector(".o_chatroom_ui_preview");
    if (!preview) {
        return;
    }
    const colors = ["primary", "secondary", "accent"];
    const update = () => colors.forEach((variable) => {
        const row = document.querySelector(`.o_chatroom_ui_color_row[data-chatroom-color='${variable}']`);
        // The color widget also renders a hidden input. Prefer the visible
        // hexadecimal field so both editing modes always drive the preview.
        const hexInput = row?.querySelector(".o_chatroom_ui_hex_input input");
        const colorInput = row?.querySelector("input[type='color']");
        const value = (hexInput?.value || colorInput?.value || "").trim();
        if (/^#[0-9a-f]{6}$/i.test(value || "")) {
            preview.style.setProperty(`--preview-${variable}`, value);
        }
    });
    preview._chatroomPreviewUpdate = update;
    update();
}

function refreshPreviewFromEvent(event) {
    const colorRow = event.target?.closest?.(".o_chatroom_ui_color_row");
    const isColorChange = colorRow;
    const isPresetChange = event.target?.name?.includes?.("chatroom_ui_theme_preset");
    if (isColorChange || isPresetChange) {
        initChatroomPreview();
        const variable = colorRow?.dataset?.chatroomColor;
        const value = event.target?.value?.trim();
        if (variable && /^#[0-9a-f]{6}$/i.test(value || "")) {
            document.querySelector(".o_chatroom_ui_preview")
                ?.style.setProperty(`--preview-${variable}`, value);
        }
        // Onchange updates the other fields on the next Owl render cycle.
        // Read them again after that cycle so selecting WhatsApp/Océano also
        // updates the preview, not only manual color edits.
        setTimeout(() => {
            initChatroomPreview();
            document.querySelector(".o_chatroom_ui_preview")?._chatroomPreviewUpdate?.();
        }, 80);
    }
}

document.addEventListener("input", refreshPreviewFromEvent);
document.addEventListener("change", refreshPreviewFromEvent);

// Register as a backend service so the preview is initialized after the
// settings view is mounted. A standalone module can be evaluated before the
// settings tab exists, which made the old one-shot initialization unreliable.
registry.category("services").add("chatroom_ui_preview", {
    start() {
        const observe = () => {
            initChatroomPreview();
            if (document.body && !document.body._chatroomPreviewObserver) {
                document.body._chatroomPreviewObserver = new MutationObserver(
                    initChatroomPreview
                );
                document.body._chatroomPreviewObserver.observe(
                    document.body, { childList: true, subtree: true });
            }
        };
        if (document.body) {
            observe();
        } else {
            document.addEventListener("DOMContentLoaded", observe, { once: true });
        }
    },
});
