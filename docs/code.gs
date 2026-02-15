/**
 * ShiftCommander Store — Full v3
 * Drive-backed JSON store + resolver + locks + cost + fairness + audit log.
 *
 * Script Properties:
 *   SC_FOLDER_ID  Drive folder ID containing JSON files
 *   SC_TOKEN      shared token
 *
 * URL: https://script.google.com/macros/s/<DEPLOY>/exec
 *
 * GET:
 *  ?kind=ping&token=...
 *  ?kind=members&token=...
 *  ?kind=units&token=...
 *  ?kind=seats&token=...
 *  ?kind=qualifications&token=...
 *  ?kind=org_settings&token=...
 *  ?kind=schedule&token=...
 *  ?kind=week&week=YYYY-MM-DD&token=...
 *  ?kind=locks&week=YYYY-MM-DD&token=...
 *  ?kind=member_availability&member_id=SCID&token=...
 *  ?kind=history_index&token=...
 *  ?kind=history_month&month=YYYY-MM&token=...
 *  ?kind=assignments_history&token=...
 *  ?kind=cost_preview&week=YYYY-MM-DD&token=...
 *  ?kind=fairness_report&weeks=8&token=...
 *  ?kind=audit_log&limit=200&token=...
 *
 * POST (JSON body):
 *  {token, kind:"members", payload:{...}}
 *  {token, kind:"org_settings", payload:{...}}
 *  {token, kind:"member_availability", member_id:"SCID", payload:{...}}
 *  {token, kind:"locks", week:"YYYY-MM-DD", payload:{...}, allow_over_cap:false}
 *  {token, kind:"resolve_week", week:"YYYY-MM-DD", mode:"fair"|"budget", commit:true|false}
 *  {token, kind:"publish_week", week:"YYYY-MM-DD"}
 */

const PROP_FOLDER = "SC_FOLDER_ID";
const PROP_TOKEN  = "SC_TOKEN";
const STORE_VERSION = 3;

function doGet(e){
  try{
    const p = (e && e.parameter) ? e.parameter : {};
    const kind = normKind_(p.kind);
    if (!kind) return jsonOut_({ok:false,error:"Missing kind"},400);
    if (kind !== "ping") enforceToken_(String(p.token||""));

    if (kind === "ping") return ok_("ping",{time:new Date().toISOString()});

    if (kind === "member_availability"){
      const id = String(p.member_id||"").trim();
      if(!id) return jsonOut_({ok:false,error:"Missing member_id"},400);
      return ok_(kind, readJsonFile_(`member_availability_${id}.json`) || {schema:"sc.availability.v1", member_id:id, ranges:[]});
    }

    if (kind === "history_month"){
      const m = String(p.month||"").trim();
      if(!m) return jsonOut_({ok:false,error:"Missing month (YYYY-MM)"},400);
      return ok_(kind, readJsonFile_(`${m}.normalized.json`) || {});
    }

    if (kind === "locks"){
      const w = String(p.week||"").trim();
      if(!w) return jsonOut_({ok:false,error:"Missing week"},400);
      return ok_(kind, readJsonFile_(`locks_${w}.json`) || {schema:"sc.locks.v1", week_start:w, locks:[]});
    }

    if (kind === "week"){
      const w = String(p.week||"").trim();
      if(!w) return jsonOut_({ok:false,error:"Missing week"},400);
      return ok_(kind, readJsonFile_(`week_${w}.json`) || {schema:"sc.week.v1", week_start:w, status:"unresolved", assignments:[], meta:{}});
    }

    if (kind === "cost_preview"){
      const w = String(p.week||"").trim();
      if(!w) return jsonOut_({ok:false,error:"Missing week"},400);
      return ok_(kind, computeCostPreview_(w));
    }

    if (kind === "fairness_report"){
      const weeks = Math.max(1, Math.min(52, Number(p.weeks||8)));
      return ok_(kind, computeFairness_(weeks));
    }

    if (kind === "audit_log"){
      const limit = Math.max(10, Math.min(2000, Number(p.limit||200)));
      const log = readJsonFile_("audit.log.json") || {version:STORE_VERSION, events:[]};
      const events = (log.events||[]).slice(-limit).reverse();
      return ok_(kind, {version:log.version||STORE_VERSION, events});
    }

    const filename = kindToFilename_(kind);
    const payload = readJsonFile_(filename);
    if (payload === null) return jsonOut_({ok:false,error:`Missing file: ${filename}`},404);
    return ok_(kind, payload);

  }catch(err){
    return jsonOut_({ok:false,error:String(err)},500);
  }
}

