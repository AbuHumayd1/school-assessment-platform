// Run before React/CSS: explicit preference wins; otherwise follow the system.
;(function () {
  var preference
  try { preference = localStorage.getItem('madaar.theme') } catch (_) {}
  var theme = preference === 'dark' || preference === 'light' ? preference :
    (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
  document.documentElement.dataset.theme = theme
  document.documentElement.style.colorScheme = theme
})()
