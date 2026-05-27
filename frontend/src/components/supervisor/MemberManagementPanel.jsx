import React, { useMemo, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { AlertCircle, Search, Save, SlidersHorizontal, UserCog } from 'lucide-react';

const ALL = 'all';

function normalize(value) {
  return String(value || '').trim().toLowerCase();
}

function uniqueValues(members, getter) {
  return Array.from(new Set((members || []).map(getter).filter(Boolean))).sort((a, b) =>
    String(a).localeCompare(String(b)),
  );
}

function memberSearchText(member) {
  return [
    member.id,
    member.name,
    member.short_name,
    member.email,
    member.google_email,
    member.auth_email,
    member.role,
    member.cert,
    member.employment_type,
    ...(member.roles || []),
    ...(member.qualifications || []),
    member.canDrive ? 'driver can drive eligible' : 'non driver',
    member.supervisor ? 'supervisor' : '',
    member.admin ? 'admin' : '',
    member.active ? 'active' : 'inactive',
  ].join(' ');
}

function EditableMemberRow({ member }) {
  const [draft, setDraft] = useState({
    role: member.role || '',
    cert: member.cert || '',
    active: member.active ? 'active' : 'inactive',
    canDrive: member.canDrive ? 'yes' : 'no',
    supervisor: member.supervisor ? 'yes' : 'no',
    admin: member.admin ? 'yes' : 'no',
  });

  const dirty = Object.entries(draft).some(([key, value]) => {
    if (key === 'active') return value !== (member.active ? 'active' : 'inactive');
    if (key === 'canDrive') return value !== (member.canDrive ? 'yes' : 'no');
    if (key === 'supervisor') return value !== (member.supervisor ? 'yes' : 'no');
    if (key === 'admin') return value !== (member.admin ? 'yes' : 'no');
    return value !== String(member[key] || '');
  });

  return (
    <div className="grid grid-cols-[minmax(190px,1.4fr)_repeat(5,minmax(104px,0.75fr))_minmax(130px,0.8fr)] gap-2 items-center px-3 py-2 rounded-lg border border-border/30 bg-background/60">
      <div className="min-w-0">
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-semibold text-sm text-foreground truncate">{member.name}</span>
          <Badge variant="outline" className="text-[10px] font-mono">{member.id || 'no-id'}</Badge>
        </div>
        <div className="mt-1 flex flex-wrap gap-1.5 text-[10px] text-muted-foreground">
          {member.email && <span className="truncate max-w-[170px]">{member.email}</span>}
          {member.employment_type && <Badge variant="outline" className="text-[9px]">{member.employment_type}</Badge>}
          {member.qrv_certified && <Badge variant="outline" className="text-[9px]">QRV</Badge>}
          {member.preferences?.shift_preference?.style && (
            <Badge variant="outline" className="text-[9px]">{member.preferences.shift_preference.style}</Badge>
          )}
        </div>
      </div>

      <Input
        value={draft.role}
        onChange={(event) => setDraft(prev => ({ ...prev, role: event.target.value }))}
        className="h-8 text-xs"
        placeholder="Role"
      />
      <Input
        value={draft.cert}
        onChange={(event) => setDraft(prev => ({ ...prev, cert: event.target.value }))}
        className="h-8 text-xs"
        placeholder="Cert"
      />

      <Select value={draft.canDrive} onValueChange={(value) => setDraft(prev => ({ ...prev, canDrive: value }))}>
        <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
        <SelectContent>
          <SelectItem value="yes">Driver</SelectItem>
          <SelectItem value="no">No driver</SelectItem>
        </SelectContent>
      </Select>

      <Select value={draft.active} onValueChange={(value) => setDraft(prev => ({ ...prev, active: value }))}>
        <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
        <SelectContent>
          <SelectItem value="active">Active</SelectItem>
          <SelectItem value="inactive">Inactive</SelectItem>
        </SelectContent>
      </Select>

      <div className="grid grid-cols-2 gap-1">
        <Select value={draft.supervisor} onValueChange={(value) => setDraft(prev => ({ ...prev, supervisor: value }))}>
          <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="yes">Sup</SelectItem>
            <SelectItem value="no">No sup</SelectItem>
          </SelectContent>
        </Select>
        <Select value={draft.admin} onValueChange={(value) => setDraft(prev => ({ ...prev, admin: value }))}>
          <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="yes">Admin</SelectItem>
            <SelectItem value="no">No admin</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <Button disabled size="sm" variant="outline" className="h-8 text-[10px]" title="No member persistence endpoint is wired yet.">
        <Save className="w-3 h-3" />
        {dirty ? 'Local only' : 'No save'}
      </Button>
    </div>
  );
}

export default function MemberManagementPanel({ members = [], loading = false }) {
  const [query, setQuery] = useState('');
  const [certFilter, setCertFilter] = useState(ALL);
  const [roleFilter, setRoleFilter] = useState(ALL);
  const [driverFilter, setDriverFilter] = useState(ALL);
  const [statusFilter, setStatusFilter] = useState(ALL);
  const [accessFilter, setAccessFilter] = useState(ALL);

  const certs = useMemo(() => uniqueValues(members, member => member.cert), [members]);
  const roles = useMemo(() => uniqueValues(members, member => member.role), [members]);

  const filteredMembers = useMemo(() => {
    const needle = normalize(query);
    return (members || []).filter(member => {
      if (needle && !normalize(memberSearchText(member)).includes(needle)) return false;
      if (certFilter !== ALL && member.cert !== certFilter) return false;
      if (roleFilter !== ALL && (member.role || '') !== roleFilter) return false;
      if (driverFilter === 'driver' && !member.canDrive) return false;
      if (driverFilter === 'non_driver' && member.canDrive) return false;
      if (statusFilter === 'active' && !member.active) return false;
      if (statusFilter === 'inactive' && member.active) return false;
      if (accessFilter === 'supervisor' && !member.supervisor) return false;
      if (accessFilter === 'admin' && !member.admin) return false;
      if (accessFilter === 'standard' && (member.supervisor || member.admin)) return false;
      return true;
    });
  }, [accessFilter, certFilter, driverFilter, members, query, roleFilter, statusFilter]);

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <CardTitle className="text-sm flex items-center gap-2">
              <UserCog className="w-4 h-4 text-primary" />
              Member Management
            </CardTitle>
            <p className="mt-1 text-xs text-muted-foreground">
              Review bootstrap member data. Edits stay local until member persistence is wired.
            </p>
          </div>
          <Badge variant="outline" className="w-fit text-[10px] bg-amber-500/10 text-amber-400 border-amber-500/20">
            Persistence not wired yet
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid gap-2 lg:grid-cols-[minmax(220px,1fr)_repeat(5,minmax(120px,0.55fr))]">
          <div className="relative">
            <Search className="absolute left-2.5 top-2.5 w-3.5 h-3.5 text-muted-foreground" />
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className="h-9 pl-8 text-xs"
              placeholder="Search name, id, role, cert, email, driver..."
            />
          </div>

          <Select value={certFilter} onValueChange={setCertFilter}>
            <SelectTrigger className="h-9 text-xs"><SelectValue placeholder="Cert" /></SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>All certs</SelectItem>
              {certs.map(cert => <SelectItem key={cert} value={cert}>{cert}</SelectItem>)}
            </SelectContent>
          </Select>

          <Select value={roleFilter} onValueChange={setRoleFilter}>
            <SelectTrigger className="h-9 text-xs"><SelectValue placeholder="Role" /></SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>All roles</SelectItem>
              {roles.map(role => <SelectItem key={role} value={role}>{role}</SelectItem>)}
            </SelectContent>
          </Select>

          <Select value={driverFilter} onValueChange={setDriverFilter}>
            <SelectTrigger className="h-9 text-xs"><SelectValue placeholder="Driver" /></SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>All driver</SelectItem>
              <SelectItem value="driver">Driver eligible</SelectItem>
              <SelectItem value="non_driver">Not driver</SelectItem>
            </SelectContent>
          </Select>

          <Select value={accessFilter} onValueChange={setAccessFilter}>
            <SelectTrigger className="h-9 text-xs"><SelectValue placeholder="Access" /></SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>All access</SelectItem>
              <SelectItem value="supervisor">Supervisor</SelectItem>
              <SelectItem value="admin">Admin</SelectItem>
              <SelectItem value="standard">Standard</SelectItem>
            </SelectContent>
          </Select>

          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="h-9 text-xs"><SelectValue placeholder="Status" /></SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>All status</SelectItem>
              <SelectItem value="active">Active</SelectItem>
              <SelectItem value="inactive">Inactive</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="flex items-center justify-between text-[10px] text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <SlidersHorizontal className="w-3 h-3" />
            Showing {filteredMembers.length} of {members.length} members
          </span>
          <span>Save buttons are disabled until a member write endpoint exists.</span>
        </div>

        {loading ? (
          <div className="h-32 rounded-lg bg-muted/40 animate-pulse" />
        ) : filteredMembers.length === 0 ? (
          <div className="flex items-center gap-2 rounded-lg border border-border/40 bg-muted/30 px-3 py-6 text-xs text-muted-foreground">
            <AlertCircle className="w-4 h-4" />
            No members match the current filters.
          </div>
        ) : (
          <div className="space-y-2 max-h-[420px] overflow-y-auto pr-1">
            {filteredMembers.map(member => (
              <EditableMemberRow key={member.id || member.name} member={member} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
