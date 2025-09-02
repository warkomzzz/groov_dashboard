// src/components/SensorSelect.tsx
type RealPoint = { ts: string; value: any; type?: string }

type Props = {
  sensors: string[]
  selected: string[]
  onToggle: (name: string) => void
  realtime: Record<string, RealPoint>
  // opciones de orden/agrupado/búsqueda
  filterText: string
  selectedFirst: boolean
  groupByPrefix: boolean
  columns?: number
}

function isOn(v: any): boolean {
  if (typeof v === 'boolean') return v
  const n = Number(v)
  return !Number.isNaN(n) && n > 0
}

function fmtVal(v: any): string {
  const n = Number(v)
  if (!Number.isFinite(n)) return String(v ?? '—')
  return (n >= 0 ? '' : '') + n.toFixed(3)
}

function prefixOf(name: string): string {
  // prefijo por primera palabra antes del guion bajo
  const i = name.indexOf('_')
  return i > 0 ? name.slice(0, i) : name
}

export default function SensorSelect({
  sensors, selected, onToggle, realtime,
  filterText, selectedFirst, groupByPrefix, columns = 4
}: Props) {
  const filter = filterText.trim().toLowerCase()

  // 1) filtrar
  let items = sensors.filter(s => s.toLowerCase().includes(filter))

  // 2) ordenar (seleccionados arriba + alfabético)
  items.sort((a, b) => {
    const sa = selected.includes(a) ? 0 : 1
    const sb = selected.includes(b) ? 0 : 1
    if (selectedFirst && sa !== sb) return sa - sb
    return a.localeCompare(b)
  })

  // 3) opcional: agrupar por prefijo
  let grouped: Record<string, string[]> | null = null
  if (groupByPrefix) {
    grouped = {}
    for (const s of items) {
      const k = prefixOf(s)
      if (!grouped[k]) grouped[k] = []
      grouped[k].push(s)
    }
  }

  const gridClass = `grid gap-2 max-h-80 overflow-auto p-2 border rounded bg-white`
  const colClass  = `grid grid-cols-[auto,1fr,auto] items-center gap-2 px-2 py-1 rounded hover:bg-slate-50`

  // estilos comunes para el “badge” grande
  const badgeBase =
    "inline-flex items-center justify-center min-w-[70px] px-1.5 py-0.5 rounded " +
    "font-semibold text-xs md:text-sm shadow-sm ring-1 tabular-nums tracking-tight"

  function Row({ name }: { name: string }) {
    const r = realtime[name]
    const isDigital = r?.type === 'digital'
    const when = r?.ts ? new Date(r.ts).toLocaleTimeString() : ''

    return (
      <label
        key={name}
        className={colClass}
        title={r?.ts ? `${name} • ${new Date(r.ts).toLocaleString()}` : name}
      >
        <input
          type="checkbox"
          checked={selected.includes(name)}
          onChange={() => onToggle(name)}
        />
        <span className="truncate">
          {name}{' '}
          {when && <span className="text-xs text-slate-500">({when})</span>}
        </span>

        {r ? (
          isDigital ? (
            <span
              className={
                badgeBase +
                ' ' +
                (isOn(r.value)
                  ? 'bg-green-600 text-white ring-green-600'
                  : 'bg-red-600 text-white ring-red-600')
              }
            >
              {isOn(r.value) ? 'ON' : 'OFF'}
            </span>
          ) : (
            <span
              className={
                badgeBase +
                ' bg-blue-100 text-blue-800 ring-blue-300'
              }
            >
              {fmtVal(r.value)}
            </span>
          )
        ) : (
          // Aún sin realtime: muestra un placeholder, no ocultes el sensor
          <span className="text-sm text-slate-400">…</span>
        )}
      </label>
    )
  }

  if (grouped) {
    // render por grupos con títulos “stickies”
    const groups = Object.keys(grouped).sort()
    return (
      <div className={`${gridClass} `}>
        <div
          className={`grid gap-3`}
          style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
        >
          {groups.map(g => (
            <div key={g} className="flex flex-col">
              <div className="text-xs font-semibold text-slate-600 sticky top-0 bg-white/90 backdrop-blur px-1 py-1 rounded">
                {g}
              </div>
              <div className="mt-1 space-y-1">
                {grouped![g].map(name => <Row key={name} name={name} />)}
              </div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  // sin agrupación: rejilla uniforme
  return (
    <div className={`${gridClass}`} >
      <div
        className={`grid gap-2`}
        style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
      >
        {items.map(name => <Row key={name} name={name} />)}
      </div>
    </div>
  )
}
