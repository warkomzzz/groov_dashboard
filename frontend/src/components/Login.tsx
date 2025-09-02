import { useState } from 'react';
import { login } from '../lib/api';

export default function Login({ onLoggedIn }: { onLoggedIn: (role: string) => void }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading,  setLoading ] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await login(username.trim(), password);
      onLoggedIn(res.role);
    } catch {
      alert('Usuario o contraseña inválidos');
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="max-w-md mx-auto p-6 bg-white rounded shadow">
      <h2 className="text-xl font-bold mb-4">Iniciar sesión</h2>
      <label className="block text-sm mb-1">Usuario</label>
      <input className="w-full border rounded px-3 py-2 mb-3"
        value={username} onChange={e => setUsername(e.target.value)} placeholder="admin o produccion" />
      <label className="block text-sm mb-1">Contraseña</label>
      <input className="w-full border rounded px-3 py-2 mb-4" type="password"
        value={password} onChange={e => setPassword(e.target.value)} />
      <button disabled={loading} className="w-full bg-sky-700 hover:bg-sky-800 text-white font-semibold rounded py-2">
        {loading ? 'Ingresando…' : 'Entrar'}
      </button>
    </form>
  );
}