function doPost(e){
  try{
    const raw = (e && e.postData && e.postData.contents) ? e.postData.contents : "{}";
    const body = JSON.parse(raw);
    const kind = normKind_(body.kind);
    if(!kind) return jsonOut_({ok:false,error:"Missing kind"},400);
    if (kind !== "ping") enforceToken_(String(body.token||""));

    if (kind === "ping") return ok_("ping",{time:new Date().toISOString()});

    if (kind === "member_availability"){
      const id = String(body.member_id||"").trim();
      if(!id) return jsonOut_({ok:false,error:"Missing member_id"},400);
      writeJsonFile_(`member_availability_${id}.json`, body.payload || {});
      audit_("member_availability.save", {member_id:id});
      return ok_(kind,{saved:true, member_id:id});
    }

    if (kind === "locks"){
      const w = String(body.week||"").trim();
      if(!w) return jsonOut_({ok:false,error:"Missing week"},400);
      const payload = body.payload || {schema:"sc.locks.v1", week_start:w, locks:[]};
      const allowOver = !!body.allow_over_cap;
      if(!allowOver){
        const capCheck = checkCapsForLocks_(w, payload);
        if(!capCheck.ok) return jsonOut_({ok:false,error:"Cap violation", details:capCheck.details},409);
      }
      writeJsonFile_(`locks_${w}.json`, payload);
      audit_("locks.save", {week:w, count:(payload.locks||[]).length});
      return ok_(kind,{saved:true, week:w});
    }

    if (kind === "resolve_week"){
      const w = String(body.week||"").trim();
      if(!w) return jsonOut_({ok:false,error:"Missing week"},400);
      const mode = String(body.mode||"fair").toLowerCase();
      const commit = !!body.commit;
      const result = resolveWeek_(w, mode);
      if(commit){
        writeJsonFile_(`week_${w}.json`, result.week);
        audit_("week.resolved", {week:w, mode, cost:result.cost.total_cost});
      }
      return ok_(kind, result);
    }

    if (kind === "publish_week"){
      const w = String(body.week||"").trim();
      if(!w) return jsonOut_({ok:false,error:"Missing week"},400);
      const wk = readJsonFile_(`week_${w}.json`);
      if(!wk) return jsonOut_({ok:false,error:"Week not found"},404);
      wk.status = "published";
      writeJsonFile_(`week_${w}.json`, wk);
      audit_("week.published", {week:w});
      return ok_(kind,{published:true, week:w});
    }

    // simple mapped writes
    if (["members","org_settings","units","seats","qualifications","schedule"].indexOf(kind)>=0){
      const filename = kindToFilename_(kind);
      writeJsonFile_(filename, body.payload || {});
      audit_(kind+".save", {});
      return ok_(kind,{saved:true});
    }

    return jsonOut_({ok:false,error:"Write not allowed for kind: "+kind},403);

  }catch(err){
    return jsonOut_({ok:false,error:String(err)},500);
  }
}

/* ---------- Mapping ---------- */

function normKind_(k){ return String(k||"").toLowerCase().trim(); }

