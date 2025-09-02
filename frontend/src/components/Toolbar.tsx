import DateRangePicker from './DateRangePicker'

type Props = {
  start: string
  end: string
  onDateChange: (k:'start'|'end', v:string)=>void
  onExcel: ()=>void
  onPDF: ()=>void
}

export default function Toolbar({ start, end, onDateChange, onExcel, onPDF }: Props){
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 glass-card p-4 text-white">
      <DateRangePicker start={start} end={end} onChange={onDateChange} />
      <div className="flex gap-2">
        <button onClick={onExcel} className="brand-button">Descargar Excel</button>
        <button onClick={onPDF} className="brand-danger">Descargar Gráfico</button>
      </div>
    </div>
  )
}
