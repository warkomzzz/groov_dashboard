type Row = { ts: string; value: number; device_ip: string; endpoint: string; type: string; name?: string }

export default function TableCard({ rows }: { rows: Row[] }){
  return (
    <div className="bg-white rounded-2xl shadow p-4 overflow-auto">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="text-left border-b">
            <th className="py-2">Fecha</th>
            <th>Sensor</th>
            <th>Valor</th>
            <th>IP</th>
            <th>Tipo</th>
            <th>EP</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i)=> (
            <tr key={i} className="border-b last:border-0">
              <td className="py-1">{new Date(r.ts).toLocaleString()}</td>
              <td>{r.name || ''}</td>
              <td>{typeof r.value==='number'? r.value.toFixed(3): String(r.value)}</td>
              <td>{r.device_ip}</td>
              <td>{r.type}</td>
              <td>{r.endpoint}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