function kindToFilename_(kind){
  switch(kind){
    case "members": return "members.json";
    case "units": return "units.json";
    case "seats": return "seats.json";
    case "qualifications": return "qualifications.json";
    case "org_settings": return "org_settings.json";
    case "schedule": return "schedule.json";
    case "history_index": return "history.index.json";
    case "assignments_history": return "assignments_history.json";
    default: throw new Error("Unknown kind: "+kind);
  }
}

function ok_(kind,payload){
  return jsonOut_({ok:true, kind, version:STORE_VERSION, payload},200);
}

/* ---------- Security ---------- */

function enforceToken_(token){
  const expected = PropertiesService.getScriptProperties().getProperty(PROP_TOKEN);
  if(!expected) throw new Error("Missing Script Property: "+PROP_TOKEN);
  if(!token || token !== expected) throw new Error("Unauthorized (bad token)");
}

function getFolderId_(){
  const folderId = PropertiesService.getScriptProperties().getProperty(PROP_FOLDER);
  if(!folderId) throw new Error("Missing Script Property: "+PROP_FOLDER);
  return folderId;
}

/* ---------- Audit ---------- */

function audit_(type, data){
  const log = readJsonFile_("audit.log.json") || {version:STORE_VERSION, events:[]};
  log.version = STORE_VERSION;
  log.events = log.events || [];
  log.events.push({
    at: new Date().toISOString(),
    type: String(type||""),
    data: data || {}
  });
  // keep last 5000
  if(log.events.length>5000) log.events = log.events.slice(log.events.length-5000);
  writeJsonFile_("audit.log.json", log);
}

/* ---------- Cost / Caps / Fairness ---------- */

function membersList_(){
  const doc = readJsonFile_("members.json") || {};
  if(Array.isArray(doc)) return doc;
  if(Array.isArray(doc.members)) return doc.members;
  return [];
}

function orgSettings_(){
  return readJsonFile_("org_settings.json") || {budget_weekly_target:0, week_hours_default:12};
}

function memberCapHours_(m){
  const comp = (m && m.comp) ? m.comp : {};
  if(comp.hour_cap_weekly_override !== null && comp.hour_cap_weekly_override !== undefined){
    return Number(comp.hour_cap_weekly_override||0);
  }
  if(comp.hour_cap_weekly !== null && comp.hour_cap_weekly !== undefined){
    return Number(comp.hour_cap_weekly||0);
  }
  const pt = String(comp.pay_type||"hourly").toLowerCase();
  if(pt==="volunteer") return 24;
  if(pt==="salary") return 60;
  return 36;
}

function effectiveHourlyRate_(m, atISO){
  const comp = (m && m.comp) ? m.comp : {};
  const rh = Array.isArray(comp.rate_history) ? comp.rate_history : [];
  const t = new Date(atISO+"T00:00:00").getTime();
  for (var i=0;i<rh.length;i++){
    const r=rh[i];
    const from = r.effective_from ? new Date(r.effective_from+"T00:00:00").getTime() : -8640000000000000;
    const to = r.effective_to ? new Date(r.effective_to+"T00:00:00").getTime() : 8640000000000000;
    if(t>=from && t<=to) return Number(r.hourly_rate||0);
  }
  return Number(comp.hourly_rate||0);
}

function checkCapsForLocks_(weekStartISO, locksPayload){
  const members = membersList_();
  const hoursBy = {};
  (locksPayload.locks||[]).forEach(lk=>{
    const id=String(lk.member_id||"").trim();
    if(!id) return;
    const hrs=Number(lk.hours||12);
    hoursBy[id]=(hoursBy[id]||0)+hrs;
  });
  const violations=[];
  Object.keys(hoursBy).forEach(id=>{
    const m = members.filter(x=>String(x.member_id)===id)[0];
    if(!m) return;
    const cap = memberCapHours_(m);
    if(Number(hoursBy[id])>cap) violations.push({member_id:id, hours:Number(hoursBy[id]), cap_hours:cap});
  });
  return violations.length ? {ok:false, details:violations} : {ok:true, details:[]};
}

