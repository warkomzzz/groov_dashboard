import { useEffect, useState } from 'react';

type Theme = 'dark' | 'light';

function applyTheme(t: Theme) {
  const root = document.documentElement;
  root.classList.toggle('theme-light', t === 'light');
  localStorage.setItem('theme', t);
}

export default function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(() => (localStorage.getItem('theme') as Theme) || 'dark');

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  const toggle = () => setTheme((t) => (t === 'dark' ? 'light' : 'dark'));

  return (
    <button
      aria-label="Cambiar tema"
      onClick={toggle}
      className="theme-toggle glass-card p-2 rounded-full hover:scale-[1.03] transition-transform"
      title={theme === 'dark' ? 'Cambiar a claro' : 'Cambiar a oscuro'}
    >
      {theme === 'dark' ? (
        // Sol simple con líneas (mejor legibilidad)
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M4 12H2M22 12h-2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
        </svg>
      ) : (
        // Luna
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
        </svg>
      )}
    </button>
  );
}
