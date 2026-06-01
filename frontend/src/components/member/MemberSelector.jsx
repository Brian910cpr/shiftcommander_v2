import React from 'react';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { User } from 'lucide-react';

export default function MemberSelector({ selectedId, onSelect, members = [] }) {
  return (
    <div className="space-y-2">
      <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
        <User className="w-3.5 h-3.5" />
        Select Member
      </label>
      <Select value={selectedId} onValueChange={onSelect}>
        <SelectTrigger className="w-full bg-card">
          <SelectValue placeholder="Choose a member..." />
        </SelectTrigger>
        <SelectContent>
          {members.map(m => (
            <SelectItem key={m.id} value={m.id}>
              <div className="flex items-center gap-2">
                <span>{m.name}</span>
                <Badge variant="outline" className="text-[10px] font-mono">
                  {m.cert}
                </Badge>
              </div>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}