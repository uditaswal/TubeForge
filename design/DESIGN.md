# TubeForge dashboard design system

This file tells you (human or AI agent) exactly how to build and change the dashboard's look.
Follow it literally. When something here and your own taste disagree, this file wins.
When a page needs something this file doesn't cover, add it here first (workflow D), then use it.

Stack: **plain HTML + Tailwind CSS v3.4.17 + plain JavaScript.** No React, no build step required.

## Files

| File | What it is | When you edit it |
|---|---|---|
| `src/tubeforge/assets/ui/tokens.css` | Every color, font, radius and width, as CSS variables. **The only place a color value may appear.** Served at `/static/ui/`. | Changing the look (workflow B) |
| `src/tubeforge/assets/ui/tailwind.config.js` | Maps Tailwind class names (`bg-tf-surface`, `text-md`, `rounded-lg`) to the tokens | Only when you add or remove a token |
| `design/guide.html` | The living guide: one `<section>` per component, with the exact HTML recipe | Changing or adding a component (workflows C, D) |
| `src/tubeforge/assets/ui/tubeforge-ui.js` | Shared behaviour switched on by `data-` attributes (nav drawer, dialogs, copy) | Only when a component needs new behaviour |
| `design/guide.js` | Guide-only behaviour (shows recipes, highlights the sidebar) | Almost never |
| `src/tubeforge/api/design_system.py` | Server side: `design_head()` (load tags), `render_app_shell()` (sidebar, top bar), the `/static/ui` route | Changing the shell or nav |
| `design/DESIGN.md` | This file: rules, workflows, one `### Component:` section per component | Every time you change a component |
| `scripts/check_design.py` | Automatic checker (tokens, classes, components, links, contrast). Must pass before you finish | Only to allow a new arbitrary value |
| `scripts/screenshot_design_guide.py` | Screenshots the guide at 390, 768 and 1440 px | Never |

## The rules (never break these)

1. **Colors only from tokens.** Use `tf-*` classes (`bg-tf-surface`, `text-tf-muted`, `border-tf-line`). Never a hex value, never `rgb()`, never Tailwind palettes (`bg-slate-800`, `text-blue-400`, `bg-white`), never opacity modifiers (`bg-tf-ok/20`). Need a new shade? Add a token.
2. **Six text sizes:** `text-xs` 12, `text-sm` 13, `text-base` 14, `text-md` 16, `text-lg` 20, `text-xl` 26. Three weights: `font-normal`, `font-medium`, `font-semibold`. Nothing else.
3. **Three radii:** `rounded-sm` (badges, checkboxes), `rounded-md` (buttons, fields, notices, rows), `rounded-lg` (panels, dialogs). Plus `rounded-full` for dots and bars. Never plain `rounded`, never `rounded-xl`.
4. **No shadows, no gradients, no blur.** Separate things with `border-tf-line` or a `tf-raised` background.
5. **The accent (`tf-accent`) only marks what you can act on now:** primary buttons, focus, the current nav item, the current stage. Links, headings and decoration never use it.
6. **One primary button per panel or dialog.** Everything else is secondary, quiet or danger.
7. **Copy recipes exactly** from `design/guide.html`. Change only the words, IDs, `href`s and which variant you pick. Don't add or remove classes on a recipe in a page; change the recipe instead (workflow C).
8. **Sentence case everywhere.** No ALL-CAPS labels, no `uppercase` class, no "→" in buttons, no emoji.
9. **Every page uses the app shell and the page header,** and its main column is `max-w-content`, left aligned.
10. **Never show raw values:** no `failed_validation`, no stack traces in the first line, no `None`. Use the tables below.
11. **Look before you finish:** run the checker and the screenshot script, then open the PNGs (workflow E).

## Workflows

### A. Build or change a dashboard page

1. Open `design/guide.html` in your editor. Find the components you need in the sidebar list (`<nav aria-label="Guide sections">`).
2. Start from the app shell: copy everything from `<a href="#main"` down to `<main id="main" ...>` and the closing tags. Set the breadcrumb text and put `aria-current="page"` on the current nav link only.
3. First child of the main column: the **page-header** recipe.
4. Add components top to bottom in the order the operator works (what to do first goes first). Use `grid gap-10` between page sections.
5. For each component, copy the HTML inside its `<div data-example>`. Change words and IDs only. IDs must be unique on the page.
6. Pick labels and colors for states from **Job state labels** below.
7. Standalone pages get the design system from `wrap_studio_page(...)`; nothing to add by hand (see **Loading on a page**).
8. Run workflow E on the page (adapt the screenshot step to the page URL).

