import React, { useState } from 'react';
import { format, addDays, parseISO } from 'date-fns';
import { Copy, Trash2, ChevronDown } from 'lucide-react';
import { getDefaultMemberAvailabilityWeeks, MEMBER_AVAILABILITY_MONTHS_AHEAD } from '@/lib/availabilityRange';

const DEFAULT_MEMBER_AVAILABILITY_WEEKS = getDefaultMemberAvailabilityWeeks();
const DISPLAY_WEEK_OPTIONS = [2, 4, 8, 12, DEFAULT_MEMBER_AVAILABILITY_WEEKS].filter((value, index, list) => list.indexOf(value) === index);

const COPY_WHAT_OPTIONS = [
  'Whole displayed week',
  'Whole Thursday cycle',
  'AM only',
  'PM only',
  'Prefer only',
  'Available only',
];

const TARGET_RANGE_OPTIONS = ['2 weeks', '4 weeks', '8 weeks', 'Through displayed horizon'];

function weekLabel(dateStr) {
  const d = parseISO(dateStr);
  const end = addDays(d, 6);
  return `${format(d, 'MMM d')} – ${format(end, 'MMM d')}`;
}

export default function AvailabilityTools({ displayWeeks, onDisplayWeeksChange, sourceWeekOptions }) {
  const [verboseMode, setVerboseMode] = useState(false);
  const [copySource, setCopySource] = useState(sourceWeekOptions?.[0] || '');
  const [copyWhat, setCopyWhat] = useState('Whole displayed week');
  const [targetRange, setTargetRange] = useState('4 weeks');

  const handleClearForward = () => {
    // Not yet implemented — button is disabled
  };

  const handleCopyForward = () => {
    // Not yet implemented — button is disabled
  };

  const Select = ({ value, onChange, options, className = '' }) => (
    <div className={`relative ${className}`}>
      <select
        value={value}
        onChange={e => onChange(e.target.value)}
        className="w-full appearance-none bg-muted border border-border/60 rounded-lg px-3 py-2 text-xs font-semibold text-foreground pr-7 outline-none cursor-pointer"
      >
        {options.map(o => (
          <option key={String(o)} value={String(o)}>{typeof o === 'number' ? `${o} weeks` : o}</option>
        ))}
      </select>
      <ChevronDown className="w-3 h-3 absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
    </div>
  );

  return (
    <div className="rounded-xl border border-border bg-card overflow-hidden">
      <div className="px-4 py-3 border-b border-border/50 flex items-center justify-between">
        <h3 className="text-sm font-bold text-foreground">Availability Calendar Tools</h3>
        <button
          onClick={() => setVerboseMode(v => !v)}
          className="text-[10px] font-semibold text-primary border border-primary/30 px-2 py-1 rounded-md"
        >
          {verboseMode ? 'Brief Mode' : 'Verbose Mode'}
        </button>
      </div>

      <div className="px-4 py-3 space-y-4">
        {/* Display week control */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="text-xs font-semibold text-foreground">Display week</label>
          </div>
          {verboseMode && (
            <p className="text-[10px] text-muted-foreground mb-2">
              Display week controls what you are looking at. It does not change the time card or copy-forward source.
            </p>
          )}
          <Select
            value={String(displayWeeks)}
            onChange={v => onDisplayWeeksChange(Number(v))}
            options={DISPLAY_WEEK_OPTIONS}
          />
          <p className="text-[10px] text-muted-foreground mt-1">
            Member availability can extend {MEMBER_AVAILABILITY_MONTHS_AHEAD} months ahead and is separate from the Wallboard horizon.
          </p>
        </div>

        {/* Divider */}
        <div className="border-t border-border/40" />

        {/* Clear Forward */}
        <div>
          <button
            onClick={handleClearForward}
            disabled
            className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg bg-muted border border-border/60 text-xs font-semibold text-muted-foreground cursor-not-allowed opacity-60"
          >
            <Trash2 className="w-3.5 h-3.5" />
            Clear from displayed week forward
          </button>
          {verboseMode && (
            <p className="text-[10px] text-muted-foreground mt-1">
              Bulk clear not yet available.
            </p>
          )}
        </div>

        {/* Divider */}
        <div className="border-t border-border/40" />

        {/* Copy Forward */}
        <div className="space-y-3">
          <p className="text-xs font-semibold text-foreground">Copy Availability Forward</p>
          {verboseMode && (
            <p className="text-[10px] text-muted-foreground">
              Copy AM and PM from the selected source week to the selected target range. Blank entries remain blank unless a copy option says otherwise.
            </p>
          )}

          <div className="space-y-2">
            <div>
              <label className="text-[10px] text-muted-foreground mb-1 block">Copy source week</label>
              <Select
                value={copySource}
                onChange={setCopySource}
                options={sourceWeekOptions?.length ? sourceWeekOptions : ['—']}
              />
            </div>

            <div>
              <label className="text-[10px] text-muted-foreground mb-1 block">What to copy</label>
              <Select value={copyWhat} onChange={setCopyWhat} options={COPY_WHAT_OPTIONS} />
            </div>

            <div>
              <label className="text-[10px] text-muted-foreground mb-1 block">Target range</label>
              <Select value={targetRange} onChange={setTargetRange} options={TARGET_RANGE_OPTIONS} />
            </div>
          </div>

          <button
            onClick={handleCopyForward}
            disabled
            className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg bg-muted border border-border/60 text-xs font-semibold text-muted-foreground cursor-not-allowed opacity-60"
          >
            <Copy className="w-3.5 h-3.5" />
            Copy Forward (coming soon)
          </button>
        </div>
      </div>
    </div>
  );
}
