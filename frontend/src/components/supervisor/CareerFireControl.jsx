import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Shield, Save, X } from 'lucide-react';
import { toast } from 'sonner';

const ALL_DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'];

export default function CareerFireControl({ settings, onSave }) {
  const [days, setDays] = useState(settings?.career_fire_days || ['Mon', 'Tue', 'Thu']);
  const [startTime, setStartTime] = useState(settings?.career_fire_start_time || '0800');
  const [endTime, setEndTime] = useState(settings?.career_fire_end_time || '1800');

  const toggleDay = (day) => {
    setDays(prev => prev.includes(day) ? prev.filter(d => d !== day) : [...prev, day]);
  };

  const handleSave = () => {
    onSave({ career_fire_days: days, career_fire_start_time: startTime, career_fire_end_time: endTime });
    toast.success('Career Fire Driver settings saved');
  };

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Shield className="w-4 h-4 text-primary" />
            <CardTitle className="text-sm">Career Fire Driver</CardTitle>
          </div>
          <Badge variant="outline" className="text-[10px] font-mono bg-slate-700/10">
            {days.join(' · ')} {startTime}–{endTime}
          </Badge>
        </div>
        <p className="text-xs text-muted-foreground">
          Marks daytime EMT/driver coverage from Career Fire.
        </p>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Day Selectors */}
        <div className="space-y-1">
          <label className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">
            Active Days
          </label>
          <div className="flex gap-1.5">
            {ALL_DAYS.map(day => (
              <button
                key={day}
                onClick={() => toggleDay(day)}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                  days.includes(day)
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-muted text-muted-foreground hover:bg-muted/80'
                }`}
              >
                {day}
              </button>
            ))}
          </div>
        </div>

        {/* Quick Presets */}
        <div className="flex gap-1.5">
          <Button variant="outline" size="sm" className="text-[10px] h-7" onClick={() => setDays(['Mon', 'Tue', 'Thu'])}>
            Standard M/T/Th
          </Button>
          <Button variant="outline" size="sm" className="text-[10px] h-7" onClick={() => setDays([...ALL_DAYS])}>
            All Weekdays
          </Button>
          <Button variant="outline" size="sm" className="text-[10px] h-7" onClick={() => setDays([])}>
            <X className="w-3 h-3 mr-1" />
            Clear
          </Button>
        </div>

        {/* Time Range */}
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <label className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">
              Start Time
            </label>
            <Input
              value={startTime}
              onChange={e => setStartTime(e.target.value)}
              className="text-xs h-8 font-mono"
              placeholder="0800"
            />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">
              End Time
            </label>
            <Input
              value={endTime}
              onChange={e => setEndTime(e.target.value)}
              className="text-xs h-8 font-mono"
              placeholder="1800"
            />
          </div>
        </div>

        <Button size="sm" className="w-full text-xs" onClick={handleSave}>
          <Save className="w-3 h-3 mr-1.5" />
          Save Coverage
        </Button>
      </CardContent>
    </Card>
  );
}