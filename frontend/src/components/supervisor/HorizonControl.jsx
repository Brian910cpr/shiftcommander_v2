import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Calendar, Lock, RefreshCw, Save } from 'lucide-react';
import { toast } from 'sonner';

export default function HorizonControl({ settings, onSave }) {
  const [mode, setMode] = useState(settings?.horizon_mode || 'frozen');
  const [frozenDate, setFrozenDate] = useState(settings?.horizon_frozen_date || '2026-06-30');
  const [rollingWeeks, setRollingWeeks] = useState(settings?.horizon_rolling_weeks || 5);

  const handleSave = () => {
    onSave({ horizon_mode: mode, horizon_frozen_date: frozenDate, horizon_rolling_weeks: rollingWeeks });
    toast.success('Horizon settings saved');
  };

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Calendar className="w-4 h-4 text-primary" />
            <CardTitle className="text-sm">Display Horizon</CardTitle>
          </div>
          <Badge variant="outline" className="text-[10px] font-mono">
            {mode === 'frozen' ? `Through ${frozenDate}` : `${rollingWeeks} weeks`}
          </Badge>
        </div>
        <p className="text-xs text-muted-foreground">
          Controls how far ahead the schedule is shown.
        </p>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-2 gap-2">
          <Button
            variant={mode === 'frozen' ? 'default' : 'outline'}
            size="sm"
            className="text-xs"
            onClick={() => setMode('frozen')}
          >
            <Lock className="w-3 h-3 mr-1.5" />
            Freeze Through Jun 30
          </Button>
          <Button
            variant={mode === 'rolling' ? 'default' : 'outline'}
            size="sm"
            className="text-xs"
            onClick={() => setMode('rolling')}
          >
            <RefreshCw className="w-3 h-3 mr-1.5" />
            Rolling Horizon
          </Button>
        </div>

        {mode === 'frozen' && (
          <div className="space-y-1">
            <label className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">
              Show through date
            </label>
            <Input
              type="date"
              value={frozenDate}
              onChange={e => setFrozenDate(e.target.value)}
              className="text-xs h-8"
            />
          </div>
        )}

        {mode === 'rolling' && (
          <div className="space-y-1">
            <label className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">
              Rolling weeks
            </label>
            <Input
              type="number"
              min={1}
              max={12}
              value={rollingWeeks}
              onChange={e => setRollingWeeks(parseInt(e.target.value) || 5)}
              className="text-xs h-8 w-20"
            />
          </div>
        )}

        <Button size="sm" className="w-full text-xs" onClick={handleSave}>
          <Save className="w-3 h-3 mr-1.5" />
          Save Horizon
        </Button>
      </CardContent>
    </Card>
  );
}