function computeCostPreview_(weekStartISO){
  const members = membersList_();
  const nameBy = {};
  members.forEach(m=>{ nameBy[String(m.member_id)] = ((m.first_name||"")+" "+(m.last_name||"")).trim(); });
  const locks = readJsonFile_(`locks_${weekStartISO}.json`) || {locks:[]};
  const week = readJsonFile_(`week_${weekStartISO}.json`) || {assignments:[]};
  const org = orgSettings_();

  // merge: locked + resolved assignments (resolved overrides duplicate seat/time)
  const items = [];
  (locks.locks||[]).forEach(lk=> items.push(Object.assign({status:"locked"}, lk)));
  (week.assignments||[]).forEach(a=> items.push(Object.assign({status:week.status||"planned"}, a)));

  const hoursBy={}, costBy={}, line_items=[];
  items.forEach(it=>{
    const id=String(it.member_id||"").trim();
    if(!id) return;
    const date=String(it.date||"").slice(0,10) || weekStartISO;
    const hrs=Number(it.hours||org.week_hours_default||12);
    const m = members.filter(x=>String(x.member_id)===id)[0];
    const rate = m ? effectiveHourlyRate_(m, date) : 0;
    hoursBy[id]=(hoursBy[id]||0)+hrs;
    costBy[id]=(costBy[id]||0)+(hrs*rate);
    line_items.push({member_id:id, name:nameBy[id]||id, date, hours:hrs, rate, cost:hrs*rate, status:it.status, unit:it.unit, seat:it.seat, shift:it.shift});
  });

  const per_member = Object.keys(hoursBy).map(id=>{
    const m = members.filter(x=>String(x.member_id)===id)[0] || {};
    const cap = memberCapHours_(m);
    return {
      member_id:id,
      name:nameBy[id]||id,
      pay_type: m.comp ? m.comp.pay_type : null,
      hours:Number(hoursBy[id]||0),
      cap_hours:cap,
      over_cap:Number(hoursBy[id]||0)>cap,
      estimated_cost:Number(costBy[id]||0)
    };
  });

  const total_cost = per_member.reduce((s,x)=>s+x.estimated_cost,0);
  return {
    schema:"sc.cost_preview.v1",
    week_start: weekStartISO,
    total_cost,
    budget_target: Number(org.budget_weekly_target||0),
    over_budget: Number(org.budget_weekly_target||0)>0 ? (total_cost > Number(org.budget_weekly_target||0)) : false,
    per_member,
    line_items
  };
}

function computeFairness_(weeks){
  const members = membersList_();
  const now = new Date();
  // approximate weeks ending on next Sunday
  const d = new Date(now); d.setHours(0,0,0,0);
  const add=(7-d.getDay())%7; d.setDate(d.getDate()+add);
  const endSunday = d;

  const buckets = {};
  members.forEach(m=>{
    buckets[String(m.member_id)] = {member_id:String(m.member_id), name:((m.first_name||"")+" "+(m.last_name||"")).trim(), hours:0, shifts:0, nights:0, weekends:0};
  });

  for(let i=0;i<weeks;i++){
    const wk = new Date(endSunday); wk.setDate(endSunday.getDate()-i*7);
    const iso = wk.toISOString().slice(0,10);
    const weekDoc = readJsonFile_(`week_${iso}.json`);
    const locksDoc = readJsonFile_(`locks_${iso}.json`);
    const items = [];
    if(weekDoc && Array.isArray(weekDoc.assignments)) items.push.apply(items, weekDoc.assignments);
    if(locksDoc && Array.isArray(locksDoc.locks)) items.push.apply(items, locksDoc.locks);
    items.forEach(a=>{
      const id=String(a.member_id||"").trim();
      if(!buckets[id]) return;
      const hrs=Number(a.hours||12);
      buckets[id].hours += hrs;
      buckets[id].shifts += 1;
      const date = String(a.date||"");
      const dt = date ? new Date(date+"T00:00:00") : null;
      const dow = dt ? dt.getDay() : null; // 0 sun
      if(dow===0 || dow===6) buckets[id].weekends += 1;
      if(String(a.shift||"").toUpperCase()==="PM" || String(a.slot||"").toUpperCase()==="PM") buckets[id].nights += 1;
    });
  }

  const rows = Object.values(buckets);
  // simple fairness score: lower is better (more burden -> higher score)
  rows.forEach(r=>{
    r.score = Math.round((r.hours*1.0) + (r.weekends*6) + (r.nights*3));
  });
  rows.sort((a,b)=>b.score-a.score);
  return {schema:"sc.fairness.v1", weeks, rows};
}

