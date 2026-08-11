(function () {
  var chips = Array.prototype.slice.call(document.querySelectorAll('.chip'));
  var search = document.getElementById('search');
  var cards = Array.prototype.slice.call(document.querySelectorAll('.card'));
  var resultCount = document.getElementById('result-count');
  var noResults = document.querySelector('.no-results');
  var activeCategory = 'all';

  function applyFilters() {
    var q = (search.value || '').trim().toLowerCase();
    var visible = 0;
    cards.forEach(function (card) {
      var matchesCategory = activeCategory === 'all' || card.dataset.category === activeCategory;
      var matchesSearch = !q || card.dataset.title.indexOf(q) !== -1;
      var show = matchesCategory && matchesSearch;
      card.style.display = show ? '' : 'none';
      if (show) visible++;
    });
    resultCount.textContent = visible + (visible === 1 ? ' item' : ' items');
    noResults.style.display = visible === 0 ? 'block' : 'none';
  }

  chips.forEach(function (chip) {
    chip.addEventListener('click', function () {
      chips.forEach(function (c) { c.classList.remove('active'); });
      chip.classList.add('active');
      activeCategory = chip.dataset.category;
      applyFilters();
    });
  });

  search.addEventListener('input', applyFilters);
  applyFilters();
})();
