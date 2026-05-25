(function() {
    const app = document.querySelector("[data-slides-app]");
    if (!app) {
        return;
    }

    const apiUrl = app.dataset.apiUrl || "/api/slides";
    const stage = app.querySelector("[data-slide-stage]");
    const clock = app.querySelector("[data-tv-clock]");
    const updated = app.querySelector("[data-tv-updated]");
    const position = app.querySelector("[data-slide-position]");
    const progress = app.querySelector("[data-slide-progress]");
    const previousButton = app.querySelector("[data-slide-prev]");
    const nextButton = app.querySelector("[data-slide-next]");

    let payload = null;
    let slides = [];
    let currentIndex = 0;
    let slideTimer = null;
    let refreshTimer = null;
    let progressTimer = null;
    let slideStartedAt = Date.now();
    let slideMs = 8000;
    let refreshMs = 90000;
    let isLoading = false;

    function escapeHtml(value) {
        return String(value || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function updateClock() {
        if (!clock) {
            return;
        }

        const now = new Date();
        clock.textContent = now.toLocaleTimeString("pt-BR", {
            hour: "2-digit",
            minute: "2-digit",
            timeZone: "America/Sao_Paulo",
        });
    }

    function renderSummarySlide(slidePayload) {
        const resumo = payload.resumo || {};
        const cards = [
            ["total_atrasadas", "Atrasadas", "atrasada"],
            ["vencem_hoje", "Vencem hoje", "hoje"],
            ["vencem_amanha", "Vencem amanhã", "amanha"],
            ["proximas_2_semanas", "Próximas 2 semanas", "proximos_15_dias"],
        ];

        return `
            <article class="tv-slide" data-slide-id="${escapeHtml(slidePayload.id)}">
                <div class="tv-slide-head">
                    <h2 class="tv-slide-title">${escapeHtml(slidePayload.titulo)}</h2>
                    <span class="tv-slide-count">OPs ativas</span>
                </div>
                <div class="tv-summary-grid">
                    ${cards.map(function(card) {
                        return `
                            <div class="tv-summary-card">
                                <strong>${Number(resumo[card[0]] || 0)}</strong>
                                <span>${escapeHtml(card[1])}</span>
                                <span class="tv-pill ${card[2]}">${escapeHtml(card[1])}</span>
                            </div>
                        `;
                    }).join("")}
                </div>
            </article>
        `;
    }

    function renderTask(item) {
        return `
            <div class="tv-task" data-urgencia="${escapeHtml(item.urgencia)}">
                <div class="tv-task-main">
                    <strong>${escapeHtml(item.op)}</strong>
                    <span>Cliente: ${escapeHtml(item.cliente)}</span>
                </div>
                <div class="tv-task-name">
                    <strong>${escapeHtml(item.tarefa)}</strong>
                    <span>${escapeHtml(item.setor)}</span>
                    <span>${escapeHtml(item.responsavel || "Geral do setor")}</span>
                </div>
                <div class="tv-task-meta">
                    <span>Prazo</span>
                    <strong>${escapeHtml(item.prazo_formatado)}</strong>
                </div>
                <span class="tv-pill ${escapeHtml(item.urgencia)}">${escapeHtml(item.urgencia_texto)} - ${escapeHtml(item.status)}</span>
            </div>
        `;
    }

    function renderListSlide(slidePayload) {
        const itens = slidePayload.itens || [];
        const body = itens.length
            ? `<div class="tv-task-list">${itens.map(renderTask).join("")}</div>`
            : `<div class="tv-empty">${escapeHtml(slidePayload.vazio || "Nenhuma tarefa")}</div>`;

        return `
            <article class="tv-slide" data-slide-id="${escapeHtml(slidePayload.id)}">
                <div class="tv-slide-head">
                    <h2 class="tv-slide-title">${escapeHtml(slidePayload.titulo)}</h2>
                    <span class="tv-slide-count">${itens.length} item(ns)</span>
                </div>
                ${body}
            </article>
        `;
    }

    function slideShouldRender(slidePayload) {
        if (!slidePayload) {
            return false;
        }
        if (slidePayload.tipo === "resumo") {
            return true;
        }
        return slidePayload.tipo === "lista";
    }

    function renderSlides() {
        const previousSlide = slides[currentIndex];
        const previousSlideId = previousSlide && previousSlide.id;
        slides = (payload.slides || []).filter(slideShouldRender);

        const preservedIndex = slides.findIndex(function(slidePayload) {
            return slidePayload.id === previousSlideId;
        });
        currentIndex = preservedIndex >= 0
            ? preservedIndex
            : Math.min(currentIndex, Math.max(slides.length - 1, 0));

        if (!slides.length) {
            stage.innerHTML = '<div class="tv-empty">Nenhuma tarefa para exibir</div>';
            return;
        }

        stage.innerHTML = slides.map(function(slidePayload) {
            if (slidePayload.tipo === "resumo") {
                return renderSummarySlide(slidePayload);
            }
            return renderListSlide(slidePayload);
        }).join("");

        showSlide(currentIndex);
    }

    function showSlide(index) {
        const slideElements = Array.from(stage.querySelectorAll(".tv-slide"));
        if (!slideElements.length) {
            return;
        }

        currentIndex = (index + slideElements.length) % slideElements.length;
        slideElements.forEach(function(slide, slideIndex) {
            slide.classList.toggle("is-active", slideIndex === currentIndex);
            slide.hidden = slideIndex !== currentIndex;
        });

        if (position) {
            position.textContent = "Slide " + (currentIndex + 1) + "/" + slideElements.length;
        }

        slideStartedAt = Date.now();
        if (progress) {
            progress.style.width = "0%";
        }
    }

    function nextSlide() {
        showSlide(currentIndex + 1);
    }

    function restartSlideTimer() {
        window.clearInterval(slideTimer);
        slideTimer = slides.length > 1
            ? window.setInterval(nextSlide, slideMs)
            : null;
    }

    function navigateManually(offset) {
        if (!slides.length) {
            return;
        }

        showSlide(currentIndex + offset);
        restartSlideTimer();
    }

    function resetTimers() {
        window.clearInterval(slideTimer);
        window.clearInterval(progressTimer);

        restartSlideTimer();
        progressTimer = window.setInterval(function() {
            if (!progress) {
                return;
            }
            const elapsed = Date.now() - slideStartedAt;
            const pct = Math.min(100, (elapsed / slideMs) * 100);
            progress.style.width = pct + "%";
        }, 250);
    }

    function scheduleRefresh() {
        window.clearTimeout(refreshTimer);
        refreshTimer = window.setTimeout(loadSlides, refreshMs);
    }

    async function loadSlides() {
        if (isLoading) {
            return;
        }

        isLoading = true;
        try {
            const response = await fetch(apiUrl, {
                headers: {
                    "Accept": "application/json",
                    "X-Requested-With": "XMLHttpRequest",
                },
            });

            if (!response.ok) {
                throw new Error("Falha ao carregar slides");
            }

            payload = await response.json();
            slideMs = Number(payload.intervalos && payload.intervalos.slide_ms) || 8000;
            refreshMs = Number(payload.intervalos && payload.intervalos.atualizacao_ms) || 90000;
            renderSlides();
            resetTimers();

            if (updated) {
                updated.textContent = "Atualizado agora";
            }
        } catch (error) {
            if (!slides.length) {
                stage.innerHTML = '<div class="tv-error">Não foi possível carregar o painel.</div>';
            }
        } finally {
            isLoading = false;
            scheduleRefresh();
        }
    }

    updateClock();
    window.setInterval(updateClock, 1000);
    loadSlides();

    if (previousButton) {
        previousButton.addEventListener("click", function() {
            navigateManually(-1);
        });
    }

    if (nextButton) {
        nextButton.addEventListener("click", function() {
            navigateManually(1);
        });
    }

    window.addEventListener("keydown", function(event) {
        if (event.key === "ArrowLeft") {
            navigateManually(-1);
        }
        if (event.key === "ArrowRight") {
            navigateManually(1);
        }
    });

    window.addEventListener("beforeunload", function() {
        window.clearInterval(slideTimer);
        window.clearTimeout(refreshTimer);
        window.clearInterval(progressTimer);
    });
})();