/* ---------- Resolver ---------- */

function resolveWeek_(weekStartISO, mode){
  const org = orgSettings_();
  const members = membersList_();
  const locksDoc = readJsonFile_(`locks_${weekStartISO}.json`) || {locks:[]};
  const baseWeek = readJsonFile_(`week_${weekStartISO}.json`) || {schema:"sc.week.v1", week_start:weekStartISO, status:"unresolved", assignments:[], meta:{}};

  // Build candidate assignments from locks first
  const assignments = [];
  const lockedKeys = {};
  (locksDoc.locks||[]).forEach(lk=>{
    const k = key_(lk);
    lockedKeys[k]=true;
    assignments.push(Object.assign({locked:true}, lk));
  });

  // Determine required seats from seats.json (if present). Otherwise, keep only locks.
  const seatsDoc = readJsonFile_("seats.json") || {seats:[]};
  const seats = Array.isArray(seatsDoc.seats) ? seatsDoc.seats : (Array.isArray(seatsDoc)?seatsDoc:[]);
  // seat objects may include {unit, seat, shift, required:true}
  const required = seats.filter(s=>s && s.required);

  // For each required seat, fill if not locked
  required.forEach(s=>{
    const stub = {date: s.date||"", shift:s.shift||"AM", unit:s.unit||"", seat:s.seat||"", hours:Number(s.hours||org.week_hours_default||12)};
    const k = key_(stub);
    if(lockedKeys[k]) return;
    const pick = pickMemberForSeat_(members, stub, weekStartISO, mode, assignments);
    if(pick){
      assignments.push({date:stub.date, shift:stub.shift, unit:stub.unit, seat:stub.seat, hours:stub.hours, member_id:pick.member_id, reason:pick.reason});
    }
  });

  // Update week doc
  const week = Object.assign({}, baseWeek);
  week.schema = "sc.week.v1";
  week.week_start = weekStartISO;
  week.status = "resolved";
  week.assignments = assignments;
  week.meta = {
    mode: mode,
    generated_at: new Date().toISOString(),
    filled_required: required.length
  };

  const cost = computeCostPreview_(weekStartISO);
  // cost_preview includes resolved week read; but we haven't written. So compute locally quick:
  // We'll compute from assignments + locks directly:
  const tmp = computeCostPreviewLocal_(weekStartISO, assignments, locksDoc.locks||[]);
  return {week, cost:tmp};
}

function key_(a){
  return String(a.date||"") + "|" + String(a.shift||"") + "|" + String(a.unit||"") + "|" + String(a.seat||"");
}

