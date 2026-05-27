(function() {
    function isReusable(form) {
        return form.hasAttribute("data-allow-resubmit");
    }

    function isGetForm(form) {
        return (form.getAttribute("method") || "get").toLowerCase() === "get";
    }

    function submitLabel(form, button) {
        if (button && button.dataset.submitLabel) {
            return button.dataset.submitLabel;
        }

        if (form.dataset.submitLabel) {
            return form.dataset.submitLabel;
        }

        const text = ((button && button.textContent) || "").trim().toLowerCase();
        if (
            text.includes("salvar")
            || text.includes("criar")
            || text.includes("editar")
            || text.includes("adicionar")
            || text.includes("alterar")
            || text.includes("finalizar cadastro")
        ) {
            return "Salvando...";
        }

        if (
            text.includes("enviar")
            || text.includes("entregar")
            || text.includes("redefinir")
            || text.includes("solicitar")
        ) {
            return "Enviando...";
        }

        return "Processando...";
    }

    function setButtonText(button, label) {
        if (!button || !label) {
            return;
        }

        if (!button.dataset.originalText) {
            button.dataset.originalText = button.innerHTML;
        }

        button.textContent = label;
    }

    document.addEventListener("submit", function(event) {
        const form = event.target;
        if (!form || form.tagName !== "FORM" || isReusable(form) || isGetForm(form)) {
            return;
        }

        if (form.dataset.submitted === "true") {
            event.preventDefault();
            event.stopImmediatePropagation();
            return;
        }

        form.dataset.submitted = "true";
        form.classList.add("is-submitting");
        form.setAttribute("aria-busy", "true");

        const submitSelector = 'button[type="submit"], button:not([type]), input[type="submit"]';
        const submitter = event.submitter || form.querySelector(submitSelector);
        const label = submitLabel(form, submitter);

        form.querySelectorAll(submitSelector).forEach(function(button) {
            setButtonText(button, label);
            button.disabled = true;
            button.setAttribute("aria-disabled", "true");
        });
    }, true);
})();
