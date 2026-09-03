// Small, dependency-free UI behaviors. No network calls -- everything here
// only touches the DOM already delivered by the server.

document.addEventListener("click", (e) => {
  const btn = e.target.closest(".opt-btn");
  if (!btn) return;
  const group = btn.closest(".options");
  group.querySelectorAll(".opt-btn").forEach((b) => b.classList.remove("selected"));
  btn.classList.add("selected");
  const hiddenInput = group.parentElement.querySelector("input[type=hidden]");
  if (hiddenInput) {
    const changed = hiddenInput.value !== (btn.dataset.value || "");
    hiddenInput.value = btn.dataset.value || "";
    if (changed) {
      const form = btn.closest("form");
      if (form) form.dataset.dirty = "1";
    }
  }
});

// Warn before leaving a form with an unsaved opt-btn correction (answer-key
// editor, submission answer editor) -- a click that changes a selection
// shouldn't be silently lost to an accidental back/refresh/navigation.
document.querySelectorAll("form").forEach((form) => {
  form.addEventListener("submit", () => { form.dataset.dirty = ""; });
});
window.addEventListener("beforeunload", (e) => {
  const dirtyForm = document.querySelector('form[data-dirty="1"]');
  if (dirtyForm) { e.preventDefault(); e.returnValue = ""; }
});

document.querySelectorAll("input[type=file]").forEach((input) => {
  input.addEventListener("change", () => {
    const label = input.closest(".field")?.querySelector(".file-name");
    if (label) label.textContent = input.files[0] ? input.files[0].name : "";
  });
});

// ---------------------------------------------------------------------
// Toast notifications. The server renders flash messages into an inert
// <template id="flash-data"> (never displayed directly); this turns each
// one into a dismissible toast. Errors stay until closed, everything
// else auto-dismisses -- matching how transient vs. important feedback
// should behave.
// ---------------------------------------------------------------------
(function () {
  const dataTpl = document.getElementById("flash-data");
  const stack = document.getElementById("toast-stack");
  if (!dataTpl || !stack) return;

  const items = dataTpl.content.querySelectorAll("div[data-category]");
  items.forEach((item, i) => {
    const category = item.dataset.category === "success" || item.dataset.category === "error" || item.dataset.category === "warning"
      ? item.dataset.category : "success";
    const message = item.textContent;

    const toast = document.createElement("div");
    toast.className = `toast toast-${category}`;
    toast.setAttribute("role", category === "error" ? "alert" : "status");

    const msg = document.createElement("span");
    msg.className = "toast-msg";
    msg.textContent = message;

    const closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.className = "toast-close";
    closeBtn.setAttribute("aria-label", "Close");
    closeBtn.textContent = "\u00d7";

    toast.appendChild(msg);
    toast.appendChild(closeBtn);
    stack.appendChild(toast);

    const dismiss = () => {
      toast.classList.remove("show");
      setTimeout(() => toast.remove(), 220);
    };
    closeBtn.addEventListener("click", dismiss);

    // Stagger entrance slightly when several arrive together.
    setTimeout(() => toast.classList.add("show"), 30 + i * 70);
    if (category !== "error") {
      setTimeout(dismiss, 5000 + i * 400);
    }
  });
})();

// ---------------------------------------------------------------------
// Keyboard-driven answer-key editing: building a 100-question key by
// clicking is tedious, so the key grid supports arrow-key navigation +
// number keys to pick an option + Ctrl/Cmd+Enter to save.
// ---------------------------------------------------------------------
(function () {
  const grid = document.getElementById("keyGrid");
  if (!grid) return;
  const rows = Array.from(grid.querySelectorAll(".key-row"));
  let focused = 0;

  function setFocused(i) {
    if (i < 0 || i >= rows.length) return;
    rows[focused] && rows[focused].classList.remove("kb-focused");
    focused = i;
    rows[focused].classList.add("kb-focused");
    rows[focused].scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
  setFocused(0);

  rows.forEach((row, i) => row.addEventListener("click", () => setFocused(i)));

  document.addEventListener("keydown", (e) => {
    const tag = (e.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select") return;

    if (e.key === "ArrowDown") {
      e.preventDefault(); setFocused(focused + 1);
    } else if (e.key === "ArrowUp") {
      e.preventDefault(); setFocused(focused - 1);
    } else if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      const form = grid.closest("form");
      if (form) (form.requestSubmit ? form.requestSubmit() : form.submit());
    } else if (/^[1-9]$/.test(e.key)) {
      const optButtons = rows[focused].querySelectorAll(".opt-btn");
      const idx = parseInt(e.key, 10) - 1;
      if (optButtons[idx]) optButtons[idx].click();
    } else if (e.key === "0") {
      // Last opt-btn in a row is the "blank" option where present
      // (submission answer editing, not the answer-key editor).
      const optButtons = rows[focused].querySelectorAll(".opt-btn");
      const blankBtn = rows[focused].querySelector(".opt-btn-blank");
      if (blankBtn) blankBtn.click();
    }
  });
})();

// ---------------------------------------------------------------------
// Loading state for slow forms (batch upload, sheet processing): swap
// the submit button to a disabled spinner state so a slow CV pass on
// several images doesn't look like the click did nothing.
// ---------------------------------------------------------------------
document.querySelectorAll("form[data-loading-text]").forEach((form) => {
  form.addEventListener("submit", (e) => {
    const btn = form.querySelector("button[type=submit]");
    if (!btn || btn.disabled) return;
    btn.disabled = true;
    btn.classList.add("btn-loading");
    btn.innerHTML = `<span class="spinner"></span> ${form.dataset.loadingText}`;
  });
});

