/** @odoo-module **/

function initChatroomPreview() {
    const preview = document.querySelector(".o_chatroom_ui_preview");
    if (!preview || preview.dataset.ready === "1") {
        return;
    }
    preview.dataset.ready = "1";
    const names = {
        primary: "chatroom_ui_primary_color",
        secondary: "chatroom_ui_secondary_color",
        accent: "chatroom_ui_accent_color",
    };
    const update = () => Object.entries(names).forEach(([variable, fieldName]) => {
        const input = document.querySelector(`input[name="${fieldName}"]`);
        if (input?.value) {
            preview.style.setProperty(`--preview-${variable}`, input.value);
        }
    });
    preview._chatroomPreviewUpdate = update;
    update();
}

document.addEventListener("input", (event) => {
    if (event.target?.name?.startsWith("chatroom_ui_")) {
        initChatroomPreview();
        document.querySelector(".o_chatroom_ui_preview")?._chatroomPreviewUpdate?.();
    }
});
document.addEventListener("change", (event) => {
    if (event.target?.name?.startsWith("chatroom_ui_")) {
        initChatroomPreview();
        document.querySelector(".o_chatroom_ui_preview")?._chatroomPreviewUpdate?.();
    }
});
if (document.body) {
    new MutationObserver(initChatroomPreview).observe(
        document.body, { childList: true, subtree: true });
    initChatroomPreview();
} else {
    document.addEventListener("DOMContentLoaded", initChatroomPreview, { once: true });
}
