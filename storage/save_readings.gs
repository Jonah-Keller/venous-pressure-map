/**
 * Venous Pressure Map: save cases and survey answers to this Google Sheet.
 *
 * Two tabs, filled by the website:
 *   "Readings": one row per case (study ID, procedure date, unit, side, every
 *     reading before / after stent, where the narrowing is, the gradient).
 *   "Survey": one row per anonymous patient survey (Timestamp + one column per
 *     question title, the same layout as a Google Forms export).
 * No names or MRNs. The study ID -> MRN key lives only in the secure team folder.
 *
 * Set up once (about 5 minutes), with the study/clinic Google account:
 *   1. Make a new Google Sheet, e.g. "Venous pressure records".
 *   2. Extensions -> Apps Script. Delete the stub, paste this whole file, Save.
 *   3. Project Settings (gear) -> Script properties -> Add property:
 *        PASSCODE = a team passcode (share it with the team; not in GitHub).
 *   4. Deploy -> New deployment -> type "Web app".
 *        Execute as: Me.   Who has access: Anyone.   -> Deploy, allow access.
 *   5. Copy the Web app URL (ends in /exec) into storage.json in the repo
 *      ("endpoint": "..."), commit, push. The Save button now works.
 *
 * Re-saving the same study ID + date overwrites that row (so corrections are easy).
 * After editing this script: Deploy -> Manage deployments -> edit -> New version.
 */
const SHEET_NAME = "Readings";
const SURVEY_SHEET = "Survey";
const ID_PATTERN = /^[A-Za-z]{1,6}-?\d{1,6}$/;   // e.g. VP-0001. Rejects MRN-like numbers.

function doPost(e) {
  try {
    const body = JSON.parse(e.postData.contents);
    const expected = PropertiesService.getScriptProperties().getProperty("PASSCODE");
    if (!expected) return reply_({ ok: false, error: "Saving is not set up: add a PASSCODE script property." });
    if (body.passcode !== expected) return reply_({ ok: false, error: "Wrong team passcode." });
    if (body.kind === "survey") return saveSurvey_(body.response || {});

    const r = body.record || {};
    const id = String(r.study_id || "").trim();
    if (!ID_PATTERN.test(id)) return reply_({ ok: false, error: "Study ID should look like VP-0001 (no MRNs)." });
    if (!/^\d{4}-\d{2}-\d{2}$/.test(String(r.procedure_date || ""))) {
      return reply_({ ok: false, error: "Procedure date is missing." });
    }
    r.study_id = id;
    r.saved_at = new Date().toISOString();

    const lock = LockService.getScriptLock();
    lock.waitLock(10000);
    try {
      const sheet = sheet_();
      const header = header_(sheet, Object.keys(r));
      const values = header.map((k) => (r[k] === null || r[k] === undefined ? "" : r[k]));
      const row = findRow_(sheet, header, id, r.procedure_date);
      if (row) sheet.getRange(row, 1, 1, header.length).setValues([values]);
      else sheet.appendRow(values);
      return reply_({ ok: true, updated: !!row });
    } finally {
      lock.releaseLock();
    }
  } catch (err) {
    return reply_({ ok: false, error: String(err) });
  }
}

/** Append one anonymous survey response. Columns follow the question titles. */
function saveSurvey_(r) {
  if (!r["Clinic code"] || !r.Timestamp) return reply_({ ok: false, error: "Survey answer is incomplete." });
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const sheet = ss.getSheetByName(SURVEY_SHEET) || ss.insertSheet(SURVEY_SHEET);
    const lastCol = sheet.getLastColumn();
    const header = lastCol ? sheet.getRange(1, 1, 1, lastCol).getValues()[0].filter(String) : [];
    for (const k of ["Timestamp"].concat(Object.keys(r))) if (header.indexOf(k) < 0) header.push(k);
    sheet.getRange(1, 1, 1, header.length).setValues([header]).setFontWeight("bold");
    sheet.setFrozenRows(1);
    sheet.appendRow(header.map((k) => (r[k] === undefined || r[k] === null ? "" : r[k])));
    return reply_({ ok: true });
  } finally {
    lock.releaseLock();
  }
}

function doGet() {
  return reply_({ ok: true, message: "Venous Pressure Map save endpoint is running." });
}

function sheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  return ss.getSheetByName(SHEET_NAME) || ss.insertSheet(SHEET_NAME);
}

/** Header row = existing columns plus any new keys, so adding a field never breaks old rows. */
function header_(sheet, keys) {
  const lastCol = sheet.getLastColumn();
  const header = lastCol ? sheet.getRange(1, 1, 1, lastCol).getValues()[0].filter(String) : [];
  const first = ["study_id", "procedure_date", "saved_at"];
  for (const k of first.concat(keys)) if (header.indexOf(k) < 0) header.push(k);
  sheet.getRange(1, 1, 1, header.length).setValues([header]).setFontWeight("bold");
  sheet.setFrozenRows(1);
  return header;
}

function findRow_(sheet, header, id, date) {
  const n = sheet.getLastRow() - 1;
  if (n < 1) return 0;
  const iId = header.indexOf("study_id"), iDate = header.indexOf("procedure_date");
  const rows = sheet.getRange(2, 1, n, header.length).getDisplayValues();
  for (let i = 0; i < rows.length; i++) {
    if (rows[i][iId] === id && String(rows[i][iDate]).slice(0, 10) === date) return i + 2;
  }
  return 0;
}

function reply_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
