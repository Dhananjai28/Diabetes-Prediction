/*
dashboard.js
------------
Sets a time-of-day greeting on the Dashboard hero and initializes the two
charts (Risk Distribution, Prediction Trend) using the data dashboard.html
embeds via window.DASHBOARD_DATA, plus the shared factory functions in
charts.js.
*/

document.addEventListener("DOMContentLoaded", function () {
  var greeting = document.getElementById("greetingText");
  if (greeting) {
    var hour = new Date().getHours();
    var text = hour < 12 ? "Good Morning" : hour < 18 ? "Good Afternoon" : "Good Evening";
    var parts = greeting.textContent.split(",");
    var name = parts.length > 1 ? parts[1].trim() : "";
    greeting.textContent = text + (name ? ", " + name : "");
  }

  var data = window.DASHBOARD_DATA;
  if (!data) return;

  createRiskDistributionChart("riskDistributionChart", data.riskCounts);
  createPredictionTrendChart("predictionTrendChart", data.trendLabels, data.trendProbabilities);
});
