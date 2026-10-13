/*
history.js
----------
Initializes the History page's Probability Chart (data embedded via
window.HISTORY_DATA and the shared factory in charts.js) and applies the
client-side risk-level and date filters on top of the server-side search
results. Search itself stays server-side (?q=) in history.py.
*/

document.addEventListener("DOMContentLoaded", function () {
  var data = window.HISTORY_DATA;
  if (data && data.labels.length) {
    createProbabilityChart("probabilityChart", data.labels, data.probabilities);
  }

  var riskFilter = document.getElementById("riskFilter");
  var dateFilter = document.getElementById("dateFilter");
  var table = document.getElementById("historyTable");
  var empty = document.getElementById("historyEmpty");
  if (!table) return;

  function applyFilters() {
    var rows = table.querySelectorAll("tbody tr");
    var visible = 0;
    var risk = riskFilter ? riskFilter.value : "all";
    var date = dateFilter ? dateFilter.value : "";

    rows.forEach(function (row) {
      var riskOk = risk === "all" || risk === row.getAttribute("data-risk");
      var dateOk = !date || date === row.getAttribute("data-date");
      var show = riskOk && dateOk;
      row.style.display = show ? "" : "none";
      if (show) visible++;
    });

    if (empty) empty.classList.toggle("d-none", visible !== 0);
  }

  if (riskFilter) riskFilter.addEventListener("change", applyFilters);
  if (dateFilter) dateFilter.addEventListener("input", applyFilters);
});
