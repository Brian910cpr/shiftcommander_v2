import React, { useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { useScheduleData } from '@/lib/useScheduleData';
import { format, parseISO } from 'date-fns';
import { AlertCircle } from 'lucide-react';

export default function OpenSeatsPanel({ shifts: propShifts }) {
  const { shifts: hookShifts } = useScheduleData();
  const shifts = propShifts || hookShifts;
  const openSeats = useMemo(() => {
    const seats = [];
    if (!shifts) return seats;
    shifts.forEach(s => {
      if (s.attendant?.status === 'OPEN') {
        seats.push({
          date: s.date,
          label: s.label,
          role: 'Attendant/ALS',
          name: s.attendant.name,
          review: s.supervisor_review,
        });
      }
      if (s.driver?.status === 'OPEN') {
        seats.push({
          date: s.date,
          label: s.label,
          role: 'Driver/EMT',
          name: s.driver.name,
          review: s.supervisor_review,
        });
      }
    });
    return seats.sort((a, b) => a.date.localeCompare(b.date));
  }, [shifts]);

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm">Open Seats</CardTitle>
          <Badge variant="outline" className="text-[10px] bg-red-500/10 text-red-400 border-red-500/20">
            {openSeats.length} open
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        {openSeats.length === 0 ? (
          <p className="text-xs text-muted-foreground text-center py-4">All seats filled</p>
        ) : (
          <div className="space-y-1 max-h-[300px] overflow-y-auto pr-1">
            {openSeats.map((seat, idx) => {
              const d = parseISO(seat.date);
              return (
                <div
                  key={idx}
                  className="flex items-center justify-between px-2.5 py-2 rounded-lg bg-muted/50 border border-border/30"
                >
                  <div className="flex items-center gap-2">
                    <AlertCircle className="w-3.5 h-3.5 text-red-400" />
                    <div>
                      <span className="text-xs font-medium text-foreground">
                        {format(d, 'EEE MMM d')} · {seat.label}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <Badge variant="outline" className="text-[9px]">
                      {seat.role}
                    </Badge>
                    {seat.review && (
                      <Badge variant="outline" className="text-[9px] bg-violet-500/10 text-violet-400 border-violet-500/20">
                        Review
                      </Badge>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}