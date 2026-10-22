/**
 * build_form.gs  -  builds the "Venous Sinus Stenting Patient Education" survey
 * ============================================================================
 *
 * WHAT THIS DOES
 *   Running buildSurvey() once creates, in YOUR Google Drive:
 *     1. a new Google Form with every question defined in SURVEY below;
 *     2. a new Google Sheet linked to the form, where answers will land;
 *     3. a "Links" tab in that Sheet holding the two PRE-FILLED patient links
 *        (clinic code A and clinic code B). Make a QR code from each one.
 *   The same two links are also printed in the Execution log.
 *
 * HOW TO RUN IT (first time using Apps Script? follow these exactly)
 *   1. Go to https://script.google.com and sign in with the Google account
 *      that should own the form (use the study/clinic account, not a personal one).
 *   2. Click "New project". Delete the little "function myFunction() {}" stub.
 *   3. Copy ALL of this file and paste it into the editor. Click the save
 *      (disk) icon. Rename the project if you like (e.g. "Stenting survey builder").
 *   4. In the toolbar, make sure the function drop-down says "buildSurvey",
 *      then click "Run".
 *   5. The first time, Google asks for permission ("Authorization required"):
 *        Review permissions -> choose your account -> if you see
 *        "Google hasn't verified this app", click "Advanced" ->
 *        "Go to <project name> (unsafe)" -> "Allow".
 *      This is normal: the "app" is your own script. It needs permission to
 *      create Forms and Sheets in your Drive. Nothing is sent anywhere else.
 *   6. Wait for "Execution completed" (about 10-30 seconds). Open
 *      "Execution log" at the bottom: it lists the form editor link, the
 *      response Sheet link and the two patient links (A and B).
 *   7. Open the Sheet -> "Links" tab. Make one QR code per link
 *      (see survey/README.md). Do NOT hand out the plain form link: it has no
 *      clinic code, so those answers cannot be analysed.
 *
 * RE-RUNNING
 *   Every run creates a BRAND-NEW form, Sheet and pair of links. Nothing old
 *   is changed or deleted. Old links keep pointing to the old form, and old
 *   answers stay in the old Sheet. So: re-run only when you mean to replace
 *   the form, then reprint the QR codes and stop accepting responses on the
 *   old form (Form -> Responses tab -> turn off "Accepting responses").
 *
 * EDITING A QUESTION
 *   Edit the SURVEY block below AND survey/answer_key.json, keeping titles and
 *   options word-for-word identical, then run the tests
 *   (.venv/bin/python -m pytest tests/test_survey_analysis.py -q).
 *   The analysis script finds each answer column by its exact question title.
 *   The SURVEY block must stay valid JSON (the tests read it): double quotes
 *   only, no trailing commas, no comments inside the block.
 *
 * DESIGN NOTES
 *   - Every 1-5 scale runs the same way: 5 = best (most understanding, most
 *     clear, most comfortable, strongly agree, excellent).
 *   - The staff-only "Clinic code" item shows only "A" or "B". What A and B
 *     mean is kept in the study README only, never in the form, so patients
 *     are not told which group they are in.
 *   - The "code" fields are internal keys for the analysis; patients never see them.
 */

