import { useState } from 'react';
import { login } from '../lib/api';
import ThemeToggle from './ThemeToggle';

export default function Login({ onLoggedIn }: { onLoggedIn: (role: string) => void }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [remember, setRemember] = useState(false);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await login(username.trim(), password);
      // (Opcional) persistir "remember" si aplica
      onLoggedIn(res.role);
    } catch {
      alert('Usuario o contraseña inválidos');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="relative min-h-screen w-full overflow-hidden flex items-center justify-center brand-gradient brand-surface">
      <ThemeToggle />
      {/* Contenedor principal */}
      <div className="w-full max-w-md px-6 sm:px-8">
        {/* Avatar */}
        <div className="mx-auto mb-6 flex h-24 w-24 items-center justify-center rounded-full bg-white/10 backdrop-blur border border-white/20 shadow-xl">
          {/* Ícono de usuario simple */}
          <svg width="44" height="44" viewBox="0 0 24 24" fill="none" className="text-white/90">
            <path d="M12 12c2.761 0 5-2.239 5-5s-2.239-5-5-5-5 2.239-5 5 2.239 5 5 5Z" fill="currentColor"/>
            <path d="M3 22c0-3.866 3.582-7 8-7s8 3.134 8 7" fill="currentColor"/>
          </svg>
        </div>

        {/* Tarjeta de login */}
        <form onSubmit={handleSubmit} className="glass-card p-6 sm:p-8 space-y-5">
          <h2 className="text-center text-xl font-semibold tracking-wide text-white/95">Iniciar sesión</h2>

          {/* Usuario */}
          <div className="relative">
            <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-600">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 12c2.8 0 5-2.2 5-5s-2.2-5-5-5-5 2.2-5 5 2.2 5 5 5Zm-9 9c0-3.9 3.6-7 9-7s9 3.1 9 7v1H3v-1Z"/>
              </svg>
            </span>
            <input
              className="glass-input pl-12 pr-3"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Usuario"
              autoComplete="username"
            />
          </div>

          {/* Contraseña */}
          <div className="relative">
            <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-600">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                <path d="M17 8h-1V6a4 4 0 0 0-8 0v2H7a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V10a2 2 0 0 0-2-2Zm-3 0H10V6a2 2 0 1 1 4 0v2Z"/>
              </svg>
            </span>
            <input
              className="glass-input pl-12 pr-3"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Contraseña"
              autoComplete="current-password"
            />
          </div>

          {/* Opciones */}
          <div className="flex items-center justify-between text-sm">
            <label className="flex items-center gap-2 text-white/80">
              <input
                type="checkbox"
                checked={remember}
                onChange={(e) => setRemember(e.target.checked)}
                className="h-4 w-4 accent-[var(--brand-teal)]"
              />
              Recuérdame
            </label>
            {/* Enlace eliminado a pedido del usuario */}
          </div>

          {/* Botón */}
          <button
            disabled={loading}
            className="mt-2 w-full brand-button tracking-wide disabled:opacity-70 disabled:cursor-not-allowed shadow"
          >
            {loading ? 'Ingresando…' : 'LOGIN'}
          </button>
        </form>
      </div>
    </div>
  );
}
