import React, { useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useScheduleData, getCrewStatusType } from '@/lib/useScheduleData';
import { CheckCircle2, AlertTriangle, Truck, Eye } from 'lucide-react';

export default function StaffingSummary({ shifts: propShifts }) {
  const { shifts: hookShifts } = useScheduleData();
  const shifts = propShifts || hookShifts;
  const stats = useMemo(() => {
    let total = 0, complete = 0, needsAls = 0, needsDriver = 0, needsReview = 0;
    shifts.forEach(s => {
      total++;
      const type = getCrewStatusType(s.crew_status);
      if (type === 'complete') complete++;
      else if (type === 'open-als') needsAls++;
      else if (type === 'open-driver') needsDriver++;
      else if (type === 'review') needsReview++;
    });
    return { total, complete, needsAls, needsDriver, needsReview };
  }, [shifts]);

  const items = [
    { label: 'Total Shifts', value: stats.total, icon: Eye, color: 'text-foreground' },
    { label: 'Complete', value: stats.complete, icon: CheckCircle2, color: 'text-emerald-500' },
    { label: 'Need ALS', value: stats.needsAls, icon: AlertTriangle, color: 'text-red-400' },
    { label: 'Need Driver', value: stats.needsDriver, icon: Truck, color: 'text-amber-400' },
    { label: 'Need Review', value: stats.needsReview, icon: AlertTriangle, color: 'text-violet-400' },
  ];

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">Staffing Overview</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-5 gap-2">
          {items.map(item => (
            <div key={item.label} className="text-center space-y-1">
              <item.icon className={`w-4 h-4 mx-auto ${item.color}`} />
              <div className="text-xl font-bold tabular-nums text-foreground">{item.value}</div>
              <div className="text-[9px] uppercase tracking-wider text-muted-foreground font-medium">{item.label}</div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}