// ===== BEGIN SURVEY =====
const SURVEY = {
  "formTitle": "Venous Sinus Stenting Patient Education Survey",
  "formDescription": "A short, anonymous survey. It takes about 5 minutes.",
  "confirmationMessage": "Thank you for taking the time to fill this out. Your answers help us take better care of our patients.\n\nIf anything is still unclear, please ask your care team before you leave.",
  "sections": [
    {
      "title": "Consent",
      "help": "This survey is part of a project to improve how we explain venous sinus stenting to patients and families.\n\nIt is anonymous. We do not ask for your name or anything that could identify you.\n\nTaking part is your choice. It will not change your care, or your family member's care, in any way.",
      "items": [
        {
          "code": "consent",
          "title": "Do you agree to take part in this survey?",
          "type": "multiple_choice",
          "required": true,
          "options": ["Yes, I agree to take part", "No, I do not want to take part"],
          "endFormOn": "No, I do not want to take part"
        }
      ]
    },
    {
      "title": "For clinic staff",
      "help": "This page is already filled in. Please tap Next.",
      "items": [
        {
          "code": "group",
          "title": "Clinic code",
          "type": "dropdown",
          "required": true,
          "options": ["A", "B"]
        }
      ]
    },
    {
      "title": "Your understanding",
      "help": "How well do you understand each of these right now?",
      "items": [
        {
          "code": "und_why",
          "title": "I understand why this procedure is being recommended",
          "type": "scale",
          "required": true,
          "lowLabel": "I don't understand",
          "highLabel": "I understand completely"
        },
        {
          "code": "und_what",
          "title": "I understand what will happen during the procedure",
          "type": "scale",
          "required": true,
          "lowLabel": "I don't understand",
          "highLabel": "I understand completely"
        },
        {
          "code": "und_after",
          "title": "I understand what I will need to do after the procedure (such as taking medicine and coming back for check-ups)",
          "type": "scale",
          "required": true,
          "lowLabel": "I don't understand",
          "highLabel": "I understand completely"
        },
        {
          "code": "und_risks",
          "title": "I understand the main risks and benefits of the procedure of the procedure",
          "type": "scale",
          "required": true,
          "lowLabel": "I don't understand",
          "highLabel": "I understand completely"
        }
      ]
    },
    {
      "title": "A few quick questions",
      "help": "This is not a test. We just want to check that we explained the key points well.\n\nIf you are not sure, choose \"I'm not sure\". Because the survey is anonymous, we won't see your answers, so please ask your care team any questions before you leave.",
      "items": [
        {
          "code": "k_reason",
          "title": "What is the main reason for this procedure?",
          "type": "multiple_choice",
          "required": true,
          "options": [
            "To open a blocked artery, like a heart procedure",
            "To lower the pressure in my head that causes my symptoms",
            "To remove a tumor that is pressing on my brain",
            "I'm not sure — please explain this again"
          ]
        },
        {
          "code": "k_after",
          "title": "After the procedure, what will you most likely need to do?",
          "type": "multiple_choice",
          "required": true,
          "options": [
            "Stay in bed at home for about a month",
            "Come back every week for a shot of medicine",
            "Take a blood-thinning medicine for a few months",
            "I'm not sure — please explain this again"
          ]
        },
        {
          "code": "k_followup",
          "title": "Why are follow-up visits needed?",
          "type": "multiple_choice",
          "required": true,
          "options": [
            "To check that the stent works and my symptoms improve",
            "To have the stent taken out after a few weeks",
            "To put in a new stent at each visit",
            "I'm not sure — please explain this again"
          ]
        },
        {
          "code": "k_symptoms",
          "title": "Which symptoms is this procedure meant to help?",
          "help": "Choose all that apply.",
          "type": "checkbox",
          "required": true,
          "options": [
            "Headaches or pressure in the head",
            "A whooshing sound in the ear",
            "Blurry vision or other vision problems",
            "Stomach pain",
            "I'm not sure"
          ]
        }
      ]
    },
    {
      "title": "How you feel right now",
      "help": "There are no wrong answers. This helps us learn how to explain things better.",
      "items": [
        {
          "code": "conf_clear",
          "title": "How clear are you about what will happen?",
          "type": "scale",
          "required": true,
          "lowLabel": "Not clear at all",
          "highLabel": "Very clear"
        },
        {
          "code": "conf_risks",
          "title": "How comfortable do you feel with the risks and benefits?",
          "type": "scale",
          "required": true,
          "lowLabel": "Not comfortable",
          "highLabel": "Very comfortable"
        },
        {
          "code": "conf_explain",
          "title": "If a friend asked about your procedure, how well could you explain it?",
          "type": "scale",
          "required": true,
          "lowLabel": "I couldn't explain it",
          "highLabel": "I could explain it well"
        }
      ]
    },
    {
      "title": "About today's visit",
      "help": "",
      "items": [
        {
          "code": "sat_clear",
          "title": "The explanation was clear and easy to follow",
          "type": "scale",
          "required": true,
          "lowLabel": "Strongly disagree",
          "highLabel": "Strongly agree"
        },
        {
          "code": "sat_time",
          "title": "I had enough time to ask questions",
          "type": "scale",
          "required": true,
          "lowLabel": "Strongly disagree",
          "highLabel": "Strongly agree"
        },
        {
          "code": "sat_overall",
          "title": "Overall, how would you rate today's discussion?",
          "type": "scale",
          "required": true,
          "lowLabel": "Poor",
          "highLabel": "Excellent"
        }
      ]
    },
    {
      "title": "About you (optional)",
      "help": "You can skip any of these. They help us see whether different people need different kinds of explanation.",
      "items": [
        {
          "code": "respondent",
          "title": "Who is filling out this survey?",
          "type": "multiple_choice",
          "required": false,
          "options": ["The patient", "A family member or caregiver", "Prefer not to say"]
        },
        {
          "code": "age",
          "title": "What is your age range?",
          "type": "multiple_choice",
          "required": false,
          "options": ["18 to 34", "35 to 49", "50 to 64", "65 or older", "Prefer not to say"]
        },
        {
          "code": "prior_proc",
          "title": "Have you had a procedure on your brain or spine before?",
          "type": "multiple_choice",
          "required": false,
          "options": ["Yes", "No", "Prefer not to say"]
        },
        {
          "code": "familiarity",
          "title": "Before today, how familiar were you with medical procedures?",
          "type": "multiple_choice",
          "required": false,
          "options": [
            "Very familiar (I work in health care or have had several procedures)",
            "Somewhat familiar",
            "Not very familiar (this is new to me)",
            "Prefer not to say"
          ]
        }
      ]
    },
    {
      "title": "Anything else?",
      "help": "",
      "items": [
        {
          "code": "open_help",
          "title": "What would have helped you understand better?",
          "type": "paragraph",
          "required": false
        },
        {
          "code": "open_feedback",
          "title": "Do you have any other comments about today's visit?",
          "type": "paragraph",
          "required": false
        }
      ]
    }
  ]
};
// ===== END SURVEY =====


