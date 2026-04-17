# What Could Break This Program — And How to Fix It

**Who this document is for:**
Anyone who has inherited this program and needs to keep it running — even if you
have never written a line of code in your life, and even if computers are not
your thing. This document assumes nothing.

---

## First: What Does This Program Actually Do?

Think of the IRS as a giant library. Every year, thousands of nonprofits are required
by law to publish a form called a Form 990, which lists how much they paid their
top employees. The IRS makes all of these forms available for free on their website.

This program is basically a robot librarian. You tell it which organizations you
care about (by their tax ID number), and it goes to the IRS's digital library,
finds the right forms, reads the compensation section, and saves everything into
a spreadsheet for you.

The problem is: the IRS's library occasionally gets reorganized. When that happens,
the robot can't find the books anymore. It doesn't know the library moved.
That's what this document is about — knowing when the library has been reorganized,
and knowing how to tell the robot where everything is now.

---

## The Good News

You do not need to understand the code to fix it.

There is an AI assistant called **Claude Code** that can read the code, understand
what's wrong, and fix it — on its own. Think of Claude Code like a very capable
intern who speaks fluent "computer." You describe the problem in plain English,
and it fixes it.

At the end of this document, there is a **ready-to-paste message** you can give to
Claude Code. It will do the investigation and the repair work for you.

---

## Try Claude Code First — It's Faster Than Reading This

Before scrolling through all the problems below, try this. Claude Code can
read the program, figure out what broke, fix it, and explain what it did —
in plain English, in a few minutes.

---

### Step 1: Open Claude Code in the project folder

1. Open Terminal
2. Type `cd ` (with a space after it), then drag the `990-pipeline` folder
   into the Terminal window. Press Enter.
3. Type `claude` and press Enter.

---

### Step 2: Paste one of the prompts below

Find the message that matches what you saw in the browser, copy the prompt
below it, paste it into Claude Code, and press Enter.

---

**"Could not download IRS index" — the program stopped before doing anything**

```
The 990 pipeline failed to download the IRS filing index. The error I saw was:

[PASTE THE ERROR MESSAGE FROM THE BROWSER HERE]

Please check whether the IRS index URL is still correct and reachable.
The URL pattern used is in modules/filing_fetcher.py under IRS_INDEX_CSV_URL.
If the IRS has moved the file, find the new location and update the URL.
Explain what you found and what you changed, in plain English.
```

---

**"Could not locate or download XML" for every single org**

```
The 990 pipeline downloaded the IRS index successfully, but then failed to
find or download the XML filing for every single organization. The error I saw was:

[PASTE THE ERROR MESSAGE FROM THE BROWSER HERE]

Please check whether the IRS has changed how XML files are stored inside
their batch ZIP files. Look at find_batch_and_download_xml() in
modules/filing_fetcher.py and compare it against a real recent batch ZIP.
Fix any mismatch you find. Explain what changed and what you fixed.
```

---

**"Unsupported ZIP compression method" warnings**

```
The 990 pipeline is showing "Unsupported ZIP compression method" warnings
for some organizations. The error I saw was:

[PASTE THE ERROR MESSAGE FROM THE BROWSER HERE]

Please check what compression method number is being rejected, look at the
decompression logic in download_and_decompress_xml_from_zip() in
modules/filing_fetcher.py, and add support for the new compression method
if a suitable Python library exists. Explain what you found and fixed.
```

---

**"No 990 filing found" for every single org (but the index downloaded fine)**

```
The 990 pipeline downloaded the IRS index and found filings for the year,
but then reported "No 990 filing found" for every single organization.
The error I saw was:

[PASTE THE ERROR MESSAGE FROM THE BROWSER HERE]

Please check whether the IRS has renamed the columns in their index CSV.
Look at find_filing_in_index() in modules/filing_fetcher.py and compare
the expected column names against the actual columns in the current index.
Fix any column name mismatches. Explain what you found and changed.
```

---

**Output CSV is empty or every org shows "no compensation data found"**

```
The 990 pipeline ran successfully and found filings for all organizations,
but the output CSV has zero rows, or every org shows that no compensation
data was found. The error or output I saw was:

[PASTE THE ERROR MESSAGE OR OUTPUT SUMMARY FROM THE BROWSER HERE]

Please check whether the IRS has changed the XML tag names used in Part VII
of the 990 form. Look at modules/parser.py and compare the tag names it
searches for against the actual tags in a recent real 990 XML filing.
Fix any mismatches. Explain what changed and what you updated.
```