function pickMemberForSeat_(members, seatStub, weekStartISO, mode, currentAssignments){
  // Very conservative deterministic pick:
  // - must have qualifications if seat requires ALS/BLS (derived from seat name)
  // - must not exceed cap with currentAssignments
  // - mode "budget" prefers lower hourly rate; mode "fair" prefers lower recent burden
  const seatName = String(seatStub.seat||"").toUpperCase();
  const needALS = (seatName.indexOf("ALS")>=0) || (seatName.indexOf("MEDIC")>=0);
  const needEMT = (seatName.indexOf("BLS")>=0) || (seatName.indexOf("DRIVER")>=0) || true;

  const hoursBy = {};
  currentAssignments.forEach(a=>{
    const id=String(a.member_id||"").trim();
    if(!id) return;
    hoursBy[id]=(hoursBy[id]||0)+Number(a.hours||12);
  });

  // fairness baseline over last 8 weeks
  const fairness = computeFairness_(8).rows || [];
  const fairnessBy = {};
  fairness.forEach(r=> fairnessBy[r.member_id]=r.score );

  const candidates = members.filter(m=>{
    if(!m || m.active===false) return false;
    const quals = m.qualifications || m.quals || [];
    const qset = {};
    (Array.isArray(quals)?quals:[]).forEach(q=>{ qset[String(q).toUpperCase()] = true; });
    if(needALS && !(qset["PARAMEDIC"] || qset["ALS"] || qset["AEMT"])) return false;
    if(needEMT && !(qset["EMT"] || qset["AEMT"] || qset["PARAMEDIC"] || qset["DRIVER"])) return false;
    const cap = memberCapHours_(m);
    const cur = Number(hoursBy[String(m.member_id)]||0);
    if(cur + Number(seatStub.hours||12) > cap) return false;
    return true;
  });

  if(!candidates.length) return null;

  // score candidates
  const scored = candidates.map(m=>{
    const id=String(m.member_id);
    const dateISO = (seatStub.date && String(seatStub.date).length>=10) ? String(seatStub.date).slice(0,10) : weekStartISO;
    const rate = effectiveHourlyRate_(m, dateISO);
    const fairScore = fairnessBy[id] || 0;
    // lower better
    const score = (mode==="budget") ? (rate*1000 + fairScore) : (fairScore*1000 + rate);
    return {m, score, rate, fairScore};
  }).sort((a,b)=> a.score-b.score || String(a.m.member_id).localeCompare(String(b.m.member_id)));

  const best = scored[0];
  return {member_id:String(best.m.member_id), reason:(mode==="budget"?"budget_pick":"fair_pick")};
}

function computeCostPreviewLocal_(weekStartISO, assignments, locks){
  const members = membersList_();
  const org = orgSettings_();
  const nameBy = {};
  members.forEach(m=>{ nameBy[String(m.member_id)] = ((m.first_name||"")+" "+(m.last_name||"")).trim(); });
  const items = [];
  (locks||[]).forEach(lk=> items.push(Object.assign({status:"locked"}, lk)));
  (assignments||[]).forEach(a=> items.push(Object.assign({status:"resolved"}, a)));

  const hoursBy={}, costBy={}, line_items=[];
  items.forEach(it=>{
    const id=String(it.member_id||"").trim();
    if(!id) return;
    const date=String(it.date||"").slice(0,10) || weekStartISO;
    const hrs=Number(it.hours||org.week_hours_default||12);
    const m = members.filter(x=>String(x.member_id)===id)[0];
    const rate = m ? effectiveHourlyRate_(m, date) : 0;
    hoursBy[id]=(hoursBy[id]||0)+hrs;
    costBy[id]=(costBy[id]||0)+(hrs*rate);
    line_items.push({member_id:id, name:nameBy[id]||id, date, hours:hrs, rate, cost:hrs*rate, status:it.status, unit:it.unit, seat:it.seat, shift:it.shift});
  });

  const per_member = Object.keys(hoursBy).map(id=>{
    const m = members.filter(x=>String(x.member_id)===id)[0] || {};
    const cap = memberCapHours_(m);
    return {
      member_id:id,
      name:nameBy[id]||id,
      pay_type: m.comp ? m.comp.pay_type : null,
      hours:Number(hoursBy[id]||0),
      cap_hours:cap,
      over_cap:Number(hoursBy[id]||0)>cap,
      estimated_cost:Number(costBy[id]||0)
    };
  });

  const total_cost = per_member.reduce((s,x)=>s+x.estimated_cost,0);
  return {
    schema:"sc.cost_preview.v1",
    week_start: weekStartISO,
    total_cost,
    budget_target: Number(org.budget_weekly_target||0),
    over_budget: Number(org.budget_weekly_target||0)>0 ? (total_cost > Number(org.budget_weekly_target||0)) : false,
    per_member,
    line_items
  };
}