/** Run this one. Creates a new form + response Sheet + pre-filled A/B links. */
function buildSurvey() {
  const form = FormApp.create(SURVEY.formTitle);
  form.setDescription(SURVEY.formDescription);
  applySettings_(form);

  let groupItemId = null;
  SURVEY.sections.forEach(function (section, i) {
    if (i === 0) {
      // The first page has no page break; show its title/help as a header.
      form.addSectionHeaderItem().setTitle(section.title).setHelpText(section.help || '');
    } else {
      form.addPageBreakItem().setTitle(section.title).setHelpText(section.help || '');
    }
    section.items.forEach(function (q) {
      const item = addItem_(form, q);
      if (q.code === 'group') groupItemId = item.getId();
    });
  });
  if (groupItemId === null) throw new Error('SURVEY has no item with code "group".');

  // Response Sheet. The first tab becomes "Links"; Forms adds its own
  // "Form Responses 1" tab when the destination is set.
  const ss = SpreadsheetApp.create(SURVEY.formTitle + ' (Responses)');
  const linksSheet = ss.getSheets()[0].setName('Links');
  form.setDestination(FormApp.DestinationType.SPREADSHEET, ss.getId());

  const links = makePrefilledLinks_(form, groupItemId, ['A', 'B']);
  writeLinksSheet_(linksSheet, form, ss, links);

  Logger.log('Form editor:      ' + form.getEditUrl());
  Logger.log('Response Sheet:   ' + ss.getUrl());
  Logger.log('Patient link, clinic code A: ' + links.A);
  Logger.log('Patient link, clinic code B: ' + links.B);
  Logger.log('Make one QR code per patient link. Do NOT share the plain form link.');
}


