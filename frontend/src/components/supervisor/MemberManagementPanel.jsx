import React, { useEffect, useMemo, useState } from 'react';
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
import { AlertCircle, Loader2, Search, Save, SlidersHorizontal, UserCog } from 'lucide-react';
import { updateMember } from '@/api/client';

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
  const [savedFields, setSavedFields] = useState({
    role: member.role || '',
    canDrive: member.canDrive ? 'yes' : 'no',
    notes: member.notes || '',
  });
  const [draft, setDraft] = useState({
    role: member.role || '',
    canDrive: member.canDrive ? 'yes' : 'no',
    notes: member.notes || '',
  });
  const [saveStatus, setSaveStatus] = useState('');
  const [saveMessage, setSaveMessage] = useState('');

  useEffect(() => {
    const next = {
      role: member.role || '',
      canDrive: member.canDrive ? 'yes' : 'no',
      notes: member.notes || '',
    };
    setSavedFields(next);
    setDraft(next);
    setSaveStatus('');
    setSaveMessage('');
  }, [member]);

  const dirty = Object.entries(draft).some(([key, value]) => value !== savedFields[key]);
  const saving = saveStatus === 'saving';

  const handleSave = async () => {
    if (!dirty || saving) return;
    setSaveStatus('saving');
    setSaveMessage('');

    try {
      const result = await updateMember(member.id, {
        role: draft.role,
        can_drive: draft.canDrive === 'yes',
        notes: draft.notes,
      });
      if (result?.saved !== true || result?.persisted !== true) {
        setSaveStatus('failed');
        setSaveMessage(result?.error || 'Worker did not confirm persistence.');
        return;
      }
      setSavedFields(draft);
      setSaveStatus('saved');
      setSaveMessage('Saved');
      setTimeout(() => {
        setSaveStatus('');
        setSaveMessage('');
      }, 3000);
    } catch (error) {
      setSaveStatus('failed');
      setSaveMessage(error?.message || 'Save failed');
    }
  };

  return (
    <div className="grid grid-cols-[minmax(190px,1.2fr)_minmax(100px,0.55fr)_minmax(104px,0.55fr)_minmax(180px,1fr)_minmax(190px,0.9fr)_minmax(130px,0.7fr)] gap-2 items-center px-3 py-2 rounded-lg border border-border/30 bg-background/60">
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
      <Select value={draft.canDrive} onValueChange={(value) => setDraft(prev => ({ ...prev, canDrive: value }))}>
        <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
        <SelectContent>
          <SelectItem value="yes">Driver</SelectItem>
          <SelectItem value="no">No driver</SelectItem>
        </SelectContent>
      </Select>

      <Input
        value={draft.notes}
        onChange={(event) => setDraft(prev => ({ ...prev, notes: event.target.value }))}
        className="h-8 text-xs"
        placeholder="Notes"
      />

      <div className="flex flex-wrap gap-1.5 text-[10px] text-muted-foreground">
        <Badge variant="outline" className="text-[9px]">Cert: {member.cert || 'n/a'}</Badge>
        <Badge variant="outline" className="text-[9px]">{member.active ? 'Active' : 'Inactive'}</Badge>
        {member.supervisor && <Badge variant="outline" className="text-[9px]">Supervisor</Badge>}
        {member.admin && <Badge variant="outline" className="text-[9px]">Admin</Badge>}
      </div>

      <div className="flex items-center gap-2">
        <Button
          disabled={!dirty || saving}
          size="sm"
          variant={dirty ? 'default' : 'outline'}
          className="h-8 text-[10px]"
          onClick={handleSave}
        >
          {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
          {saving ? 'Saving' : saveStatus === 'saved' ? 'Saved' : saveStatus === 'failed' ? 'Retry' : 'Save'}
        </Button>
        {saveMessage && (
          <span className={`text-[10px] font-semibold ${saveStatus === 'failed' ? 'text-red-400' : 'text-emerald-400'}`}>
            {saveMessage}
          </span>
        )}
      </div>
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
              Save supported member updates live. Unsupported fields remain read-only.
            </p>
          </div>
          <Badge variant="outline" className="w-fit text-[10px] bg-emerald-500/10 text-emerald-400 border-emerald-500/20">
            Member updates live
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
          <span>Persists role, driver eligibility, and notes. Cert/status/access are read-only.</span>
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