/* ---------- Drive (Shared Drive safe) ---------- */
/* Requires Advanced Google Service: Drive API (v2) enabled as "Drive" */

function findFileIdByName_(folderId, filename){
  const safeName = filename.replace(/'/g, "\\'");
  const q = `'${folderId}' in parents and title = '${safeName}' and trashed = false`;
  const resp = Drive.Files.list({
    q, maxResults: 10,
    fields: "items(id,title,modifiedDate)",
    supportsAllDrives: true,
    includeItemsFromAllDrives: true
  });
  if(!resp.items || !resp.items.length) return null;
  resp.items.sort((a,b)=> new Date(b.modifiedDate) - new Date(a.modifiedDate));
  return resp.items[0].id;
}

function readJsonFile_(filename){
  const folderId = getFolderId_();
  const fileId = findFileIdByName_(folderId, filename);
  if(!fileId) return null;
  const token = ScriptApp.getOAuthToken();
  const url = `https://www.googleapis.com/drive/v2/files/${fileId}?alt=media`;
  const res = UrlFetchApp.fetch(url, {
    method:"get",
    headers:{Authorization:`Bearer ${token}`},
    muteHttpExceptions:true
  });
  const code=res.getResponseCode();
  if(code<200 || code>=300) throw new Error(`Drive read failed (${code}) for ${filename}: ${res.getContentText()}`);
  const txt=res.getContentText("utf-8");
  if(!txt) return {};
  return JSON.parse(txt);
}

function writeJsonFile_(filename, obj){
  const lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try{
    const folderId = getFolderId_();
    const content = JSON.stringify(obj ?? {}, null, 2);
    const fileId = findFileIdByName_(folderId, filename);
    const token = ScriptApp.getOAuthToken();

    if(fileId){
      const url = `https://www.googleapis.com/upload/drive/v2/files/${fileId}?uploadType=media&supportsAllDrives=true`;
      const res = UrlFetchApp.fetch(url, {
        method:"put",
        contentType:"application/json",
        payload:content,
        headers:{Authorization:`Bearer ${token}`},
        muteHttpExceptions:true
      });
      const code=res.getResponseCode();
      if(code<200 || code>=300) throw new Error(`Drive update failed (${code}) for ${filename}: ${res.getContentText()}`);
      return;
    }

    const boundary="sc_boundary_"+Date.now();
    const delimiter=`\r\n--${boundary}\r\n`;
    const closeDelim=`\r\n--${boundary}--`;
    const metadata={title:filename, mimeType:"application/json", parents:[{id:folderId}]};
    const multipartBody =
      delimiter + "Content-Type: application/json; charset=UTF-8\r\n\r\n" + JSON.stringify(metadata) +
      delimiter + "Content-Type: application/json; charset=UTF-8\r\n\r\n" + content +
      closeDelim;

    const url="https://www.googleapis.com/upload/drive/v2/files?uploadType=multipart&supportsAllDrives=true";
    const res=UrlFetchApp.fetch(url,{
      method:"post",
      contentType:`multipart/related; boundary=${boundary}`,
      payload:multipartBody,
      headers:{Authorization:`Bearer ${token}`},
      muteHttpExceptions:true
    });
    const code=res.getResponseCode();
    if(code<200 || code>=300) throw new Error(`Drive create failed (${code}) for ${filename}: ${res.getContentText()}`);
  } finally {
    lock.releaseLock();
  }
}

function jsonOut_(obj, status){
  const payload = Object.assign({_status:Number(status)}, obj || {});
  return ContentService.createTextOutput(JSON.stringify(payload))
    .setMimeType(ContentService.MimeType.JSON);
}
