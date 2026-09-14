'use client'

interface GraphFiltersProps {
  entitySearch: string
  onEntitySearchChange: (v: string) => void
  depth: number
  onDepthChange: (v: number) => void
  relationshipTypes: string[]
  onRelationshipTypesChange: (v: string[]) => void
  onApply: () => void
}

const REL_TYPES = ['CALLED', 'TRANSFERRED_TO', 'USED_DEVICE', 'CONNECTED_TO_TOWER']

export default function GraphFilters({
  entitySearch,
  onEntitySearchChange,
  depth,
  onDepthChange,
  relationshipTypes,
  onRelationshipTypesChange,
  onApply,
}: GraphFiltersProps) {
  const toggleRel = (rel: string) => {
    onRelationshipTypesChange(
      relationshipTypes.includes(rel)
        ? relationshipTypes.filter((r) => r !== rel)
        : [...relationshipTypes, rel]
    )
  }

  return (
    <div className="p-3 space-y-4 text-xs">
      {/* Entity Search */}
      <div>
        <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block mb-1.5">
          Entity Search
        </label>
        <input
          value={entitySearch}
          onChange={(e) => onEntitySearchChange(e.target.value)}
          placeholder="+91 98XXXXXX12 or account@upi"
          className="w-full bg-[#070D14] border border-brand-border rounded px-2.5 py-1.5 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-brand-cyan focus:ring-1 focus:ring-brand-cyan"
        />
      </div>

      {/* Depth */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
            Radial Hops
          </label>
          <span className="text-[10px] text-brand-cyan font-mono">{depth} Hops</span>
        </div>
        <div className="grid grid-cols-3 gap-1 p-0.5 bg-[#070D14] rounded border border-brand-border">
          {[1, 2, 3].map((d) => (
            <button
              key={d}
              onClick={() => onDepthChange(d)}
              className={`py-1 text-center rounded text-[11px] transition ${
                depth === d
                  ? 'bg-brand-cyan text-black font-semibold'
                  : 'text-slate-400 hover:text-white hover:bg-slate-800'
              }`}
            >
              {d} Hop
            </button>
          ))}
        </div>
      </div>

      {/* Relationship types */}
      <div>
        <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block mb-1.5">
          Relationship Types
        </label>
        <div className="space-y-1">
          {REL_TYPES.map((rel) => (
            <label key={rel} className="flex items-center gap-2 hover:bg-slate-800/40 px-2 py-1 rounded cursor-pointer">
              <input
                type="checkbox"
                checked={relationshipTypes.includes(rel)}
                onChange={() => toggleRel(rel)}
                className="rounded bg-slate-900 border-slate-700 text-brand-cyan focus:ring-0"
              />
              <span className="text-slate-300 text-[11px]">{rel.replace(/_/g, ' ')}</span>
            </label>
          ))}
        </div>
      </div>

      {/* Apply */}
      <button
        onClick={onApply}
        className="w-full py-2 bg-brand-cyan/15 hover:bg-brand-cyan/25 border border-brand-cyan/40 text-brand-cyan text-xs font-semibold rounded transition"
      >
        Apply Filters
      </button>

      {/* Legend */}
      <div className="pt-2 border-t border-slate-800/80">
        <div className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-2">Entity Legend</div>
        <div className="space-y-1.5">
          {[
            { color: 'bg-brand-green',  label: 'Phone' },
            { color: 'bg-brand-amber',  label: 'Account' },
            { color: 'bg-brand-cyan',   label: 'Device' },
            { color: 'bg-slate-400',    label: 'Tower' },
            { color: 'bg-brand-purple', label: 'Document' },
          ].map(({ color, label }) => (
            <div key={label} className="flex items-center gap-2">
              <span className={`w-2.5 h-2.5 rounded-full ${color}`} />
              <span className="text-[11px] text-slate-300">{label}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
