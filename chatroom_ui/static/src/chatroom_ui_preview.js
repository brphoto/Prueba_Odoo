/** @odoo-module **/

function initChatroomPreview() {
    const preview = document.querySelector(".o_chatroom_ui_preview");
    if (!preview) {
        return;
    }
    const colors = ["primary", "secondary", "accent"];
    const update = () => colors.forEach((variable, index) => {
        const row = document.querySelectorAll(".o_chatroom_ui_color_row")[index];
        const input = row?.querySelector("input[type='color'], input[type='text']");
        if (input?.value) {
            preview.style.setProperty(`--preview-${variable}`, input.value.trim());
        }
    });
    preview._chatroomPreviewUpdate = update;
    update();
}

document.addEventListener("input", (event) => {
    if (event.target?.closest?.(".o_chatroom_ui_color_row")) {
        initChatroomPreview();
        document.querySelector(".o_chatroom_ui_preview")?._chatroomPreviewUpdate?.();
    }
});
document.addEventListener("change", (event) => {
    if (event.target?.closest?.(".o_chatroom_ui_color_row")) {
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
