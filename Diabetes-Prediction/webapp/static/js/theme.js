/*
theme.js
--------
Dark/light theme toggle (persisted in localStorage, matching the pattern
used across every page since base.html sets the initial theme inline
before first paint), the mobile hamburger menu, and the toast (flash
message) auto-hide/close behaviour.
*/

document.addEventListener("DOMContentLoaded", function () {
  var root = document.documentElement;
  var themeBtn = document.getElementById("themeToggleBtn");
  var themeIcon = document.getElementById("themeToggleIcon");

  function syncThemeIcon() {
    if (!themeIcon) return;
    var mode = root.getAttribute("data-bs-theme") || "light";
    themeIcon.className = mode === "dark" ? "bi bi-sun" : "bi bi-moon-stars";
  }

  if (themeBtn) {
    themeBtn.addEventListener("click", function () {
      var current = root.getAttribute("data-bs-theme") || "light";
      var next = current === "dark" ? "light" : "dark";
      root.setAttribute("data-bs-theme", next);
      localStorage.setItem("diabetesAppTheme", next);
      syncThemeIcon();
    });
  }
  syncThemeIcon();

  // Mobile hamburger menu
  var navToggle = document.getElementById("navToggleBtn");
  var nav = document.getElementById("mainNav");
  if (navToggle && nav) {
    navToggle.addEventListener("click", function () {
      var isOpen = nav.classList.toggle("open");
      navToggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
    });
    nav.addEventListener("click", function (e) {
      if (e.target.closest("a")) {
        nav.classList.remove("open");
        navToggle.setAttribute("aria-expanded", "false");
      }
    });
  }

  window.addEventListener("resize", function () {
    if (window.innerWidth >= 1200 && nav) {
      nav.classList.remove("open");
      if (navToggle) navToggle.setAttribute("aria-expanded", "false");
    }
  });

  // Toasts: auto-hide + manual close
  document.querySelectorAll(".app-toast").forEach(function (toast) {
    var closeBtn = toast.querySelector("[data-toast-close]");
    if (closeBtn) {
      closeBtn.addEventListener("click", function () {
        toast.classList.add("hide-toast");
        setTimeout(function () { toast.remove(); }, 350);
      });
    }
    setTimeout(function () {
      toast.classList.add("hide-toast");
      setTimeout(function () { toast.remove(); }, 350);
    }, 4500);
  });
});