function applySettings_(form) {
  form.setProgressBar(true);
  form.setAllowResponseEdits(false);
  form.setLimitOneResponsePerUser(false);   // shared clinic tablet: many responses per device/account
  form.setShowLinkToRespondAgain(true);
  form.setPublishingSummary(false);
  form.setConfirmationMessage(SURVEY.confirmationMessage);
  form.setAcceptingResponses(true);
  // These calls differ between account types / Forms versions; failures are harmless.
  tryCall_('setCollectEmail(false)', function () { form.setCollectEmail(false); });
  tryCall_('setRequireLogin(false)', function () { form.setRequireLogin(false); });
  tryCall_('setPublished(true)', function () {
    if (typeof form.setPublished === 'function') form.setPublished(true);
  });
}


function addItem_(form, q) {
  let item;
  switch (q.type) {
    case 'multiple_choice': {
      item = form.addMultipleChoiceItem();
      if (q.endFormOn) {
        // Chosen option ends the form (SUBMIT); all others continue.
        item.setChoices(q.options.map(function (opt) {
          return item.createChoice(opt, opt === q.endFormOn
            ? FormApp.PageNavigationType.SUBMIT
            : FormApp.PageNavigationType.CONTINUE);
        }));
      } else {
        item.setChoiceValues(q.options);
      }
      break;
    }
    case 'dropdown':
      item = form.addListItem().setChoiceValues(q.options);
      break;
    case 'checkbox':
      item = form.addCheckboxItem().setChoiceValues(q.options);
      break;
    case 'scale':
      item = form.addScaleItem().setBounds(1, 5).setLabels(q.lowLabel, q.highLabel);
      break;
    case 'paragraph':
      item = form.addParagraphTextItem();
      break;
    default:
      throw new Error('Unknown question type "' + q.type + '" for ' + q.code);
  }
  item.setTitle(q.title).setRequired(Boolean(q.required));
  if (q.help) item.setHelpText(q.help);
  return item;
}


function makePrefilledLinks_(form, groupItemId, codes) {
  const listItem = form.getItemById(groupItemId).asListItem();
  const links = {};
  codes.forEach(function (code) {
    const response = form.createResponse();   // not submitted; only used to build the URL
    response.withItemResponse(listItem.createResponse(code));
    links[code] = response.toPrefilledUrl();
  });
  return links;
}


function writeLinksSheet_(sheet, form, ss, links) {
  const rows = [
    ['What', 'Link / note'],
    ['Patient link - clinic code A', links.A],
    ['Patient link - clinic code B', links.B],
    ['How to use', 'Make one QR code from each patient link (e.g. Google Chrome: right-click the page -> "Create QR code", or any free QR generator). Print them on two staff-only cards. After each discussion, staff show the patient the QR code that matches what was done. Which code means which discussion is written in the study README, not here or in the form.'],
    ['Do not use', 'The plain form link below has no clinic code; answers from it cannot be analysed.'],
    ['Plain form link (do not hand out)', form.getPublishedUrl()],
    ['Form editor (staff)', form.getEditUrl()],
    ['Response Sheet (this file)', ss.getUrl()],
    ['Created', new Date().toString()],
    ['Answers', 'Answers appear in the "Form Responses 1" tab. Do not rename its column headers: the analysis script matches them to survey/answer_key.json.']
  ];
  sheet.getRange(1, 1, rows.length, 2).setValues(rows);
  sheet.getRange(1, 1, 1, 2).setFontWeight('bold');
  sheet.setColumnWidth(1, 260);
  sheet.setColumnWidth(2, 700);
  sheet.getRange(1, 2, rows.length, 1).setWrap(true);
}


function tryCall_(label, fn) {
  try {
    fn();
  } catch (e) {
    Logger.log('Note: ' + label + ' was skipped (' + e.message + '). This is usually fine.');
  }
}