---

**Program crashes immediately at startup with a technical error**

```
The 990 pipeline crashes right when I start it, before it does anything.
The full error message is:

[PASTE THE ENTIRE ERROR MESSAGE HERE — COPY EVERYTHING FROM THE TERMINAL OR BROWSER]

Please diagnose what caused this crash. Check whether it is a Python library
version incompatibility, a missing dependency, or a syntax/import error.
Fix it and explain what was wrong and what you changed.
```

---

**Not sure what happened — general diagnostic**

```
Something went wrong with the 990 pipeline. Here is what I saw:

[PASTE THE FULL OUTPUT OR ERROR FROM THE BROWSER HERE]

Please read the pipeline code, look at what the error says, figure out
what broke, fix it, and explain in plain English:
  - What went wrong
  - What you changed to fix it
  - Whether it is working now
  - Anything that still needs a human to look at
```

---

That's it. Claude Code will read the code, investigate the problem, make
any fixes, and report back in plain English.

If you don't have Claude Code installed yet, jump to the section
"How to Fix It Using Claude Code" near the bottom of this document.

---

## What Could Go Wrong

Here are all the things that could cause this program to stop working,
written in plain English.

---

### Problem 1: The IRS Moved Where the Files Are Stored

**The simple version:**
Imagine the IRS's filing system is like a filing cabinet. For years, the Form 990
files for a given organization were kept in a labeled folder inside a drawer
(think: drawer = a ZIP archive, folder = a named subfolder inside it).

In 2025, the IRS stopped using the labeled folder. Now the files sit loose in the
drawer with no folder — same drawer, just no folder inside.

This already broke the program once. We fixed it. But the IRS could reorganize
again in the future in a way we haven't seen yet.

**How would you know this happened?**
You run the program, and every single organization fails with the same message:
"Could not locate or download XML." Not one or two — every single org, all of them.
The program found the organizations just fine (it found their tax ID in the index),
it just couldn't open the actual file.

**What to do:**
Go to the section "How to Fix It Using Claude Code" at the bottom of this document.
Use the prompt provided there.

---

### Problem 2: The IRS Changed the Website Address

**The simple version:**
The program goes to a specific web address (like a URL) to download IRS data.
In 2021, the IRS moved everything from one web address to a different one
without warning. Any program using the old address stopped working immediately.
This could happen again.

**How would you know this happened?**
The program fails at the very first step — before it even starts looking for
your organizations. You will see something like:
"Could not download IRS index."
The program never gets past that first step. Nothing works at all.

**What to do:**
1. Open a web browser (Chrome, Safari, etc.)
2. Go to: `https://apps.irs.gov/pub/epostcard/990/`
3. See if the page loads and the files are there
4. If the page is gone or looks completely different, the IRS moved the files
5. Use the Claude Code prompt at the bottom — describe what you saw on the page

---

### Problem 3: The IRS Renamed the Columns in Their Spreadsheet

**The simple version:**
The IRS publishes a giant spreadsheet (called the "index") listing every 990
filing that exists. The program reads specific columns from that spreadsheet —
like "EIN" (the tax ID) and "OBJECT_ID" (a unique file number).

If the IRS ever changes what those columns are called — like renaming "EIN"
to "TAXPAYER_ID" — the program would look for a column that doesn't exist
and fail.

