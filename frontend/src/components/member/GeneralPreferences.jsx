import React, { useState } from 'react';
import { toast } from 'sonner';
import { Save } from 'lucide-react';

const HOURS_OPTIONS = ['16', '24', '32', '36', '40', '48', '56'];
const DAY_NIGHT_OPTIONS = [
  'I prefer day shifts',
  'I prefer night shifts',
  'I am willing to work either',
];
const HOUR_PREF_OPTIONS = [
  'I prefer 8-hour shifts',
  'I prefer 12-hour shifts',
  'I prefer 24-hour shifts',
  'No preference',
];
const NOTICE_OPTIONS = [
  'I want open-shift notices',
  'I do not want open-shift notices',
];

export default function GeneralPreferences() {
  const [desiredHours, setDesiredHours] = useState('36');
  const [dayNight, setDayNight] = useState('I am willing to work either');
  const [hourPref, setHourPref] = useState('I prefer 12-hour shifts');
  const [notices, setNotices] = useState('I want open-shift notices');
  const [dirty, setDirty] = useState(false);

  const mark = setter => val => { setter(val); setDirty(true); };

  const handleSave = () => {
    toast.warning('General Preferences are not saved yet. Backend preference persistence is not wired.', { duration: 5000 });
  };

  const Row = ({ label, value, onChange, options }) => (
    <div className="flex items-center justify-between py-3 border-b border-border/40 last:border-0">
      <span className="text-sm text-muted-foreground flex-shrink-0 w-40">{label}</span>
      <select
        value={value}
        onChange={e => onChange(e.target.value)}
        className="flex-1 text-sm font-semibold text-foreground bg-transparent text-right outline-none cursor-pointer"
      >
        {options.map(o => <option key={o} value={o}>{o}</option>)}
      </select>
    </div>
  );

  return (
    <div className="rounded-xl border border-border bg-card">
      <div className="px-4 py-3 border-b border-border/50">
        <h3 className="text-sm font-bold text-foreground">General Preferences</h3>
        <p className="text-[10px] text-muted-foreground mt-0.5">Pre-beta — controls visible, backend write not yet available.</p>
      </div>
      <div className="px-4">
        <Row label="Desired Hours / Week" value={desiredHours} onChange={mark(setDesiredHours)} options={HOURS_OPTIONS} />
        <Row label="Day / Night Preference" value={dayNight} onChange={mark(setDayNight)} options={DAY_NIGHT_OPTIONS} />
        <Row label="24-hour Preference" value={hourPref} onChange={mark(setHourPref)} options={HOUR_PREF_OPTIONS} />
        <Row label="Open-shift Notices" value={notices} onChange={mark(setNotices)} options={NOTICE_OPTIONS} />
      </div>
      <div className="px-4 py-3 border-t border-border/50">
        <button
          onClick={handleSave}
          disabled
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-colors ${
            dirty
              ? 'bg-muted text-muted-foreground cursor-not-allowed'
              : 'bg-muted text-muted-foreground cursor-default'
          }`}
          title="General Preferences are display-only until a backend preference endpoint is added."
        >
          <Save className="w-3.5 h-3.5" />
          Preferences not saved yet
        </button>
      </div>
    </div>
  );
}
