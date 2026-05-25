document.addEventListener("click", function(event) {
    const button = event.target.closest("[data-password-toggle]");
    if (!button) {
        return;
    }

    const targetId = button.getAttribute("data-password-toggle");
    const input = document.getElementById(targetId);
    if (!input) {
        return;
    }

    const mostrar = input.type === "password";
    input.type = mostrar ? "text" : "password";
    button.textContent = mostrar ? "Ocultar" : "Mostrar";
});
