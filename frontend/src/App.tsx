// src/App.tsx
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  fetchSensors,
  fetchMeasurements,
  exportExcel,
  exportPDF,
  fetchRealtime,
  RealPoint,
  me,
} from './lib/api';
import SensorSelect from './components/SensorSelect';
import ChartCard from './components/ChartCard';
import TableCard from './components/TableCard';
import Toolbar from './components/Toolbar';
import Login from './components/Login';
import { getToken, clearToken } from './lib/auth';
import './styles.css';
import ThemeToggle from './components/ThemeToggle';

type Role = 'admin' | 'user';

export default function App() {
  // State base
  const [authed, setAuthed] = useState(false);
  const [role, setRole] = useState<Role | null>(null);
  const [bootErr, setBootErr] = useState<string | null>(null);

  const [sensors, setSensors] = useState<string[]>([]);
  const [sel, setSel] = useState<string[]>([]);
  const [start, setStart] = useState<string>('');
  const [end, setEnd] = useState<string>('');
  const [series, setSeries] = useState<Record<string, any[]>>({});
  const [realtime, setRealtime] = useState<Record<string, RealPoint>>({});

  const [filterText, setFilterText] = useState('');
  const [selectedFirst, setSelectedFirst] = useState(true);
  const [groupByPrefix, setGroupByPrefix] = useState(true);
  // Evita re-autoselección automática tras interacción del usuario
  const didAutoSelectRef = useRef(false);

  // Heurística para clasificar mientras no llega realtime
  const guessType = (name: string): 'analog' | 'digital' => {
    const digitalPrefixes = ['FALLA_', 'FUNCIONANDO_', 'PARADA_', 'ALARM', 'SELECTOR_', 'BB', 'BBA', 'NO_FUNCIONA', 'N0_FUNCA'];
    return digitalPrefixes.some((p) => name.startsWith(p)) ? 'digital' : 'analog';
  };

  // Boot: validar sesión si hay token
  useEffect(() => {
    let alive = true;
    (async () => {
      if (!getToken()) {
        if (!alive) return;
        setAuthed(false);
        setRole(null);
        return;
      }
      try {
        const info = await me();
        if (!alive) return;
        setRole(info.role as Role);
        setAuthed(true);
      } catch {
        if (!alive) return;
        setBootErr('No se pudo validar la sesión. Inicia sesión nuevamente.');
        setAuthed(false);
        setRole(null);
        clearToken();
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  // Cargar sensores al autenticarse
  useEffect(() => {
    let mounted = true;
    if (!authed) return;
    (async () => {
      try {
        const items = await fetchSensors();
        if (mounted) setSensors(items);
      } catch {
        setBootErr('No se pudieron cargar datos (revisa backend y CORS).');
      }
    })();
    return () => {
      mounted = false;
    };
  }, [authed]);

  // --------- POLLING DE TIEMPO REAL ----------
  // Estrategia por lotes:
  //  - Pedimos SIEMPRE los seleccionados en cada tick (para gráficos).
  //  - Además, pedimos un lote rotativo de los NO seleccionados para ir
  //    completando y refrescando toda la parrilla sin saturar el backend.
  //  - Se mantiene backoff progresivo y revalidación en 401.
  const pollAbortRef = useRef<AbortController | null>(null);
  const isPollingRef = useRef(false);
  const batchCursorRef = useRef(0);

  useEffect(() => {
    if (!authed || sensors.length === 0) return;
    // Solo admins ven/usan tiempo real
    if (role !== 'admin') return;

    let alive = true;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let delay = 1200;           // ms entre ticks (se adapta con éxito/errores)
    const minDelay = 800;
    const maxDelay = 8000;
    const BATCH = 60;           // tamaño del lote para NO seleccionados

    const tick = async () => {
      if (!alive) return;
      if (isPollingRef.current) {
        timer = setTimeout(tick, delay);
        return;
      }
      isPollingRef.current = true;
      // Construye el lote rotativo
      const selSet = new Set(sel);
      const nonSelected = sensors.filter(s => !selSet.has(s));

      // Cursor y rebanada del lote
      let startIdx = batchCursorRef.current;
      if (startIdx >= nonSelected.length) startIdx = 0;
      const endIdx = Math.min(startIdx + BATCH, nonSelected.length);
      const batch = nonSelected.slice(startIdx, endIdx);
      batchCursorRef.current = endIdx; // avanza para el siguiente tick

      // Nombres a consultar en este tick
      let namesToAsk: string[] = [];
      if (sel.length > 0) namesToAsk.push(...sel);
      if (batch.length > 0) namesToAsk.push(...batch);
      if (namesToAsk.length === 0 && sensors.length > 0) {
        // caso especial: no hay seleccionados ni lote (pocos sensores)
        namesToAsk = sensors.slice(0, Math.min(BATCH, sensors.length));
      }

      // Abortar request anterior si quedara viva
      if (pollAbortRef.current) pollAbortRef.current.abort();
      const ac = new AbortController();
      pollAbortRef.current = ac;

      try {
        const data = await fetchRealtime(namesToAsk, ac.signal);
        if (!alive) return;

        // Fusión incremental: sólo se pisan las claves recibidas en este tick
        setRealtime(prev => ({ ...prev, ...(data || {}) }));
        setBootErr(null);

        // Ajusta backoff: éxito => baja
        delay = Math.max(minDelay, Math.floor(delay * 0.85));
      } catch (e: any) {
        // Ignorar abortos intencionales del fetch al reiniciar el tick
        if (e?.code === 'ERR_CANCELED' || e?.name === 'CanceledError' || String(e?.message || '').toLowerCase().includes('cancel')) {
          // no marcar degradación
          isPollingRef.current = false;
          if (alive) timer = setTimeout(tick, delay);
          return;
        }
        const status = e?.response?.status;
        if (status === 401) {
          // Revalida sesión
          try {
            await me();
          } catch {
            if (alive) {
              setAuthed(false);
              setRole(null);
              clearToken();
              setBootErr('Sesión expirada. Inicia sesión nuevamente.');
            }
            isPollingRef.current = false;
            return;
          }
        }
        if (alive) setBootErr('Tiempo real degradado (red/servidor). Reintentando…');
        delay = Math.min(maxDelay, Math.floor(delay * 1.6));
      } finally {
        isPollingRef.current = false;
      }

      if (alive) timer = setTimeout(tick, delay);
    };

    // primer disparo
    timer = setTimeout(tick, 150);

    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
      if (pollAbortRef.current) pollAbortRef.current.abort();
    };
  }, [authed, role, sensors, sel]);

  // Series históricas (para gráficos)
  useEffect(() => {
    let cancelled = false;
    if (!authed) return;
    // Solo admins consultan series para gráficos/tabla
    if (role !== 'admin') return;
    if (sel.length === 0) {
      setSeries({});
      return;
    }

    (async () => {
      const next: Record<string, any[]> = {};
      for (const s of sel) {
        try {
          const data = await fetchMeasurements(
            s,
            start ? new Date(start).toISOString() : undefined,
            end ? new Date(end).toISOString() : undefined
          );
          next[s] = data.map((d) => ({
            ts: d.ts,
            value: d.value,
            device_ip: d.device_ip,
            endpoint: d.endpoint,
            type: d.type,
          }));
        } catch {
          // seguimos con los demás
        }
      }
      if (!cancelled) setSeries(next);
    })();

    return () => {
      cancelled = true;
    };
  }, [authed, role, sel, start, end]);

  // Listas usando realtime si existe; si no, heurística
  const analogList = useMemo(
    () => sensors.filter((s) => (realtime[s]?.type ?? guessType(s)) === 'analog'),
    [sensors, realtime]
  );
  const digitalList = useMemo(
    () => sensors.filter((s) => (realtime[s]?.type ?? guessType(s)) === 'digital'),
    [sensors, realtime]
  );

  // No autoseleccionar sensores al iniciar

  // Al cerrar sesión, permitir que se vuelva a autoseleccionar en el próximo login
  useEffect(() => {
    if (!authed) {
      didAutoSelectRef.current = false;
    }
  }, [authed]);

  // Tabla
  const rows = useMemo(() => {
    const arr: any[] = [];
    Object.entries(series).forEach(([name, data]) =>
      data.forEach((p: any) => arr.push({ name, ...p }))
    );
    return arr.sort((a, b) => new Date(a.ts).getTime() - new Date(b.ts).getTime());
  }, [series]);

  // Render
  if (!authed) {
    return (
      <Login
        onLoggedIn={(r) => {
          setRole(r as Role);
          setAuthed(true);
          setBootErr(null);
        }}
      />
    );
  }

  // Vista restringida para rol "user": solo selección + descargas
  if (role === 'user') {
    return (
      <div className="min-h-screen brand-gradient brand-surface">
        <ThemeToggle />
        {bootErr && (
          <div className="bg-yellow-100/90 text-yellow-900 px-4 py-2 text-sm">{bootErr}</div>
        )}

        <div className="max-w-7xl mx-auto p-4 space-y-4">
          <div className="flex items-center justify-between gap-4">
            <h1 className="text-2xl font-bold">Descargas — Groov EPIC</h1>
            <button
              onClick={() => {
                clearToken();
                setAuthed(false);
                setRole(null);
                setSel([]);
                setSeries({});
                setRealtime({});
                setBootErr(null);
              }}
              className="text-sm brand-danger"
              title="Cerrar sesión"
            >
              Cerrar sesión
            </button>
          </div>

          <Toolbar
            start={start}
            end={end}
            onDateChange={(k, v) => (k === 'start' ? setStart(v) : setEnd(v))}
            onExcel={() =>
              exportExcel(
                sel,
                start ? new Date(start).toISOString() : undefined,
                end ? new Date(end).toISOString() : undefined
              )
            }
            onPDF={() =>
              exportPDF(
                sel,
                start ? new Date(start).toISOString() : undefined,
                end ? new Date(end).toISOString() : undefined
              )
            }
          />

          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              <span className="text-sm text-slate-700">Buscar</span>
              <input
                value={filterText}
                onChange={(e) => setFilterText(e.target.value)}
                placeholder="Nombre del sensor…"
                className="border rounded px-2 py-1"
                style={{ minWidth: 260 }}
              />
            </div>

            <label className="text-sm flex items-center gap-2">
              <input
                type="checkbox"
                checked={selectedFirst}
                onChange={(e) => setSelectedFirst(e.target.checked)}
              />
              Seleccionados primero
            </label>

            <label className="text-sm flex items-center gap-2">
              <input
                type="checkbox"
                checked={groupByPrefix}
                onChange={(e) => setGroupByPrefix(e.target.checked)}
              />
              Agrupar por prefijo
            </label>
          </div>

          <div className="space-y-2">
            <h2 className="font-semibold">Sensores Analógicos</h2>
            <SensorSelect
              sensors={analogList}
              selected={sel}
              onToggle={(n) =>
                setSel((curr) => (curr.includes(n) ? curr.filter((x) => x !== n) : [...curr, n]))
              }
              realtime={{}}
              filterText={filterText}
              selectedFirst={selectedFirst}
              groupByPrefix={groupByPrefix}
              columns={3}
              showRealtime={false}
            />

            <h2 className="font-semibold mt-4">Sensores Digitales</h2>
            <SensorSelect
              sensors={digitalList}
              selected={sel}
              onToggle={(n) =>
                setSel((curr) => (curr.includes(n) ? curr.filter((x) => x !== n) : [...curr, n]))
              }
              realtime={{}}
              filterText={filterText}
              selectedFirst={selectedFirst}
              groupByPrefix={groupByPrefix}
              columns={3}
              showRealtime={false}
            />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen brand-gradient brand-surface">
      <ThemeToggle />
      {bootErr && (
        <div className="bg-yellow-100/90 text-yellow-900 px-4 py-2 text-sm">{bootErr}</div>
      )}

      <div className="max-w-7xl mx-auto p-4 space-y-4">
        <div className="flex items-center justify-between gap-4">
          <h1 className="text-2xl font-bold">Dashboard — INGELSA</h1>
          <button
            onClick={() => {
              clearToken();
              setAuthed(false);
              setRole(null);
              setSel([]);
              setSeries({});
              setRealtime({});
              setBootErr(null);
            }}
            className="text-sm brand-danger"
            title="Cerrar sesión"
          >
            Cerrar sesión
          </button>
        </div>

        <Toolbar
          start={start}
          end={end}
          onDateChange={(k, v) => (k === 'start' ? setStart(v) : setEnd(v))}
          onExcel={() =>
            exportExcel(
              sel,
              start ? new Date(start).toISOString() : undefined,
              end ? new Date(end).toISOString() : undefined
            )
          }
          onPDF={() =>
            exportPDF(
              sel,
              start ? new Date(start).toISOString() : undefined,
              end ? new Date(end).toISOString() : undefined
            )
          }
        />

        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-full bg-white/10 text-white/90 text-xs font-semibold tracking-wide">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="11" cy="11" r="8"/>
                <path d="M21 21l-3.5-3.5"/>
              </svg>
              Buscar
            </span>
            <input
              value={filterText}
              onChange={(e) => setFilterText(e.target.value)}
              placeholder="Nombre del sensor…"
              className="glass-input"
              style={{ minWidth: 260 }}
            />
          </div>

          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={selectedFirst}
              onChange={(e) => setSelectedFirst(e.target.checked)}
            />
            Seleccionados primero
          </label>

          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={groupByPrefix}
              onChange={(e) => setGroupByPrefix(e.target.checked)}
            />
            Agrupar por prefijo
          </label>
        </div>

        <div className="space-y-2">
          <h2 className="font-semibold">Sensores Analógicos</h2>
          <SensorSelect
            sensors={analogList}
            selected={sel}
            onToggle={(n) =>
              setSel((curr) => (curr.includes(n) ? curr.filter((x) => x !== n) : [...curr, n]))
            }
            realtime={realtime}
            filterText={filterText}
            selectedFirst={selectedFirst}
            groupByPrefix={groupByPrefix}
            columns={3}
          />

          <h2 className="font-semibold mt-4">Sensores Digitales</h2>
          <SensorSelect
            sensors={digitalList}
            selected={sel}
            onToggle={(n) =>
              setSel((curr) => (curr.includes(n) ? curr.filter((x) => x !== n) : [...curr, n]))
            }
            realtime={realtime}
            filterText={filterText}
            selectedFirst={selectedFirst}
            groupByPrefix={groupByPrefix}
            columns={3}
          />
        </div>

        <div className="grid md:grid-cols-2 gap-4">
          {sel.map((name) => (
            <ChartCard key={name} title={name} data={series[name] || []} />
          ))}
        </div>

        <TableCard rows={rows} />
      </div>
    </div>
  );
}
