/*
profile.js
-----------
Live Age (from the Year/Month/Day pickers) and BMI (from Height/Weight)
display in the profile form -- purely for immediate visual feedback. The
authoritative calculation happens server-side via
app.profile.calculate_age()/calculate_bmi() when the form is saved, so
this never risks drifting from what actually gets stored.
*/

function calculateAgeJS(year, month, day) {
  var today = new Date();
  var dob = new Date(year, month - 1, day);
  var age = today.getFullYear() - dob.getFullYear();
  var hasHadBirthdayThisYear =
    today.getMonth() > dob.getMonth() ||
    (today.getMonth() === dob.getMonth() && today.getDate() >= dob.getDate());
  if (!hasHadBirthdayThisYear) age -= 1;
  return Math.max(age, 0);
}

function calculateBmiJS(heightCm, weightKg) {
  if (!heightCm || heightCm <= 0) return null;
  var heightM = heightCm / 100;
  return Math.round((weightKg / (heightM * heightM)) * 10) / 10;
}

document.addEventListener("DOMContentLoaded", function () {
  var yearEl = document.getElementById("dobYear");
  var monthEl = document.getElementById("dobMonth");
  var dayEl = document.getElementById("dobDay");
  var ageDisplay = document.getElementById("ageDisplay");

  function updateAge() {
    if (!yearEl || !monthEl || !dayEl || !ageDisplay) return;
    var age = calculateAgeJS(
      parseInt(yearEl.value, 10), parseInt(monthEl.value, 10), parseInt(dayEl.value, 10)
    );
    ageDisplay.textContent = age + " years";
  }

  [yearEl, monthEl, dayEl].forEach(function (el) {
    if (el) el.addEventListener("change", updateAge);
  });
  updateAge();

  var heightEl = document.getElementById("heightInput");
  var weightEl = document.getElementById("weightInput");
  var bmiDisplay = document.getElementById("bmiDisplay");

  function updateBmi() {
    if (!heightEl || !weightEl || !bmiDisplay) return;
    var bmi = calculateBmiJS(parseFloat(heightEl.value), parseFloat(weightEl.value));
    bmiDisplay.textContent = bmi !== null && !isNaN(bmi) ? bmi : "-";
  }

  [heightEl, weightEl].forEach(function (el) {
    if (el) el.addEventListener("input", updateBmi);
  });
  updateBmi();

  var bloodGroupEl = document.getElementById("blood_group");
  var customBloodGroupContainer = document.getElementById("customBloodGroupContainer");
  var customBloodGroupEl = document.getElementById("custom_blood_group");

  function updateCustomBloodGroup(clearWhenHidden) {
    if (!bloodGroupEl || !customBloodGroupContainer || !customBloodGroupEl) return;
    var isOther = bloodGroupEl.value === "Other";
    customBloodGroupContainer.hidden = !isOther;
    customBloodGroupEl.disabled = !isOther;
    customBloodGroupEl.required = isOther;
    if (!isOther && clearWhenHidden) customBloodGroupEl.value = "";
  }

  if (bloodGroupEl) {
    bloodGroupEl.addEventListener("change", function () {
      updateCustomBloodGroup(true);
    });
  }
  updateCustomBloodGroup(false);

  var resetBtn = document.getElementById("resetBtn");
  if (resetBtn) {
    resetBtn.addEventListener("click", function () {
      // native form reset happens first (type="reset"), then refresh the
      // derived displays on the next tick once fields have reverted
      setTimeout(function () {
        updateAge();
        updateBmi();
        updateCustomBloodGroup(false);
      }, 0);
    });
  }
});
