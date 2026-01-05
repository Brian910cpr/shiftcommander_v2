/**
 * ShiftCommander JSON Store (Google Drive folder)
 *
 * Script Properties required:
 *   SC_FOLDER_ID = Drive folder that holds JSON files
 *   SC_TOKEN     = shared secret token
 *
 * GET:
 *   ?kind=ping&token=XYZ
 *   ?kind=members&token=XYZ
 *   ?kind=units&token=XYZ
 *   ?kind=seats&token=XYZ
 *   ?kind=qualifications&token=XYZ
 *   ?kind=org_settings&token=XYZ
 *   ?kind=assignments&token=XYZ
 *   ?kind=supervisor_patch&token=XYZ
 *   ?kind=member_availability&member_id=123&token=XYZ
 *
 * POST (JSON body):
 *   { token:"XYZ", kind:"members", payload:{...} }
 *   { token:"XYZ", kind:"member_availability", member_id:"123", payload:{...} }
 *
 * Notes:
 * - No CORS here. Cloudflare Worker provides CORS.
 * - Requires Advanced Google Service: Drive API enabled with identifier "Drive".
 */

const PROP_FOLDER = "SC_FOLDER_ID";
const PROP_TOKEN  = "SC_TOKEN";

function doGet(e) {
  try {
    const p = (e && e.parameter) ? e.parameter : {};
    const kind = normKind_(p.kind);
    if (!kind) return jsonOut_({ ok:false, error:"Missing kind" }, 400);

    if (kind !== "ping") enforceToken_(String(p.token || ""));

    if (kind === "ping") {
      return jsonOut_({ ok:true, kind:"ping", time: new Date().toISOString() }, 200);
    }

    if (kind === "member_availability") {
      const memberId = String(p.member_id || p.memberId || "").trim();
      if (!memberId) return jsonOut_({ ok:false, error:"Missing member_id" }, 400);
      const filename = `member_availability_${memberId}.json`;
      const payload = readJsonFile_(filename) || {};
      return jsonOut_({ ok:true, kind, member_id: memberId, payload }, 200);
    }

    const filename = kindToFilename_(kind);
    const payload = readJsonFile_(filename) || {};
    return jsonOut_({ ok:true, kind, payload }, 200);

  } catch (err) {
    return jsonOut_({ ok:false, error:String(err) }, 500);
  }
}

function doPost(e) {
  try {
    const raw = (e && e.postData && e.postData.contents) ? e.postData.contents : "{}";
    const body = JSON.parse(raw);

    const kind = normKind_(body.kind);
    if (!kind) return jsonOut_({ ok:false, error:"Missing kind" }, 400);

    if (kind !== "ping") enforceToken_(String(body.token || ""));

    if (kind === "ping") {
      return jsonOut_({ ok:true, kind:"ping", time: new Date().toISOString() }, 200);
    }

    if (kind === "member_availability") {
      const memberId = String(body.member_id || body.memberId || "").trim();
      if (!memberId) return jsonOut_({ ok:false, error:"Missing member_id" }, 400);

      const filename = `member_availability_${memberId}.json`;
      const payload = (body.payload !== undefined) ? body.payload : {};
      writeJsonFile_(filename, payload);

      return jsonOut_({ ok:true, kind, member_id: memberId, saved:true }, 200);
    }

    const filename = kindToFilename_(kind);
    const payload = (body.payload !== undefined) ? body.payload : {};
    writeJsonFile_(filename, payload);

    return jsonOut_({ ok:true, kind, saved:true }, 200);

  } catch (err) {
    return jsonOut_({ ok:false, error:String(err) }, 500);
  }
}

/* ---------------- Kind / filename mapping ---------------- */

function normKind_(k) {
  return String(k || "").toLowerCase().trim();
}

function kindToFilename_(kind) {
  switch (kind) {
    case "members":          return "members.json";
    case "units":            return "units.json";
    case "seats":            return "seats.json";
    case "qualifications":   return "qualifications.json";
    case "org_settings":     return "org_settings.json";
    case "assignments":      return "assignments.json";
    case "supervisor_patch": return "supervisor_patch.json";
    case "schedule":         return "schedule.json";

    default:
      throw new Error("Unknown kind: " + kind);
  }
}

