import React from 'react';
import { CheckCircle2, AlertTriangle, Clock, Shield, Truck } from 'lucide-react';

const LEGEND_ITEMS = [
  { icon: CheckCircle2, label: 'Complete', color: 'text-emerald-500', bg: 'bg-emerald-500/10' },
  { icon: AlertTriangle, label: 'ALS Needed', color: 'text-red-400', bg: 'bg-red-500/10' },
  { icon: Truck, label: 'Driver Needed', color: 'text-amber-400', bg: 'bg-amber-500/10' },
  { icon: AlertTriangle, label: 'Needs Review', color: 'text-violet-400', bg: 'bg-violet-500/10' },
  { icon: Shield, label: 'Structural Coverage', color: 'text-slate-300', bg: 'bg-slate-700/40' },
  { icon: Clock, label: 'Coverage Gap', color: 'text-amber-400', bg: 'bg-amber-500/10' },
];

export default function WallboardLegend() {
  return (
    <div className="flex flex-wrap items-center gap-3 px-4 py-2 border-b border-border/30 bg-muted/30">
      {LEGEND_ITEMS.map(item => (
        <div key={item.label} className="flex items-center gap-1.5">
          <div className={`w-5 h-5 rounded flex items-center justify-center ${item.bg}`}>
            <item.icon className={`w-3 h-3 ${item.color}`} />
          </div>
          <span className="text-[10px] text-muted-foreground font-medium">{item.label}</span>
        </div>
      ))}
    </div>
  );
}