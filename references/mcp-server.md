# Unit4 MCP Server

`mcp/` has a small MCP server that runs this skill's Unit4 browser steps
through Playwright on the user's own Chrome tab. Each tool replaces a
screenshot-and-click phase with one guarded call.

## How it connects

- The server starts `@playwright/mcp --extension` as a stdio child process.
  It only ever calls that child's `browser_run_code` tool, with scripts
  composed from `mcp/src/page/ops.js`. Arguments are embedded as JSON
  literals.
- The Playwright Extension attaches to the tab the user picks on its
  "Allow & select" page. The SSO session is reused. There is no remote-debug
  port and no separate profile.
- Do not use `@playwright/mcp`'s library API (`createConnection`) in extension
  mode. It reads `browser.contexts()[0]` before a tab is shared, then fails with
  `Cannot read properties of undefined (reading 'once')`.
- Chrome saves downloads itself, so Playwright gets no download events. The
  server identifies each new `Rapporter_<timestamp>.zip` or `<prefix>_<order>.log`
  from a before/after listing of the download folder, matching only that
  pattern. It never deletes or overwrites anything there. Override the folder
  with `UNIT4_DOWNLOAD_DIR`.

## Setup

1. Install the Playwright Extension in the Chrome profile that is signed in to
   Unit4:
   `https://chromewebstore.google.com/detail/playwright-extension/mmlmfjhmonkocbjadbfplnigmagldckm`
2. Install the server's dependencies. This needs Node 23.6 or later, which
   runs the TypeScript sources directly:

   ```text
   make mcp-install
   ```

3. Register the server with the agent host, using the absolute path of this
   skill:
   - **Claude Code** (user scope, so the skill works from any directory):
     `claude mcp add --scope user unit4 -- node <skill-root>/mcp/src/server.ts`.
     Inside this repository, `.mcp.json` registers it at project scope.
   - **Codex** (`~/.codex/config.toml`):

     ```toml
     [mcp_servers.unit4]
     command = "node"
     args = ["<skill-root>/mcp/src/server.ts"]
     ```

4. `UNIT4_PYTHON` overrides the interpreter used for `scripts/run_manifest.py`
   (default `python3`).

## Operating rules for users

- Keep the shared Unit4 tab's window open and not minimized. Other apps and
  windows can be on top of it. When Chrome reports the tab as hidden it stops
  painting it, and Playwright's click checks then fail. The tools check this
  first and return `NEEDS_USER` / `window_hidden`.
- Make the window tall enough, preferably maximized with DevTools closed. The
  supplier form's bottom toolbar **Lagre** sits about 650 px down the page, and
  a shorter window leaves it outside the viewport. Playwright then refuses the
  click (`element is outside of the viewport`), and `unit4_order` returns
  `RETRY_ALLOWED` without having clicked. `unit4_probe_lagre` checks this
  read-only.
- Do not use the shared tab or other Unit4 tabs during a run.
- Unit4 allows at most 10 open activities per session. A log view (TRA014)
  counts as one, and so do report forms and the order table. The tools reuse
  one tab per report type, close log views after reading them, and close the
  run's tabs for that company after a successful download
  (`unit4_close_tabs` does the same on demand). When Unit4 still refuses
  (`Systemet tillater at opptil 10 aktiviteter er åpne samtidig`), the tools
  log out and return to the application once, which reopens Unit4 in the same
  session with every activity closed, then restore the company and retry.
  `unit4_reset_activities` does the same on demand (at most 3 per server
  session). This also closes Unit4 activities the user opened. Clearing the
  buffer did not clear the limit on 2026-09-29.

## Unit4 DOM notes (CR 26.1)

These notes come from read-only discovery and one confirmed test order
(Råbalanse 18574, company 312, period 202608, on 2026-09-29).

- **Top page**: ExtJS. The company button in toolbar `Program` is labelled
  `<code> <name>`. The global search is combobox `Søk (Alt+q)`. It needs key
  events, and each result `.u4-search-result-item` has a title `<b>`, a
  `.u4-menu-search-result-viewid` (`Vindus-ID: TRA015`) and a
  `.u4-menu-search-result-path`. The previous query's results stay visible
  until the new ones arrive.
- **Tabs**: `role=tab` with accessible name `<company> <title> : <window id>`.
  `aria-controls` names the `#activity-N` panel. The close control is the
  `.x-tab-close-btn` in the same `div.x-tab`.
- **Frames**: each panel holds `Container.aspx` iframes, one per stacked
  activity with the last one on top. Each has a child frame named
  `contentcontainer`. Its `name` is not an HTML attribute, so resolve frames
  through element handles. Inactive panels are `display:none`.
- **Report forms (ASP.NET)**: `h1.PageTitle`. Every parameter is a
  `table.Control` with the `role=combobox` editor (labelled), a hidden
  `input[id$="_RowValue"]` holding the **committed** value, and either
  `td.DropDownButton [role=button]` or a field-help button. Dropdown lists are
  `[id=<aria-controls>] tr[role=option]`. Field ids are reused across forms,
  so always locate fields by label.
- **Lagre**: the button `Lagre` in toolbar `Handling` (`a#b$tblsysSave`). The
  success overlay is `[data-u4id=u4_messageoverlay_success]` (`role=alertdialog`)
  with the text `Rapporten har ordrenummer <n> og er tilgjengelig under Dine
  bestilte rapporter.` and an `OK` button. It appeared about 3.4 s after the
  double-click, and **Lagre** was disabled in between.
- **Dine bestilte rapporter (TRA003)**: `Fra`/`Til` (`dd.MM.yyyy`) plus `Last`.
  The rows are `tr[id^="b_g1s2_row"]`. Each cell's `onclick` names its field
  (`orderno`, `description`, `report_name`, `user_id`, `file_name`,
  `status`, …). `div[data-originaltext]` holds the untruncated value with
  HTML entities. The row checkbox is `input[id$="__delete"]`, toggled with
  its `label.DeleteRowCheckLabel`. The toolbar `Handling` has `Last ned`.
- **Vis logg** opens TRA014 on top of the order table, in the same tab. It has
  a link `<prefix>_<order>.log`, and clicking the link downloads the log. The
  log has `Orderno .....:` and `Client ......:` header lines, then a
  `PARAMETERS:` block of `Label (name) = value` lines.
- **Tøm bufferen**: the user menu button `… Handlingsmeny`, then link `Om Unit4 ERP`,
  then the dialog's button `Tøm bufferen`, then `Fullført` with `OK`, then close
  the About dialog with `Steng (Escape)`. The page does not reload, and the
  extension stays attached.
- **Activity reset**: the same user menu's log-out entry opens the page "Do
  you want to log out of your account?" with `Yes` and `Return to the
  application`. Only the second is ever clicked; Unit4 then reloads with no
  activities and may show the default company. The log-out entry's label is
  matched as `Logg ut` / `Logg av` / `Log out` / `Logout` / `Sign out` and has
  not been confirmed by live discovery yet.
