# Kindle QuickSend (`kqs`)

A tiny, reliable Windows-friendly command-line tool to send Markdown notes and plain text documents to your Kindle effortlessly via **Amazon Send to Kindle**.

```
[Markdown / Text] ---> [Pandoc EPUB3] ---> [Gmail SMTP] ---> [Amazon Send to Kindle] ---> [Kindle over Wi-Fi]
```

## Features

- **High-quality EPUB3 generation:** Converts Markdown (`.md`, `.markdown`) and plain text (`.txt`) into clean EPUBs with table of contents, typography, headings, code blocks, tables, images, and full Hungarian / Unicode character support.
- **Embedded Pandoc:** Uses `pypandoc_binary`, bundling the exact Pandoc engine automatically—no manual Pandoc installation or system PATH tinkering needed.
- **Secure credential storage:** Gmail app passwords are saved directly into **Windows Credential Manager** (via `keyring`), never in plaintext configuration files or git repositories.
- **Zero background bloat:** No background services, no daemons, no databases, no external SaaS dependencies.
- **Multi-PC portability:** Designed to install independently and run identically across your desktop PC and laptops.
- **Native Windows conveniences:**
  - File picker when run without arguments (`kqs send`).
  - Windows Explorer **Send to → Kindle** right-click shortcut support.

---

## One-Time Preparation (Amazon & Gmail)

Before using Kindle QuickSend, ensure your accounts are linked:

1. **Gmail App Password (Sender):**
   - Ensure **2-Step Verification** is turned on in your Google Account.
   - Go to [Google App Passwords](https://myaccount.google.com/apppasswords).
   - Generate a 16-character App Password (e.g. name it `Kindle QuickSend`).
2. **Amazon Approved Sender (Recipient):**
   - Visit [Amazon Manage Your Content and Devices](https://www.amazon.com/myk).
   - Go to **Preferences** → **Personal Document Settings**.
   - Note your Kindle email address (e.g. `yourname@kindle.com`).
   - Under **Approved Personal Document E-mail List**, click **Add a new approved e-mail address** and add your Gmail address.

---

## Installation Across Your Three Computers

Follow these steps on each of your computers (desktop and laptops):

### Option A: Via `pipx` from Git (Recommended)

1. Make sure Python 3.11+ is installed (from [python.org](https://www.python.org/) or Microsoft Store).
2. Install `pipx` if you don't already have it:
   ```powershell
   python -m pip install --user pipx
   pipx ensurepath
   ```
   *(Restart your PowerShell terminal if `ensurepath` modified PATH).*
3. Install `kindle-quicksend`:
   ```powershell
   pipx install git+https://github.com/bceenaeiklmr/kindle-quicksend.git
   ```
4. Run initial setup:
   ```powershell
   kqs setup
   ```

### Option B: Local Editable Installation (Development)

```powershell
git clone https://github.com/bceenaeiklmr/kindle-quicksend.git
cd kindle-quicksend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
kqs setup
```

---

## Usage

### 1. Interactive Setup (`kqs setup`)

Configures your Kindle address, sender address, tests SMTP connectivity, and stores the app password in Windows Credential Manager:

```powershell
kqs setup
```

### 2. Send Document to Kindle (`kqs send`)

Send a specific Markdown or text document:
```powershell
kqs send notes.md
```

Or run without a filename to open the native Windows file picker:
```powershell
kqs send
```

Example output:
```
Converting 'notes.md' to EPUB ... OK
  Title: "Meeting Notes"
Sending to yourname@kindle.com ... OK

[OK] Submitted "Meeting Notes" to yourname@kindle.com.
Note: Gmail accepted the email. Delivery to your Kindle usually takes 1-5 minutes over Wi-Fi.
If Amazon encounters an issue, a notification will be sent to your@gmail.com.
```

### 3. Convert Locally (`kqs convert`)

Preview your document's EPUB output without emailing it:
```powershell
kqs convert notes.md -o output.epub
```

### 4. Windows Explorer Right-Click Shortcut ("Send to → Kindle")

To send any document directly from Windows File Explorer:

1. Press `Win + R`, enter `shell:sendto`, and press Enter.
2. In the folder that opens, right-click an empty space → **New** → **Shortcut**.
3. For target location, enter:
   ```cmd
   "%USERPROFILE%\.local\bin\kqs.exe" send --pause
   ```
   *(If using a virtual environment, replace with the full path to `kqs.exe`, e.g. `C:\dev\GitHub\kindle-quicksend\.venv\Scripts\kqs.exe send --pause`)*.
4. Name the shortcut **Kindle**.
5. **Done!** You can now right-click any `.md` or `.txt` file in Windows Explorer, select **Send to** → **Kindle**. The console will show progress and wait for Enter before closing.

---

## Document Formatting Tips

- **Title detection:**
  - If a YAML front-matter block contains `title: "Custom Title"`, that title is used.
  - Otherwise, the first level-1 heading (`# Title`) is used.
  - If neither is present, the filename stem is used.
- **Plain text (`.txt`):**
  - Paragraphs are separated by blank lines.
  - Markdown syntax characters (`#`, `*`, `_`, `[]`) are preserved verbatim without parsing.
- **Images:**
  - Local relative images (`![Diagram](diagram.png)`) are bundled directly into the EPUB.

---

## Security & Privacy

- **No hardcoded secrets:** App passwords are never stored in `config.toml` or log files.
- **OS-backed secret store:** Credentials are saved in **Windows Credential Manager** via the standard Windows DPAPI.
- **Safe temporary files:** Conversion artifacts are generated in isolated temporary folders and wiped immediately upon completion.
- **Source preservation:** Source files are read-only; originals are never modified or overwritten.

---

## Configuration & Logs

- **Config file:** `%APPDATA%\kindle-quicksend\config.toml` (contains non-secret addresses only).
- **Log file:** `%APPDATA%\kindle-quicksend\kqs.log` (rotating log, max 2 MB).
- **Verbose mode:** Add `-v` / `--verbose` to any command for live diagnostic output:
  ```powershell
  kqs -v send notes.md
  ```

---

## Running Tests

```powershell
pytest -v
```
