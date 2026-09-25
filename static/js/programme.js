/* The conference programme (apps/programme): "my programme" stars, kept in the visitor's browser
   only (nothing is sent anywhere), and the page that lists the starred sessions. Without
   JavaScript, or without browser storage, the stars stay hidden and the programme works as before. */
(function () {
  "use strict";
  const key = year => "iglc-programme-" + year;
  function load(year) {
    try { return new Set(JSON.parse(localStorage.getItem(key(year)) || "[]").map(String)); }
    catch (e) { return null; }
  }
  function save(year, set) {
    try { localStorage.setItem(key(year), JSON.stringify([...set])); return true; } catch (e) { return false; }
  }

  function refresh(year, chosen) {
    document.querySelectorAll('[data-star][data-year="' + year + '"]').forEach(button => {
      const on = chosen.has(button.dataset.star);
      button.setAttribute("aria-pressed", on ? "true" : "false");
      button.title = on ? "In my programme (click to remove)" : "Add to my programme";
    });
    const mine = document.querySelector('[data-my-programme="' + year + '"]');
    if (!mine) return;
    let shown = 0;
    mine.querySelectorAll("[data-session]").forEach(item => {
      const on = chosen.has(item.dataset.session);
      item.hidden = !on;
      shown += on ? 1 : 0;
    });
    mine.querySelectorAll("[data-day]").forEach(day => {
      day.hidden = !day.querySelector("[data-session]:not([hidden])");
    });
    const empty = mine.querySelector("[data-my-empty]"), tools = mine.querySelector("[data-my-tools]");
    if (empty) empty.hidden = shown > 0;
    if (tools) {
      tools.hidden = shown === 0;
      const ids = [...chosen].join(",");
      tools.querySelectorAll("[data-my-calendar]").forEach(link => {
        const url = new URL(link.dataset.myCalendar, location.href);
        url.searchParams.set("sessions", ids);
        link.href = link.dataset.webcal !== undefined ? url.href.replace(/^https?:/, "webcal:") : url.href;
      });
    }
  }

  // Offline at the venue: a service worker keeps the programme's pages (apps/programme/offline.py).
  function offline() {
    const holder = document.querySelector("[data-sw]");
    if (holder && "serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost" || location.hostname.endsWith(".localhost"))) {
      navigator.serviceWorker.register(holder.dataset.sw, {scope: holder.dataset.swScope}).catch(() => null);
    }
    const note = document.querySelector("[data-offline-note]");
    if (note) {
      const show = () => { note.hidden = navigator.onLine; };
      window.addEventListener("online", show);
      window.addEventListener("offline", show);
      show();
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    offline();
    const years = new Set([...document.querySelectorAll("[data-star]")].map(b => b.dataset.year));
    document.querySelectorAll("[data-my-programme]").forEach(el => years.add(el.dataset.myProgramme));
    years.forEach(year => {
      const chosen = load(year);
      if (chosen === null) return;  // no storage: leave the stars hidden
      document.querySelectorAll('[data-star][data-year="' + year + '"]').forEach(button => {
        button.hidden = false;
        button.addEventListener("click", () => {
          const id = button.dataset.star;
          chosen.has(id) ? chosen.delete(id) : chosen.add(id);
          save(year, chosen);
          refresh(year, chosen);
        });
      });
      document.querySelectorAll('[data-my-programme="' + year + '"] [data-my-js]').forEach(el => el.hidden = false);
      refresh(year, chosen);
    });
  });
})();
