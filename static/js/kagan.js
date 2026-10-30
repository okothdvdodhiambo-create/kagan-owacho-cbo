/* Kagan Owacho CBO - small vanilla helpers (slider, calendar, dashboard). */

(function () {
  "use strict";

  /* ----------------------------------------------------- home photo slider */
  function initSlider() {
    var root = document.querySelector("[data-slider]");
    if (!root) return;
    var slides = Array.prototype.slice.call(root.querySelectorAll(".koco-slide"));
    var dots = Array.prototype.slice.call(root.querySelectorAll("[data-dot]"));
    if (slides.length === 0) return;

    var index = 0;
    var timer = null;
    var delay = parseInt(root.getAttribute("data-interval") || "5000", 10);

    function show(next) {
      index = (next + slides.length) % slides.length;
      slides.forEach(function (slide, i) { slide.classList.toggle("is-active", i === index); });
      dots.forEach(function (dot, i) { dot.classList.toggle("is-active", i === index); });
    }
    function start() {
      stop();
      if (slides.length > 1) timer = setInterval(function () { show(index + 1); }, delay);
    }
    function stop() { if (timer) { clearInterval(timer); timer = null; } }

    var prev = root.querySelector("[data-prev]");
    var next = root.querySelector("[data-next]");
    if (prev) prev.addEventListener("click", function () { show(index - 1); start(); });
    if (next) next.addEventListener("click", function () { show(index + 1); start(); });
    dots.forEach(function (dot, i) { dot.addEventListener("click", function () { show(i); start(); }); });

    root.addEventListener("mouseenter", stop);
    root.addEventListener("mouseleave", start);
    root.addEventListener("focusin", stop);
    root.addEventListener("focusout", start);

    // Swipe on phones
    var startX = null;
    root.addEventListener("touchstart", function (event) { startX = event.touches[0].clientX; }, { passive: true });
    root.addEventListener("touchend", function (event) {
      if (startX === null) return;
      var delta = event.changedTouches[0].clientX - startX;
      if (Math.abs(delta) > 45) show(delta < 0 ? index + 1 : index - 1);
      startX = null;
      start();
    });

    document.addEventListener("visibilitychange", function () {
      if (document.hidden) stop(); else start();
    });

    show(0);
    start();
  }

  /* ------------------------------------------------------ resend cooldown */
  function initCooldown() {
    var el = document.querySelector("[data-cooldown-seconds]");
    if (!el) return;
    var button = el.querySelector("button");
    var label = el.querySelector("[data-cooldown-label]");
    var left = parseInt(el.getAttribute("data-cooldown-seconds"), 10) || 0;
    if (!button || left <= 0) return;

    var original = button.dataset.originalLabel || button.textContent;
    button.dataset.originalLabel = original;
    button.disabled = true;

    function tick() {
      if (left <= 0) {
        button.disabled = false;
        button.textContent = original;
        if (label) label.textContent = "";
        return;
      }
      button.textContent = original + " (" + left + "s)";
      if (label) label.textContent = "You can request another code in " + left + " seconds.";
      left -= 1;
      setTimeout(tick, 1000);
    }
    tick();
  }

  /* -------------------------------------------- M-Pesa waiting page poller */
  function initMpesaPolling() {
    var box = document.querySelector("[data-mpesa-waiting]");
    if (!box) return;
    var url = box.getAttribute("data-status-url");
    var result = box.querySelector("[data-mpesa-result]");
    var attempts = 0;

    function poll() {
      attempts += 1;
      fetch(url, { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
        .then(function (response) { return response.json(); })
        .then(function (data) {
          if (data.status === "confirmed") {
            result.innerHTML =
              '<div class="alert alert-success mb-0"><strong>Payment received.</strong> ' +
              "M-Pesa code " + (data.reference || "-") + " of KSh " + data.amount + " is on your transcript." +
              '<a class="koco-btn koco-btn-outline koco-btn-sm ms-2" href="/contributions/transcript/">View transcript</a></div>';
            return;
          }
          if (data.status === "failed" || data.status === "cancelled") {
            result.innerHTML =
              '<div class="alert alert-warning mb-0">The prompt was ' + data.status +
              ". You can pay from your phone and record the M-Pesa code instead." +
              '<a class="koco-btn koco-btn-outline koco-btn-sm ms-2" href="/contributions/mpesa/record-code/">Record a code</a></div>';
            return;
          }
          if (attempts < 40) setTimeout(poll, 5000);
          else
            result.innerHTML =
              '<div class="alert alert-secondary mb-0">Still waiting for Safaricom. ' +
              "The payment shows on your transcript once the network confirms it.</div>";
        })
        .catch(function () {
          if (attempts < 40) setTimeout(poll, 8000);
        });
    }
    setTimeout(poll, 4000);
  }

  /* ----------------------------------------------------- dashboard sidebar */
  function initSidebar() {
    var side = document.querySelector("[data-side]");
    var toggle = document.querySelector("[data-side-toggle]");
    if (!side || !toggle) return;
    toggle.addEventListener("click", function () {
      var collapsed = side.getAttribute("data-collapsed") === "true";
      side.setAttribute("data-collapsed", collapsed ? "false" : "true");
      toggle.setAttribute("aria-expanded", collapsed ? "true" : "false");
    });
  }

  /* ------------------------------------------------------- calendar modal */
  function initCalendar() {
    var el = document.getElementById("koco-calendar");
    if (!el || typeof FullCalendar === "undefined") return;
    var modal = document.getElementById("eventModal");
    var timeZone = el.getAttribute("data-timezone") || "local";
    var calendar = new FullCalendar.Calendar(el, {
      initialView: "dayGridMonth",
      height: "auto",
      timeZone: timeZone,
      headerToolbar: { left: "prev,next today", center: "title", right: "dayGridMonth,listMonth" },
      buttonText: { today: "Today", month: "Month", list: "List" },
      events: el.getAttribute("data-feed-url"),
      eventClick: function (info) {
        info.jsEvent.preventDefault();
        var ev = info.event;
        modal.querySelector("[data-modal-title]").textContent = ev.title;
        modal.querySelector("[data-modal-when]").textContent =
          ev.start.toLocaleString("en-KE", { weekday: "long", day: "numeric", month: "long", year: "numeric", hour: "numeric", minute: "2-digit", timeZone: timeZone }) +
          " (EAT)";
        modal.querySelector("[data-modal-venue]").textContent = ev.extendedProps.venue || "Venue to be confirmed";
        modal.querySelector("[data-modal-desc]").textContent = ev.extendedProps.description || "No description yet.";
        var link = modal.querySelector("[data-modal-link]");
        link.href = ev.url || "#";
        link.style.display = ev.url ? "inline-flex" : "none";
        var pop = new bootstrap.Modal(modal);
        pop.show();
      }
    });
    calendar.render();
  }

  /* ------------------------------------------------ confirm before delete */
  function initConfirmations() {
    document.querySelectorAll("form[data-confirm]").forEach(function (form) {
      form.addEventListener("submit", function (event) {
        if (!window.confirm(form.getAttribute("data-confirm"))) event.preventDefault();
      });
    });
  }

  /* ------------------------------------- number input shows KSh as typed */
  function initMoneyHints() {
    document.querySelectorAll('input[type="number"][data-ksh]').forEach(function (input) {
      var hint = document.querySelector('[data-money-preview="' + input.name + '"]');
      if (!hint) return;
      function update() {
        var value = parseFloat(input.value || "0");
        hint.textContent = isNaN(value) ? "KSh 0.00" : "KSh " + value.toLocaleString("en-KE", { minimumFractionDigits: 2 });
      }
      input.addEventListener("input", update);
      update();
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initSlider();
    initCooldown();
    initMpesaPolling();
    initSidebar();
    initCalendar();
    initConfirmations();
    initMoneyHints();
  });
})();
