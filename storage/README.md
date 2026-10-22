# Saving cases to the study sheet

The website sends two kinds of rows to one Google Sheet:

- **Readings** tab: the app's **Save to study records** button, one row per
  case (study ID, procedure date, unit, side, every reading before and after
  stent, where the narrowing is, the gradient).
- **Survey** tab: the patient survey page (`survey.html`), one anonymous row
  per patient, with the same columns as a Google Forms export. The analysis
  script reads it directly.

**No names or MRNs.**

The study ID ↔ MRN key is a separate file kept only in the secure team folder
(for example Penn Box). Add a row there each time you give out a new ID.

## Set up once (about 5 minutes)

Use the study's institutional Google account, not a personal one. The rows
include procedure dates, so check with the IRB/QI office which Google account
is approved.

1. Make a new Google Sheet, for example "Venous pressure records".
2. In the sheet: **Extensions → Apps Script**. Delete the stub code, paste all
   of [`save_readings.gs`](save_readings.gs), and click **Save**.
3. **Project Settings** (gear icon) → **Script properties** → **Add property**:
   `PASSCODE` = a team passcode. Share it with the team in person. It is never
   stored in GitHub.
4. **Deploy → New deployment →** type **Web app**. Set *Execute as*: **Me**, and
   *Who has access*: **Anyone**. Click **Deploy** and allow access.
5. Copy the **Web app URL** (it ends in `/exec`) into `storage.json` at the repo
   root (`"endpoint": "https://script.google.com/macros/s/…/exec"`). Then commit
   and push.

The first time someone saves, or sets up a survey on a computer, the website
asks for the passcode and remembers it in that browser.

## Good to know

- **Saving the same study ID and date again** overwrites that row, so
  corrections are easy.
- **Study IDs** must look like `VP-0001` (letters, then numbers). Long numbers
  that look like MRNs are refused.
- **After editing the script:** go to **Deploy → Manage deployments**, edit the
  deployment, choose **New version**, then **Deploy**. The URL stays the same.
- **If saving isn't set up,** or the internet is down, use **Readings (CSV)**
  and paste the row into the sheet by hand.
- **Survey offline:** if the internet drops, the answers are kept on that
  computer and sent automatically the next time the survey page opens.