### B. Change a color, font, radius or width

1. Edit the value in `src/tubeforge/assets/ui/tokens.css`. Do not rename tokens.
2. Run `python scripts/check_design.py --contrast`. Every line must say `ok`. If a pair is `LOW`, adjust the value and run again.
3. Run workflow E.

Adding a **new** color token: add `--tf-name: #rrggbb;` in `tokens.css` with a comment saying what it's for, add `"tf-name": "var(--tf-name)",` to `colors` in `tailwind.config.js`, add a swatch in the Colors section of `guide.html`, and add a contrast pair to `CONTRAST_PAIRS` in `scripts/check_design.py` if text sits on it.

### C. Change an existing component

1. Find `<section id="NAME" data-component="NAME"` in `design/guide.html`. Edit the HTML inside its `<div data-example>`.
2. Update `### Component: NAME` in this file if the rules or variants changed.
3. Search the dashboard source for the old classes (`rg -n "old class string" src/tubeforge`) and update every copy, or list them in your report as still to migrate.
4. Run workflow E with the section name: `python scripts/screenshot_design_guide.py NAME`.

### D. Add a new component

1. Check it isn't already here under another name. Prefer combining existing components.
2. In `design/guide.html`, copy this block and paste it after the last section in the right group (Foundations, Layout, Controls, Status, Content):

```html
      <section id="NAME" data-component="NAME" class="grid grid-cols-1 gap-5">
        <div class="grid max-w-form gap-2">
          <h2 class="text-lg font-semibold">Readable name</h2>
          <p class="text-base text-tf-muted"><strong class="font-medium text-tf-text">Use for:</strong> one or two sentences.</p>
        </div>
        <div data-example>
<!-- the recipe HTML, starting at column 0 -->
        </div>
      </section>
```

