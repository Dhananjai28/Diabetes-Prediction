/*
charts.js
----------
Reusable Chart.js factory functions shared by dashboard.js and history.js,
so chart styling (colors pulled from the CSS theme variables, so charts
stay correct in both light and dark mode) lives in exactly one place.
*/

function getThemeColor(varName) {
  return getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
}

function createRiskDistributionChart(canvasId, riskCounts) {
  var el = document.getElementById(canvasId);
  if (!el) return null;
  return new Chart(el, {
    type: "doughnut",
    data: {
      labels: ["Green", "Yellow", "Red"],
      datasets: [{
        data: [riskCounts.Green || 0, riskCounts.Yellow || 0, riskCounts.Red || 0],
        backgroundColor: [
          getThemeColor("--color-success"),
          getThemeColor("--color-warning"),
          getThemeColor("--color-danger"),
        ],
        borderWidth: 0,
      }],
    },
    options: {
      responsive: true,
      plugins: { legend: { position: "bottom" } },
    },
  });
}

function createPredictionTrendChart(canvasId, labels, probabilities) {
  var el = document.getElementById(canvasId);
  if (!el) return null;
  var primary = getThemeColor("--color-primary");
  return new Chart(el, {
    type: "line",
    data: {
      labels: labels.map(function (l) { return l.split(" ")[0]; }),
      datasets: [{
        label: "Probability",
        data: probabilities.map(function (p) { return (p * 100).toFixed(1); }),
        borderColor: primary,
        backgroundColor: primary + "33",
        fill: true,
        tension: 0.3,
      }],
    },
    options: {
      responsive: true,
      scales: { y: { beginAtZero: true, max: 100, ticks: { callback: function (v) { return v + "%"; } } } },
      plugins: { legend: { display: false } },
    },
  });
}

function createProbabilityChart(canvasId, labels, probabilities) {
  var el = document.getElementById(canvasId);
  if (!el) return null;
  var primary = getThemeColor("--color-primary");
  return new Chart(el, {
    type: "bar",
    data: {
      labels: labels.map(function (l) { return l.split(" ")[0]; }),
      datasets: [{
        label: "Probability (%)",
        data: probabilities.map(function (p) { return (p * 100).toFixed(1); }),
        backgroundColor: primary,
      }],
    },
    options: {
      responsive: true,
      scales: { y: { beginAtZero: true, max: 100, ticks: { callback: function (v) { return v + "%"; } } } },
      plugins: { legend: { display: false } },
    },
  });
}
