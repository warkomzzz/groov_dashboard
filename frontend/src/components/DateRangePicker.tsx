
type Props = {
  start: string
  end: string
  onChange: (k: 'start'|'end', v: string) => void
}

export default function DateRangePicker({ start, end, onChange }: Props) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <label className="text-sm text-white/90">Desde</label>
      <input type="datetime-local" value={start} onChange={e=>onChange('start', e.target.value)} className="glass-input py-1.5"/>
      <label className="text-sm text-white/90">Hasta</label>
      <input type="datetime-local" value={end} onChange={e=>onChange('end', e.target.value)} className="glass-input py-1.5"/>
    </div>
  )
}
