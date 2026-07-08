// Main JavaScript for Software Reviews Site

document.addEventListener('DOMContentLoaded', function() {
  // Search toggle
  window.toggleSearch = function() {
    const input = document.getElementById('hero-search-input');
    if (input) {
      input.focus();
    }
  };

  // Hero search functionality
  const searchInput = document.getElementById('hero-search-input');
  if (searchInput) {
    searchInput.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') {
        const query = this.value.trim();
        if (query.length > 0) {
          window.location.href = '/search/?q=' + encodeURIComponent(query);
        }
      }
    });
  }
});