**How would you know this happened?**
The index downloads successfully (the program says something like "748,906 filings
found"), but then every organization shows "No 990 filing found" — even ones you
know have definitely filed.

**What to do:**
Use the Claude Code prompt at the bottom of this document.

---

### Problem 4: The IRS Changed What's Inside the 990 XML Files

**The simple version:**
The Form 990 is an XML file — think of it like a very structured document with
labeled sections. The program knows to look for a section called, for example,
"OfficerDirectorTrusteeKeyEmplGrp" to find the compensation data.

If the IRS renames that section to something else in a future version of the form,
the program won't find any compensation data — even though it successfully
downloaded the filing.

**How would you know this happened?**
The program runs, finds all your organizations, downloads their filings — but
the final spreadsheet is empty (zero rows), or the program says something like
"Filing was found but contained no Part VII compensation data" for every org.

**What to do:**
Use the Claude Code prompt at the bottom. Claude Code can look at an actual
recent filing and find out what the sections are named now.

---

### Problem 5: An Organization Filed Their Taxes Late — Or Didn't File At All

**The simple version:**
The IRS only includes filings in their index after the filing is received and
processed. If a nonprofit is late filing their Form 990, their data won't be in
the system when you run the program.

This is not a bug in the program. The data simply isn't available yet.

**How would you know this happened?**
One or a few specific organizations (not all of them) show up in the "ACTION NEEDED"
section at the end of the run with the reason:
"No 990 filing found in the [year] IRS index."

**What to do:**
No code fix needed. Your options are:
- **Wait and try again later** — the IRS adds late filings throughout the year
- **Look up the org manually** on ProPublica's nonprofit database:
  Go to `https://projects.propublica.org/nonprofits/` and search by organization name
- **Check if the EIN is correct** — see Problem 6 below

---

### Problem 6: An Organization's Tax ID Number Is Wrong in the List

**The simple version:**
Every organization has a unique 9-digit tax ID number (called an EIN). The program
uses this number to find their filing. If the number is wrong — even by one digit —
the program can't find the organization.

EINs are permanent and don't change. But mergers, name changes, or a simple typo
when someone entered it could result in a wrong number in the list.

**How would you know this happened?**
One specific organization shows "No 990 filing found" — but you know they exist and
definitely file. Other organizations around it work fine.

**What to do:**
1. Go to ProPublica: `https://projects.propublica.org/nonprofits/`
2. Search for the organization by name
3. Find their correct EIN
4. Open the file `config.py` in the pipeline folder
5. Find the organization's entry and correct the `"ein"` number
6. Or use Claude Code: describe the organization, and ask it to update the EIN

---

### Problem 7: The Program Won't Start — Port Conflict

**The simple version:**
This program runs a tiny local website on your computer that you access in your
browser. It needs a "port" — think of this like a specific door to knock on.
The default door is number 5000.

If another program on your computer is already using door 5000, this program will
automatically try doors 5001 through 5019. If all 20 doors are occupied
(which almost never happens), it gives up.

**How would you know this happened?**
The Terminal window shows:
"ERROR: Could not find an open port between 5000 and 5019."

**What to do:**
The most common cause is Apple's AirPlay Receiver feature, which uses port 5000.
To turn it off:
1. Click the Apple  menu (top-left corner of your screen)
2. Select **System Settings**
3. Click **General**
4. Click **AirDrop & Handoff**
5. Turn off **AirPlay Receiver**
6. Try starting the program again

---

### Problem 8: The Launcher File Won't Open — macOS Security

**The simple version:**
When you receive a file from someone else (like this entire program folder),
macOS is cautious about letting it run automatically. It may block the launcher
file and show a message like "Cannot be opened because the developer cannot
be verified."

**What to do:**
1. Find the `START_PIPELINE.command` file in the program folder
2. Instead of double-clicking it, **right-click** (or hold Control and click)
3. Select **Open** from the menu that appears
4. A warning will appear — click **Open** to confirm
5. This tells macOS you trust this file, and it will work normally going forward

If that still doesn't work:
1. Open Terminal (find it in Applications → Utilities, or search with Spotlight)
2. Type: `chmod +x ` (with a space after it)
3. Drag and drop the `START_PIPELINE.command` file into the Terminal window
   (this pastes its full path automatically)
4. Press Enter
5. Try double-clicking the launcher again

---

### Problem 9: The Program Crashes Right at Startup — Library Error

**The simple version:**
The program relies on several helper tools (called libraries) created by other
developers. Very occasionally, these libraries release updates that accidentally
break compatibility. The program would crash immediately when you start it.

**How would you know this happened?**
The program crashes right away — before it does anything — with an error that
looks technical and confusing, like:
`AttributeError: 'DataFrame' object has no attribute...`
or similar.

**What to do:**
Copy the entire error message, then use the Claude Code prompt at the bottom —
paste the error into your message along with the standard prompt.

---

## How to Fix It Using Claude Code

This section explains what Claude Code is, how to install it once, and how to
use it whenever something breaks.

---

### What Is Claude Code?

Claude Code is an AI assistant — similar to ChatGPT, but designed specifically
to work with code files. Instead of using it through a website, you use it
directly inside the program folder on your computer. It can read all the files
in the folder, understand what they do, and make changes to fix problems.

You talk to it in plain English. No coding knowledge required.

---

### One-Time Setup: Installing Claude Code

You only need to do this once. After it's installed, it's there forever.

**Step 1: Check if Node.js is installed**

Node.js is a technical requirement for Claude Code (you don't need to understand
what it is — just install it).

1. Open Terminal (Applications → Utilities → Terminal, or search "Terminal"
   with Spotlight — the magnifying glass icon at the top right of your screen)
2. Type: `node --version` and press Enter
3. If you see something like `v22.0.0` — you're good. Skip to Step 2.
4. If you see "command not found" — go to `https://nodejs.org/` and click
   the big "Download Node.js (LTS)" button. Install it like any other app.

**Step 2: Install Claude Code**

1. In Terminal, type exactly:
   ```
   npm install -g @anthropic-ai/claude-code
   ```
2. Press Enter and wait. It may take a minute.
3. When it finishes (you'll see the `$` prompt again), type:
   ```
   claude --version
   ```
4. If you see a version number, Claude Code is installed.

**Step 3: Log in to Claude Code**

1. Type: `claude` and press Enter
2. Claude Code will open and ask you to log in
3. Go to `https://claude.ai` and create a free account if you don't have one
4. Follow the on-screen instructions to link your account

---

### Using Claude Code When Something Breaks

Every time you need to fix the program, do this:

**Step 1: Open Terminal**

**Step 2: Navigate to the program folder**

Type `cd ` (with a space), then drag the `990-pipeline` folder from Finder
into the Terminal window. Press Enter.

(You should see the path to the folder appear, like:
`/Users/YourName/Documents/990-pipeline`)

**Step 3: Start Claude Code**

Type: `claude` and press Enter.

**Step 4: Give it permission**

The first time in a new folder, it will ask:
"Do you trust the files in this folder?"
Type `yes` and press Enter.

**Step 5: Paste this prompt**

Copy everything inside the box below and paste it into Claude Code.
Then press Enter and let it work.

---

```
You are helping maintain a Python pipeline that downloads IRS Form 990 XML filings
and extracts executive compensation data. Something may have broken because the
IRS has changed something on their end.

Please do the following:

1. CHECK THE IRS INDEX
   Download the IRS filing index for the most recent available year:
   https://apps.irs.gov/pub/epostcard/990/xml/{year}/index_{year}.csv
   Confirm the column names match what the code in modules/filing_fetcher.py
   expects. If column names have changed, update the code.

2. CHECK THE BATCH ZIP STRUCTURE
   Download the central directory of one known batch ZIP for the most recent year.
   Check whether XML files are stored inside a named subfolder or at the root level.
   Update find_batch_and_download_xml() in modules/filing_fetcher.py if needed.

3. CHECK THE BATCH NAMING CONVENTION
   Confirm what batch name suffixes the IRS currently uses (A, B, C, D, etc.).
   If build_monthly_batch_search_order() is missing any suffixes, add them.

4. CHECK THE XML SCHEMA
   Download one actual 990 XML filing for a known organization.
   Confirm the tag names in modules/parser.py still match what the IRS uses for
   Part VII compensation data. If tag names have changed, update the parser.

5. WHEN YOU ARE DONE:
   a. Make all necessary code changes.
   b. Write a plain-English summary — written for someone who has never seen code —
      explaining:
      - What you found (did the IRS change something? what?)
      - What you fixed (what did you update, and why does it matter?)
      - Whether the pipeline is now working correctly
      - Anything that still needs a human to look at it
      - How confident you are that everything is fixed

Keep the explanation simple enough that a person who just started using
computers can understand it.
```

---

That's it. Claude Code will read the program, check the IRS website, compare
what it finds to what the code expects, fix any mismatches, and explain
everything it did in plain English.

---

## Quick Reference Card

Cut this out and keep it nearby if you like.

| What you see when you run the program | What probably happened | Where to look |
|---|---|---|
| "Could not download IRS index" — nothing works | IRS changed their website address | Problem 2 |
| "No 990 filing found" for ALL orgs | IRS renamed columns in their spreadsheet | Problem 3 |
| "Could not locate or download XML" for ALL orgs | IRS changed how files are stored in ZIPs | Problem 1 |
| Output spreadsheet is empty / zero rows | IRS changed tag names inside XML files | Problem 4 |
| One or two orgs missing, rest work fine | Late filer or wrong EIN | Problems 5 & 6 |
| "Could not find an open port" at startup | Port 5000 is being used by another app | Problem 7 |
| Launcher won't open at all | macOS blocked the file | Problem 8 |
| Program crashes immediately with technical error | Library version conflict | Problem 9 |

For all technical problems: use Claude Code with the prompt in this document.