/* ---------------- Security ---------------- */

function enforceToken_(token) {
  const expected = PropertiesService.getScriptProperties().getProperty(PROP_TOKEN);
  if (!expected) throw new Error(`Missing Script Property: ${PROP_TOKEN}`);
  if (!token || token !== expected) throw new Error("Unauthorized (bad token)");
}

function getFolderId_() {
  const folderId = PropertiesService.getScriptProperties().getProperty(PROP_FOLDER);
  if (!folderId) throw new Error(`Missing Script Property: ${PROP_FOLDER}`);
  return folderId;
}

/* ---------------- Drive (Shared Drive safe) ----------------
   Uses Advanced Google Service: Drive API (v2) with identifier "Drive"
*/

function findFileIdByName_(folderId, filename) {
  const safeName = filename.replace(/'/g, "\\'");
  const q = `'${folderId}' in parents and title = '${safeName}' and trashed = false`;

  const resp = Drive.Files.list({
    q: q,
    maxResults: 1,
    fields: "items(id,title)",
    supportsAllDrives: true,
    includeItemsFromAllDrives: true
  });

  if (resp.items && resp.items.length) return resp.items[0].id;
  return null;
}

function readJsonFile_(filename) {
  const folderId = getFolderId_();
  const fileId = findFileIdByName_(folderId, filename);
  if (!fileId) return null;

  const token = ScriptApp.getOAuthToken();
  const url = `https://www.googleapis.com/drive/v2/files/${fileId}?alt=media`;

  const res = UrlFetchApp.fetch(url, {
    method: "get",
    headers: { Authorization: `Bearer ${token}` },
    muteHttpExceptions: true
  });

  const code = res.getResponseCode();
  if (code < 200 || code >= 300) {
    throw new Error(`Drive read failed (${code}) for ${filename}: ${res.getContentText()}`);
  }

  const txt = res.getContentText("utf-8");
  if (!txt) return {};
  return JSON.parse(txt);
}

function writeJsonFile_(filename, obj) {
  const folderId = getFolderId_();
  const content = JSON.stringify(obj ?? {}, null, 2);
  const fileId = findFileIdByName_(folderId, filename);
  const token = ScriptApp.getOAuthToken();

  if (fileId) {
    const url = `https://www.googleapis.com/upload/drive/v2/files/${fileId}?uploadType=media&supportsAllDrives=true`;
    const res = UrlFetchApp.fetch(url, {
      method: "put",
      contentType: "application/json",
      payload: content,
      headers: { Authorization: `Bearer ${token}` },
      muteHttpExceptions: true
    });

    const code = res.getResponseCode();
    if (code < 200 || code >= 300) {
      throw new Error(`Drive update failed (${code}) for ${filename}: ${res.getContentText()}`);
    }
    return;
  }

  // create new
  const boundary = "sc_boundary_" + Date.now();
  const delimiter = `\r\n--${boundary}\r\n`;
  const closeDelim = `\r\n--${boundary}--`;

  const metadata = {
    title: filename,
    mimeType: "application/json",
    parents: [{ id: folderId }]
  };

  const multipartBody =
    delimiter +
    "Content-Type: application/json; charset=UTF-8\r\n\r\n" +
    JSON.stringify(metadata) +
    delimiter +
    "Content-Type: application/json; charset=UTF-8\r\n\r\n" +
    content +
    closeDelim;

  const url = "https://www.googleapis.com/upload/drive/v2/files?uploadType=multipart&supportsAllDrives=true";
  const res = UrlFetchApp.fetch(url, {
    method: "post",
    contentType: `multipart/related; boundary=${boundary}`,
    payload: multipartBody,
    headers: { Authorization: `Bearer ${token}` },
    muteHttpExceptions: true
  });

  const code = res.getResponseCode();
  if (code < 200 || code >= 300) {
    throw new Error(`Drive create failed (${code}) for ${filename}: ${res.getContentText()}`);
  }
}

/* ---------------- Response ---------------- */

function jsonOut_(obj, status) {
  const payload = Object.assign({ _status: Number(status) }, obj || {});
  return ContentService
    .createTextOutput(JSON.stringify(payload))
    .setMimeType(ContentService.MimeType.JSON);
}
