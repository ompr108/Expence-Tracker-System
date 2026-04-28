document.addEventListener('DOMContentLoaded', () => {
  // Set today's date on empty date inputs
  const today = new Date().toISOString().split('T')[0];
  document.querySelectorAll('input[type=date]:not([value])').forEach(el => { el.value = today; });
  const md = document.getElementById('modalDate');
  if (md && !md.value) md.value = today;

  // Collapsible Sidebar
  const sidebar = document.getElementById('sidebar');
  const main    = document.getElementById('mainContent');
  const toggle  = document.getElementById('sidebarToggle');
  const COLLAPSED_KEY = 'sidebar_collapsed';
  const isCollapsed = () => localStorage.getItem(COLLAPSED_KEY) === '1';

  function applySidebarState() {
    if (!sidebar) return;
    if (isCollapsed()) {
      sidebar.classList.add('collapsed');
      main?.classList.add('expanded');
    } else {
      sidebar.classList.remove('collapsed');
      main?.classList.remove('expanded');
    }
  }
  applySidebarState();
  toggle?.addEventListener('click', () => {
    localStorage.setItem(COLLAPSED_KEY, isCollapsed() ? '0' : '1');
    applySidebarState();
  });

  // Modal helpers
  window.openModal = function() {
    const m = document.getElementById('addModal');
    if (m) { m.classList.add('open'); document.getElementById('modalDate')?.focus(); }
  };
  window.closeModal = function() {
    document.getElementById('addModal')?.classList.remove('open');
  };
  const overlay = document.getElementById('addModal');
  if (overlay) {
    overlay.addEventListener('click', e => { if (e.target === overlay) closeModal(); });
    document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });
  }

  // Form submit loading state
  document.querySelectorAll('form').forEach(form => {
    form.addEventListener('submit', () => {
      const btn = form.querySelector('button[type=submit]');
      if (btn) { btn.textContent = '⏳ Saving…'; btn.disabled = true; }
    });
  });

  // Budget bar animation trigger
  document.querySelectorAll('.budget-bar-fill').forEach(bar => {
    const w = bar.style.getPropertyValue('--target-w') || '0%';
    bar.style.setProperty('--target-w', w);
  });

  // Savings ring animation
  const ring = document.getElementById('savingsRing');
  if (ring) {
    const pct = parseFloat(ring.dataset.pct) || 0;
    setTimeout(() => { ring.style.strokeDashoffset = 198 - (pct / 100) * 198; }, 500);
  }
});
