/** @odoo-module **/

function initChatroomPreview() {
    const preview = document.querySelector(".o_chatroom_ui_preview");
    if (!preview) {
        return;
    }
    const colors = ["primary", "secondary", "accent"];
    const update = () => colors.forEach((variable) => {
        const row = document.querySelector(`.o_chatroom_ui_color_row[data-chatroom-color='${variable}']`);
        const inputs = [...(row?.querySelectorAll("input") || [])];
        const input = inputs.find((candidate) => /^#[0-9a-f]{6}$/i.test(candidate.value?.trim()))
            || inputs[0];
        const value = input?.value?.trim();
        if (/^#[0-9a-f]{6}$/i.test(value || "")) {
            preview.style.setProperty(`--preview-${variable}`, value);
        }
    });
    preview._chatroomPreviewUpdate = update;
    update();
}

function refreshPreviewFromEvent(event) {
    const isColorChange = event.target?.closest?.(".o_chatroom_ui_color_row");
    const isPresetChange = event.target?.name?.includes?.("chatroom_ui_theme_preset");
    if (isColorChange || isPresetChange) {
        initChatroomPreview();
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
if (document.body) {
    new MutationObserver(initChatroomPreview).observe(
        document.body, { childList: true, subtree: true });
    initChatroomPreview();
} else {
    document.addEventListener("DOMContentLoaded", initChatroomPreview, { once: true });
}
