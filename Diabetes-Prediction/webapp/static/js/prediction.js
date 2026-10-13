/*
prediction.js
-------------
Lightweight client-side UX only -- Bootstrap-style validation feedback on
submit plus a loading spinner on the submit button. The actual validation
rules (ranges, types) are enforced server-side by
app.validators.validate_prediction_form(), which this never duplicates.
*/

document.addEventListener("DOMContentLoaded", function () {
  var form = document.getElementById("predictionForm");
  if (!form) return;

  var btn = document.getElementById("predictBtn");
  var original = btn ? btn.innerHTML : "";

  form.addEventListener("submit", function (event) {
    if (!form.checkValidity()) {
      event.preventDefault();
      event.stopPropagation();
    } else if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>Running prediction...';
    }
    form.classList.add("was-validated");
  });

  form.addEventListener("reset", function () {
    if (btn) { btn.disabled = false; btn.innerHTML = original; }
    form.classList.remove("was-validated");
  });
});
