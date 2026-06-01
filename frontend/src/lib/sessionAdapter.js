export function normalizeSession(raw) {
  const source = raw?.session || raw?.auth || raw;
  const sourceEmail = source?.email || source?.auth_email || source?.user_email || null;
  const user = source?.user || source?.current_user || source?.member || (sourceEmail ? {
    email: sourceEmail,
    name: source?.member_name || source?.name || sourceEmail,
  } : null);
  const member = source?.member || source?.currentMember || source?.selectedMember || null;

  if (!source || (!user && !member && !source.authenticated)) {
    return null;
  }

  return {
    ...source,
    authenticated: Boolean(source.authenticated || user || member),
    user,
    member,
    member_id: source.member_id || member?.member_id || member?.id || null,
    email: sourceEmail || user?.email || member?.email || member?.auth_email || member?.google_email || null,
    role: source.role || member?.role || member?.sc_role || null,
    source: source.source || raw?.source || 'bootstrap',
  };
}

export function getBootstrapSession(bootstrap) {
  return normalizeSession(bootstrap?.session || bootstrap?.auth || bootstrap?.current_user || bootstrap);
}