3. Add a sidebar link in the matching group of `<nav aria-label="Guide sections">` (copy a neighbouring `<a>`, change `href="#NAME"` and the text).
4. Add a `### Component: NAME` section to this file using the same headings as the others (Use for, Don't, Variants, Words).
5. Build the recipe only from existing tokens and the allowed classes. If it needs behaviour, add a `data-` attribute handler to `src/tubeforge/assets/ui/tubeforge-ui.js` and document the attribute there and in the component section.
6. Run workflow E.

### E. Check your work (required before you finish)

1. `python scripts/check_design.py` must print `Design check passed.` Fix every listed problem; each line says how.
2. `.venv-benchmark/bin/python scripts/screenshot_design_guide.py` (or add a section id to shoot one component). It must not print any `PROBLEM:` line.
3. Open every PNG it printed (phone, tablet, desktop) and go through the **Visual checklist**. Write down what you checked in your report.
4. `PYTHONPATH=src .venv-benchmark/bin/python -m pytest -q tests/test_design_system.py`.

## Visual checklist (read the screenshots against this)

- Nothing is cut off, overlapping, or wider than the screen at 390 px.
- Every text is readable: no dark text on dark backgrounds, no light-on-light.
- Exactly one cyan (accent) button per panel or dialog; links are not cyan.
- Repeated items (rows, swatches, buttons in a row) line up on the same edges and have the same heights.
- Status is readable without color: each badge and stage has a word, not only a color.
- There is no empty box, no box inside a box, and no panel around a single sentence or field.
- Headings get smaller as you go down the hierarchy; nothing is bigger than the page title.
- The layout follows the order the operator works in: the action the page is for is easy to find.

## Loading on a page

**Implemented.** Every standalone page gets the design system by calling `wrap_studio_page(...)`
(`src/tubeforge/api/studio_shell.py`), which emits `design_head()` and the app shell from
`src/tubeforge/api/design_system.py`. Do not write these tags by hand. `design_head()` loads, in order:
the IBM Plex fonts, the Tailwind Play CDN (3.4.17), `/static/ui/tailwind.config.js`, `/static/ui/tokens.css`,
and `/static/ui/tubeforge-ui.js` (deferred). `/static/ui/` is public (no sign-in) because it holds no data.

Pages currently using the shell: Batch plans, Day review, Settings, Clips, Reference videos, Long-form scripts.
The single-page dashboard at `/` still uses `studio_shell.py`'s own chrome (see Migration status).

Tailwind's preflight is **off** (`corePlugins.preflight: false`). See **Known collisions** for why.

## Migration status

| Area | Status |
|---|---|
| Tokens, Tailwind config, shared JS served at `/static/ui/` | Done |
| App shell (sidebar, drawer, top bar) on the six standalone pages | Done (chrome only) |
| Page content on those six pages (forms, lists, tables, panels) | Not started: still styled by `STUDIO_CSS` |
| Single-page dashboard at `/` (Studio, Generations, Scheduling, Accounts, Media, Publishing) | Not started |
| Compiled Tailwind CSS (standalone CLI) and self-hosted fonts | Not started |

Next step: migrate Day review's content to the recipes (panel, job list, review-split, notice), then Settings.
Delete each page's old CSS in the same change.

## Known collisions

These are the traps found while wiring the system into the live pages. Read this before writing markup.

1. **Legacy `.grid`.** Settings (and other pages' own CSS) defines a global `.grid` with a two-column template and a
   19 px gap. Tailwind's `grid` uses the same class name, so `grid` alone can place children side by side.
   Fix in markup: add `!grid-cols-1` (and `!gap-N` when the gap matters) on any `grid` container on a dashboard page.
   The shell already does this. Remove the legacy rule when its page is migrated.
2. **Legacy element rules.** `STUDIO_CSS` underlines every `a` and gives every `button` a cyan fill and radius.
   The recipes set their own colors, so they win. For links, always write `underline` (text links) or
   `no-underline` (buttons and navigation). The checker enforces this in `design/guide.html`.
3. **Preflight is off.** Tailwind's base reset would override the legacy button and input styles, because the
   Play CDN style is injected after `STUDIO_CSS`. Consequence: headings and paragraphs keep browser margins.
   The guide's body has `tf-guide`, which zeroes them. A new page that needs predictable margins puts
   `m-0` on each element that needs it (Tailwind's zero-margin class).
4. **Old shell classes.** `.studio-sidebar`, `.studio-topbar`, `.studio-main`, `.studio-backdrop` are no longer
   produced on standalone pages. Navigation is `data-nav`, `data-nav-open` and `data-nav-close`, handled by
   `tubeforge-ui.js`. The SPA at `/` still uses the old classes until it is migrated.

## Do you need a framework?

No, not for anything the dashboard does today. Server-rendered HTML, these recipes and small `data-`-attribute scripts cover forms, lists that refresh every 30 seconds, dialogs, video review and settings.

Consider a small library (still no build step) only for these cases, and ask the operator first:

- **htmx** (one script tag): if many pages need "click → replace this part of the page with server HTML" and the hand-written `fetch` code keeps growing.
- **Alpine.js** (one script tag): if one page needs a lot of local interactive state, such as a drag-to-reorder schedule calendar or a multi-step wizard.
- **A real framework (React, Svelte, Vue) with a build step:** only for a clip or timeline editor with frame-accurate scrubbing, waveforms and many synchronized panels. Nothing planned needs this yet.

## Job state labels

Never show the raw state. Use this table for the badge and the stage track. "Needs you" states are warn (amber) because the queue waits for the operator.

| Raw state | Badge label | Badge tone | Stage | Stage state |
|---|---|---|---|---|
| `topic_created` | Queued | neutral | Script | waiting |
| `source_inspecting`, `source_acquiring`, `source_analyzing` | Reading source | info | Script | working |
| `clip_rendering` | Cutting clips | info | Render | working |
| `content_generating` | Writing script | info | Script | working |
| `content_ready` | Script written | info | Script | done |
| `script_approval_required` | Script needs review | warn | Script | needs you |
| `asset_acquisition`, `assets_ready` | Gathering visuals | info | Voice | working |
| `voice_generation`, `voice_ready`, `caption_generation` | Recording voice | info | Voice | working |
| `preview_rendering` | Rendering preview | info | Render | working |
| `preview_ready`, `preview_approval_required` | Preview needs review | warn | Review | needs you |
| `preview_approved`, `final_rendering` | Rendering final | info | Review | working |
| `final_ready` | Final ready | ok | Publish | waiting |
| `publication_preparing` | Preparing post | info | Publish | working |
| `publication_approval_required`, `publish_approval_required` | Post needs approval | warn | Publish | needs you |
| `publication_ready`, `private_upload_ready` | Ready to upload | ok | Publish | waiting |
| `publishing`, `private_uploading` | Uploading | info | Publish | working |
| `publication_verification_pending`, `publication_reconciling` | Checking upload | info | Publish | working |
| `published` | Published | ok | Publish | done |
| `failed_retryable` | Retry scheduled | warn | (stage it failed in) | failed |
| `failed_validation`, `failed_exhausted` | Failed | bad | (stage it failed in) | failed |
| `auth_required` | Sign-in needed | warn | (current stage) | needs you |
| `cancelled` | Cancelled | neutral | (last stage) | waiting |

Stages before the current one are **done**; stages after it are **waiting**.

## Words

- Name things the way the operator does: "video", "script", "review", "publish". Not "artifact", "job payload", "gate".
- Buttons are verbs that say exactly what happens: "Approve video", "Delete job", "Retry". The result message uses the same verb: "Approved", "Deleted".
- A button that opens a dialog ends with "…" ("Delete job…").
- Errors: first what happened, then what to do. No apologies, no "Something went wrong". Raw error text goes under "Technical details".
- Empty states: what will appear here, then the action that creates the first one.
- Dates: `18 Nov, 01:38` (day month, 24-hour). Durations: `0:58` for video length, `2m 05s` for elapsed time.

## Common mistakes (check your diff for these)

- Inventing classes that don't exist: `bg-tf-primary`, `text-tf-secondary`, `rounded-xl`, `text-2xl`. Only the names in `tailwind.config.js` work.
- Using `text-tf-accent` for links or headings. Links use the **link** recipe.
- Putting a panel inside a panel, or a panel around one field.
- A second primary button in the same panel.
- `<button>` without `type="button"`; an `<input>` without a `<label for>`.
- Copying a recipe and then "improving" it with extra classes. Change the recipe instead (workflow C).
- Showing "Loading…" after data has arrived, or a loading screen on background refresh.
- Using `alert()` or `confirm()`. Use the **dialog** recipe.

## Components

### Component: colors
Use for: reference only. The palette and what each token is for. Surfaces go darkest (page) to lightest (dialog): `tf-bg` → `tf-surface` → `tf-raised`; `tf-input` sits inside fields.
Don't: use status colors (`tf-ok`, `tf-warn`, `tf-bad`, `tf-info`) for decoration or brand.
Variants: each status color has a `-soft` pair for backgrounds; text on a soft background uses the strong color or `tf-text`.

### Component: type
Use for: reference only. IBM Plex Sans for everything; `tf-mono` (IBM Plex Mono) only for machine values: job IDs, file paths, durations, commands, numbers in tables.
Don't: use mono for labels or headings; use more than one heading level per visual level.
Variants: page title `text-xl font-semibold`; section heading `text-lg font-semibold`; item title `text-md font-semibold`; body `text-base`; labels/help `text-sm`; badges/stage labels `text-xs`.

### Component: shape
Use for: reference only. Radii, spacing and widths.
Don't: use spacing values off the 4 px scale (`p-[13px]`), or center a page's main column.
Variants: `max-w-content` for the main column; `max-w-form` for forms and paragraphs; `gap-10` between page sections; `gap-4`/`gap-5` inside panels; `px-5 py-4` inside list rows.

### Component: app-shell
Use for: every signed-in page. Sidebar (drawer below 1024 px), sticky top bar, main column.
Don't: build a different top bar for some pages; put actions in the top bar other than Sign out.
Variants: none. Nav groups, in order (`NAV_GROUPS` in `design_system.py`): Make (Studio, Batch plans, Reference videos, Long-form scripts, Clips), Review (Generations), Publish (Publishing, Scheduling, Accounts), System (Media tools, Settings). Day review is reached from Batch plans, not from the nav. The connection indicator shows "Connected" with a `tf-ok` dot, or "Reconnecting…" with a `tf-warn` dot.
Behaviour: `data-nav-open` / `data-nav-close` (in `tubeforge-ui.js`); Escape closes the drawer.

### Component: page-header
Use for: once per page, first in the main column.
Don't: add a second description paragraph, or more than one primary action.
Variants: with or without actions on the right.
Words: title = the nav label; description = one sentence saying what the page is for.

### Component: panel
Use for: a self-contained tool: a form, a list, a review area.
Don't: nest panels; box a single field, sentence or button; give every section of a page its own panel.
Variants: none. A panel's heading is `text-lg`, and it has an `id` referenced by `aria-labelledby`.

### Component: button
Use for: doing something. Primary (one per panel/dialog), secondary, quiet (low-stakes, dense rows), danger (destructive, usually inside a confirm dialog).
Don't: use a button to navigate (use a link); disable a button without visible text explaining why.
Variants: default `h-9 px-4 text-base`; small `h-8 px-3 text-sm` in list rows and the top bar. Disabled buttons get `disabled` plus `aria-describedby` pointing at the reason.
Words: verb + object ("Approve video"). Dialog openers end with "…".

### Component: link
Use for: going to another page or a source.
Don't: color links with the accent or green; use a link for an action.
Variants: none.

### Component: field
Use for: text input, textarea, select, checkbox. One column inside `max-w-form`.
Don't: use a placeholder instead of a label; put two fields side by side except very short pairs (date + time).
Variants: error state = `border-tf-bad`, `aria-invalid="true"`, and an error line `text-sm text-tf-bad` linked by `aria-describedby`. Help text = `text-sm text-tf-muted` linked by `aria-describedby`.
Words: label in sentence case, no colon. Errors say how to fix it ("Use lowercase letters, numbers and dashes").

### Component: dialog
Use for: confirming destructive or irreversible actions; focused tasks (activity log, video player).
Don't: use `alert()`/`confirm()`; open a dialog on page load.
Variants: confirm (title question naming the object, consequence sentence, keep + do buttons); task (title, content, a single "Close" secondary button).
Behaviour: `data-dialog-open="ID"` opens `<dialog id="ID">`; buttons inside `<form method="dialog">` close it and set `dialog.returnValue` to their `value`. The page's JS reads `returnValue` on the `close` event to act.

### Component: stage-track
Use for: where a video is in Script → Voice → Render → Review → Publish. On every job row and at the top of a job's detail view. This is the dashboard's signature element.
Don't: change the five stage names; show it for items that aren't videos; rely on color alone (the `sr-only` text and label colors carry the state).
Variants (per step): done = bar `bg-tf-ok`, label `font-medium text-tf-muted`; working = bar `bg-tf-accent`, label `font-semibold text-tf-accent`, `aria-current="step"`; needs you = bar `bg-tf-warn`, label `font-semibold text-tf-warn`, `aria-current="step"`; failed = bar `bg-tf-bad`, label `font-semibold text-tf-bad`, `aria-current="step"`; waiting = bar `bg-tf-line`, label `font-medium text-tf-faint`. Optional third line `tf-mono text-xs text-tf-faint`: elapsed time (`2m 05s`) or a short reason (`QA: loudness`, `needs you`).
Words: the `<ol>`'s `aria-label` is "Progress: " + the badge label in lower case. Map states with **Job state labels**.

### Component: badge
Use for: an item's overall state, one per item, top right of its row.
Don't: show raw state names; use more than one badge per item; use badges as tags or categories.
Variants: ok, warn, bad, info, neutral (see recipe). Pick label and tone from **Job state labels**.

### Component: notice
Use for: a failure, warning or important fact about one item or a page.
Don't: put raw error text in the first line; stack more than two notices; use it for success messages (use the result text next to the button).
Variants: bad (failed), warn (retrying, needs attention), info (fact the operator should know). Optional "Technical details" `<details>` with the raw error in `tf-mono`. Add `role="alert"` only when it appears after page load.

### Component: empty-loading
Use for: a list or area with no data yet (empty), or before the first data arrives (loading).
Don't: show the loading line after data has rendered; show a loading state on background refresh; leave an empty area blank.
Variants: loading line (`role="status"`); empty box (dashed border) with a heading, one sentence and the action that creates the first item.

### Component: job-list
Use for: lists of videos or jobs: Studio work in progress, Generations, Clips, Day review queue.
Don't: put each job in its own panel; show more than three buttons per row (the rest go in "More"); repeat the same facts in the title and the details.
Variants: row with a notice (failed or retrying) placed between title and stage track; every video row has a stage track (clip jobs from a source video use Script = reading source, Render = cutting clips).
Behaviour: "More" uses `<details>`; "Copy job ID" uses `data-copy`.

### Component: meta-list
Use for: facts about one item. Inline (`flex flex-wrap gap-x-6`) in rows; two columns (`grid sm:grid-cols-2`) in a detail view.
Don't: join values with dots in a sentence; show facts the operator doesn't act on.
Variants: inline, stacked (see recipe; the inline version is inside the job-list recipe).

### Component: data-table
Use for: rows compared across the same columns: settings, scenes, usage.
Don't: use a table for layout; leave it without the `overflow-x-auto` wrapper.
Variants: numbers right-aligned in `tf-mono`. The `min-w-[560px]` on the table is an allowed arbitrary value so columns stay readable on phones (the wrapper scrolls).

### Component: review-split
Use for: Day review and any approval of a rendered video.
Don't: approve anything other than the exact file shown; hide the sources; put the decision buttons above the video.
Variants: the scene table may have a fourth column for warnings. `aspect-[9/16]` keeps the player in Shorts proportion; use `aspect-video` for landscape.
Words: "Approve this video", "Regenerate…", "Reject…". After approval, the badge changes to "Approved" (ok) and the result text says "Approved. Staged for publishing."
