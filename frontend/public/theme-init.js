// Run before React/CSS: explicit preference wins; otherwise use light.
;(function () {
  var preference
  try { preference = localStorage.getItem('madaar.theme') } catch (_) {}
  var theme = preference === 'dark' || preference === 'light' ? preference : 'light'
  document.documentElement.dataset.theme = theme
  document.documentElement.style.colorScheme = theme
})()
