---
name: ppt-master
description: >
  AI-driven multi-format SVG content generation system. Converts source documents
  (PDF/DOCX/URL/Markdown) into high-quality SVG pages and exports to PPTX through
  multi-role collaboration. Use when user asks to "create PPT", "make presentation",
  "生成PPT", "做PPT", "制作演示文稿", or mentions "ppt-master".
---

# PPT Master Skill

> AI-driven multi-format SVG content generation system. Converts source documents into high-quality SVG pages through multi-role collaboration and exports to PPTX.

**Core Pipeline**: `Source Document → Create Project → [Template] → Strategist → [Image_Generator] → Executor Live Preview → Quality Check → Post-processing → Export`

> [!CAUTION]
> ## 🚨 Global Execution Discipline (MANDATORY)
>
> **This workflow is a strict serial pipeline. The following rules have the highest priority — violating any one of them constitutes execution failure:**
>
> 1. **SERIAL EXECUTION** — Steps MUST be executed in order; the output of each step is the input for the next. Non-BLOCKING adjacent steps may proceed continuously once prerequisites are met, without waiting for the user to say "continue"
> 2. **BLOCKING = HARD STOP** — Steps marked ⛔ BLOCKING require a full stop; the AI MUST wait for an explicit user response before proceeding and MUST NOT make any decisions on behalf of the user. **Exception**: the Eight Confirmations in Step 4 auto-bypass for simple ≤2-page tasks with no ambiguity (see Step 4 for details)
> 3. **NO CROSS-PHASE BUNDLING** — Cross-phase bundling is FORBIDDEN. (Note: the Eight Confirmations in Step 4 are ⛔ BLOCKING — the AI MUST present recommendations and wait for explicit user confirmation before proceeding, unless the ≤2-page auto-bypass applies. Once the user confirms [or auto-bypass triggers], all subsequent non-BLOCKING steps — design spec output, SVG generation, speaker notes, and post-processing — may proceed automatically without further user confirmation)
> 4. **GATE BEFORE ENTRY** — Each Step has prerequisites (🚧 GATE) listed at the top; these MUST be verified before starting that Step
> 5. **NO SPECULATIVE EXECUTION** — "Pre-preparing" content for subsequent Steps is FORBIDDEN (e.g., writing SVG code during the Strategist phase)
> 6. **NO SUB-AGENT SVG GENERATION** — Executor Step 6 SVG generation is context-dependent and MUST be completed by the current main agent end-to-end. Delegating page SVG generation to sub-agents is FORBIDDEN
> 7. **SEQUENTIAL PAGE GENERATION ONLY** — In Executor Step 6, after the global design context is confirmed, SVG pages MUST be generated sequentially page by page in one continuous pass. Grouped page batches (for example, 5 pages at a time) are FORBIDDEN
> 8. **SPEC_LOCK RE-READ PER PAGE** — Before generating each SVG page, Executor MUST read `spec_lock.md` from MinIO: `python3 ${SKILL_DIR}/scripts/minio_project.py read-file --prefix "$PROJECT_PREFIX" spec_lock.md`. All colors / fonts / icons / images MUST come from this file — no values from memory or invented on the fly. Executor MUST also look up the current page's `page_rhythm` (`anchor` / `dense` / `breathing`), `page_layouts` (which template SVG to inherit, if any), and `page_charts` (which chart template to adapt, if any). Empty / absent entries are intentional Strategist signals — see executor-base.md §2.1. This rule exists to resist context-compression drift on long decks and to break the uniform "every page is a card grid" default
> 9. **SVG MUST BE HAND-WRITTEN, NOT SCRIPT-GENERATED** — Every SVG page is written by the main agent directly, one page at a time (see rules 6 and 7). Writing or running a Python / Node / shell script that produces the SVG files in batch — looping over pages, templating from data, or emitting them via a generator — is FORBIDDEN, including under "save tokens", "quick draft", or "user is in a hurry" pretexts. The script-generation path was tried on a feature branch and abandoned: cross-page visual consistency depends on per-page authoring with full upstream context, which a generator script cannot reproduce
> 10. **ALL PROJECT FILES GO IN `$WORK_DIR` — NEVER `/tmp/`** — Every file written during this workflow (SVGs, spec_lock.md, design_spec.md, notes, images, source documents) MUST be written inside `$WORK_DIR` (the unique working directory created at Step 2 via `minio_project.py create-workdir`). Writing to `/tmp/`, `/var/tmp/`, or any path OUTSIDE `$WORK_DIR` is STRICTLY FORBIDDEN and will be blocked by the tool layer. NEVER run `mkdir /tmp/...`. NEVER redirect output to `/tmp/...`. Only the final deliverable (PPTX) is uploaded to MinIO at the end of Step 7; then `$WORK_DIR` is deleted immediately. This design ensures: (a) no conflicts between concurrent users — each task has a UUID-named directory; (b) no persistent state after task completion; (c) MinIO receives only the finished result.

> [!IMPORTANT]
> ## 🌐 Language & Communication Rule
>
> - **Response language**: match the user's input and source materials. Explicit user override (e.g., "请用英文回答") takes precedence.
> - **Template format**: `design_spec.md` MUST follow its original English template structure (section headings, field names) regardless of conversation language. Content values may be in the user's language.

> [!IMPORTANT]
> ## 🔌 Compatibility With Generic Coding Skills
>
> - `ppt-master` is a repository-specific workflow, not a general application scaffold
> - Do NOT create `.worktrees/`, `tests/`, branch workflows, or generic engineering structure by default
> - On conflict with a generic coding skill, follow this skill unless the user explicitly says otherwise

## Main Pipeline Scripts

| Script | Purpose |
|--------|---------|
| `${SKILL_DIR}/scripts/source_to_md/pdf_to_md.py` | PDF to Markdown |
| `${SKILL_DIR}/scripts/source_to_md/doc_to_md.py` | Documents to Markdown — native Python for DOCX/HTML/EPUB/IPYNB, pandoc fallback for legacy formats (.doc/.odt/.rtf/.tex/.rst/.org/.typ) |
| `${SKILL_DIR}/scripts/source_to_md/excel_to_md.py` | Excel workbooks to Markdown — supports .xlsx/.xlsm; legacy .xls should be resaved as .xlsx |
| `${SKILL_DIR}/scripts/source_to_md/ppt_to_md.py` | PowerPoint to Markdown |
| `${SKILL_DIR}/scripts/source_to_md/web_to_md.py` | Web page to Markdown (supports WeChat via `curl_cffi`) |
| `${SKILL_DIR}/scripts/minio_project.py` | **MinIO project lifecycle** — init / run / write-file / read-file / list / import-source |
| `${SKILL_DIR}/scripts/analyze_images.py` | Image analysis |
| `${SKILL_DIR}/scripts/latex_render.py` | LaTeX formula rendering (manifest-driven PNG assets) |
| `${SKILL_DIR}/scripts/image_gen.py` | AI image generation (multi-provider) |
| `${SKILL_DIR}/scripts/svg_quality_checker.py` | SVG quality check |
| `${SKILL_DIR}/scripts/total_md_split.py` | Speaker notes splitting |
| `${SKILL_DIR}/scripts/finalize_svg.py` | SVG post-processing (unified entry) |
| `${SKILL_DIR}/scripts/svg_to_pptx.py` | Export to PPTX |
| `${SKILL_DIR}/scripts/update_spec.py` | Propagate a `spec_lock.md` color / font_family change across all generated SVGs |

For complete tool documentation, see `${SKILL_DIR}/scripts/README.md`.

---

## Storage Model (MANDATORY — applies to every step)

> [!CAUTION]
> **Working files live in `$WORK_DIR` (unique per task, deleted when done). Final result uploads to MinIO.**
> - All intermediate files (SVGs, spec_lock.md, images, notes…) → write to `$WORK_DIR` using the `file_write` tool
> - All processing scripts → run directly with `$WORK_DIR` as argument
> - Final PPTX only → upload to MinIO via `minio_project.py upload-result` (auto-cleans work dir)
> - On completion → delete `$WORK_DIR` via `minio_project.py cleanup` (explicit safety net)
> - Orphan recovery → `minio_project.py cleanup-stale --max-age-hours 24` for crashed sessions

**Create the working directory at Step 2** and keep `$WORK_DIR` for the entire session:
```bash
export WORK_DIR=$(python3 ${SKILL_DIR}/scripts/minio_project.py create-workdir | python3 -c "import sys,json; print(json.load(sys.stdin)['work_dir'])")
echo "Working directory: $WORK_DIR"
```

**Write a file into the working directory** — use the `file_write` tool with the **actual absolute path** (substitute the real value of `$WORK_DIR`, e.g. `/app/tmp-doc/42_a3f7c891/`):
```
file_write(path="/app/tmp-doc/42_a3f7c891/spec_lock.md", content="...")
file_write(path="/app/tmp-doc/42_a3f7c891/svg_output/slide_01.svg", content="<svg>...</svg>")
```
> ⚠️ `$WORK_DIR` is a shell variable — it does NOT expand inside the `file_write` tool. Always substitute the real path string returned by `create-workdir`.
>
> **Idempotency**: If `create-workdir` is called again within 5 minutes for the same `employee_id`, it returns the same existing directory (shown with `"reused": true`). This prevents duplicate directories when the model accidentally invokes the command more than once.

**Read a file from the working directory** — use the `file_read` tool or `cat`:
```bash
cat "$WORK_DIR/spec_lock.md"
```

**Run any processing script** — pass `$WORK_DIR` as the project path directly:
```bash
python3 ${SKILL_DIR}/scripts/finalize_svg.py "$WORK_DIR"
python3 ${SKILL_DIR}/scripts/svg_quality_checker.py "$WORK_DIR"
```

**Upload final result to MinIO** (Step 7, after PPTX is generated):
```bash
PPTX_FILE=$(find "$WORK_DIR/exports" -name "*.pptx" -not -name "*_svg.pptx" | head -1)
python3 ${SKILL_DIR}/scripts/minio_project.py upload-result "$PPTX_FILE"
```

**Delete working directory** (immediately after upload):
```bash
python3 ${SKILL_DIR}/scripts/minio_project.py cleanup --work-dir "$WORK_DIR"
```

> **Orphaned directories**: if a session crashes mid-workflow, stale directories may remain under `tmp-doc/`. Clean them up periodically:
> ```bash
> # List stale dirs (older than 24 h) without deleting
> python3 ${SKILL_DIR}/scripts/minio_project.py cleanup-stale --dry-run
> # Actually delete them
> python3 ${SKILL_DIR}/scripts/minio_project.py cleanup-stale --max-age-hours 24
> ```

---

## Template Index

| Index | Path | Purpose |
|-------|------|---------|
| Layout templates | `${SKILL_DIR}/templates/layouts/layouts_index.json` | Query available page layout templates |
| Brand presets | `${SKILL_DIR}/templates/brands/brands_index.json` | Query available brand identity presets (color / typography / logo / voice) |
| Visualization templates | `${SKILL_DIR}/templates/charts/charts_index.json` | Query available visualization SVG templates (charts, infographics, diagrams, frameworks) |
| Icon library | `${SKILL_DIR}/templates/icons/` | See `${SKILL_DIR}/templates/icons/README.md`; search icons on demand with `ls templates/icons/<library>/ \| grep <keyword>` |

## Standalone Workflows

| Workflow | Path | Purpose |
|----------|------|---------|
| `topic-research` | `workflows/topic-research.md` | Pre-pipeline — gather web sources when the user supplies only a topic with no source files |
| `create-template` | `workflows/create-template.md` | Standalone layout template creation workflow |
| `create-brand` | `workflows/create-brand.md` | Standalone brand-only template creation (identity preset; no SVG page roster) |
| `resume-execute` | `workflows/resume-execute.md` | Phase B entry — resume execution in a fresh chat after Phase A (Step 1–5) completed in another session (split mode) |
| `verify-charts` | `workflows/verify-charts.md` | Chart coordinate calibration — run after SVG generation if the deck contains data charts |
| `customize-animations` | `workflows/customize-animations.md` | Object-level PPTX animation customization — run only when the user explicitly asks to tune animation order/effects/timing |
| `live-preview` | `workflows/live-preview.md` | Browser-based live preview — auto-started during generation and re-enterable any time the user mentions "live preview", "preview", "看效果", or wants to click/select a slide element |
| `visual-review` | `workflows/visual-review.md` | Per-page rubric-based visual self-check — run only when the user explicitly asks for a visual re-pass on the generated SVGs (between Executor and post-processing). Opt-in only; never invoked by the main pipeline. |

---

## Workflow

### Step 1: Source Content Processing

🚧 **GATE**: User has provided source material (PDF / DOCX / EPUB / URL / Markdown file / text description / conversation content — any form is acceptable).

> **No source content?** When the user supplies only a topic name or requirements without any file or substantive description, run the [`topic-research`](workflows/topic-research.md) workflow first, then return here with its products as input.

When the user provides non-Markdown content, convert immediately:

| User Provides | Command |
|---------------|---------|
| PDF file | `python3 ${SKILL_DIR}/scripts/source_to_md/pdf_to_md.py <file>` |
| DOCX / Word / Office document | `python3 ${SKILL_DIR}/scripts/source_to_md/doc_to_md.py <file>` |
| XLSX / XLSM / Excel workbook | `python3 ${SKILL_DIR}/scripts/source_to_md/excel_to_md.py <file>` |
| CSV / TSV | Read directly as plain-text table source |
| PPTX / PowerPoint deck | `python3 ${SKILL_DIR}/scripts/source_to_md/ppt_to_md.py <file>` |
| EPUB / HTML / LaTeX / RST / other | `python3 ${SKILL_DIR}/scripts/source_to_md/doc_to_md.py <file>` |
| Web link | `python3 ${SKILL_DIR}/scripts/source_to_md/web_to_md.py <URL>` |
| WeChat / high-security site | `python3 ${SKILL_DIR}/scripts/source_to_md/web_to_md.py <URL>` (requires `curl_cffi`, included in `requirements.txt`) |
| Markdown | Read directly |

> **Office vector assets (EMF/WMF) from DOCX/PPTX sources**:
> `doc_to_md.py` / `ppt_to_md.py` extract embedded Office vector images (.emf/.wmf)
> alongside bitmap images. After `import-sources`, these land in `images/`
> together with `image_manifest.json` and are first-class assets in §VIII Image Resource List.
>
> **Do NOT convert EMF/WMF to PNG.** The PPT Master pipeline preserves them as external
> references (`finalize_svg.py` skips them) and `svg_to_pptx.py` embeds them as
> PPTX-native media via `image/x-emf` / `image/x-wmf` MIME — PowerPoint renders them at full vector fidelity.
> Converting via LibreOffice/Inkscape introduces CJK font substitution drift and
> rasterization loss; the original EMF/WMF is always higher fidelity than the converted PNG.
>
> Browser-based live preview cannot render EMF (will show blank) — this is expected;
> the PPTX output is the source of truth.

**✅ Checkpoint — Confirm source content is ready, proceed to Step 2.**

---

### Step 2: Project Initialization

🚧 **GATE**: Step 1 complete; source content is ready (Markdown file, user-provided text, or requirements described in conversation are all valid).

**Create the unique working directory** and keep `$WORK_DIR` for the entire session:
```bash
export WORK_DIR=$(python3 ${SKILL_DIR}/scripts/minio_project.py create-workdir | python3 -c "import sys,json; print(json.load(sys.stdin)['work_dir'])")
echo "Working directory: $WORK_DIR"
```

Format is embedded in the project path; the canvas format is passed to scripts directly (e.g. `--format ppt169`). Format options: `ppt169` (default), `ppt43`, `xhs`, `story`, etc. See `references/canvas-formats.md`.

Import source content (choose based on the situation):

| Situation | Action |
|-----------|--------|
| Has source files (PDF/MD/etc.) that were converted in Step 1 | Use `file_write` to write the converted content into `$WORK_DIR/sources/`; or move the local file with `mv <file> "$WORK_DIR/sources/"` |
| User provided text directly in conversation | No import needed — content is in conversation context |

**✅ Checkpoint — Confirm `$WORK_DIR` is set and accessible. Proceed to Step 3.**

---

### Step 3: Template Option

🚧 **GATE**: Step 2 complete; project directory structure is ready.

**Default — free design.** Proceed directly to Step 4. Do NOT query any `*_index.json` unless triggered. Do NOT ask the user. Do NOT proactively suggest, hint at, or fuzzy-match any template based on content, slug-like words, or vague style descriptions.

**Template flow triggers ONLY on explicit directory paths** supplied by the user in their initial message. The trigger rule is mechanical, not interpretive:

| User input contains | Step 3 action |
|---|---|
| One or more explicit template directory paths (each resolves to a directory containing `design_spec.md` with `kind: brand` / `kind: layout` / `kind: deck` in its YAML frontmatter) | Read each spec's `kind`, dispatch per the kind matrix below, fuse if multiple |
| Anything else — bare template names ("用 academic_defense"), style descriptions ("麦肯锡风格"), brand mentions ("招商银行风格"), vague intent ("想用个模板"), or silence | Skip Step 3, free design |

There is no slug matching, no name lookup, no fuzzy resolution. A name without a path does not trigger — the user must give a path the AI can `cd` into.

> Style descriptions ("麦肯锡风格" / "Keynote 风" / "极简风" / etc.) never trigger Step 3. They flow into Strategist's Eight Confirmations as a style brief (color / typography / tone in confirmations e–g).

> Bare names ("academic_defense", "招商银行", "anthropic") do NOT trigger Step 3 even if a matching directory exists in the library. The user must give a path. AI must not "helpfully" resolve a name to a path.

> "What templates exist?" is out-of-band Q&A — answer by listing entries from `brands_index.json` / `layouts_index.json` / `decks_index.json` together with their paths. Listing alone does not advance the pipeline; the user must send a path back to trigger Step 3.

> To create a new layout or deck, read [`workflows/create-template.md`](workflows/create-template.md). To create a new brand, read [`workflows/create-brand.md`](workflows/create-brand.md).

#### Three template kinds

The architecture has three independent reference bundles. Full schema in [`docs/zh/templates-architecture.md`](../../docs/zh/templates-architecture.md). Summary:

| Kind | Physical dir | Contains | Frontmatter |
|---|---|---|---|
| **brand** | `templates/brands/<id>/` | identity-only segment: color / typography / logo / voice / icon style | `kind: brand` |
| **layout** | `templates/layouts/<id>/` | structure-only segment: canvas / page structure / page types / SVG roster | `kind: layout` |
| **deck** | `templates/decks/<id>/` | full replica: identity + structure + middle (template overview) segments | `kind: deck` |

**Segment ownership** (governs fusion override priority):

| Segment | Sections | Owner kind on fusion |
|---|---|---|
| Identity | Color Scheme / Typography / Logo / Voice & Tone / Icon Style | brand |
| Structure | Canvas / Page Structure / Page Types / SVG Roster | layout |
| Middle | Template Overview (use cases / design intent) | deck (no other kind writes this) |

#### Single-path dispatch

| User path's `kind` | Step 3 action |
|---|---|
| `kind: brand` | Copy `design_spec.md` + logo files + asset subdirs (`images/` / `illustrations/` / `icons/`) into `<project>/templates/`. Strategist locks identity segment as truth; structure stays free. |
| `kind: layout` | Copy `design_spec.md` + SVG roster + asset files into `<project>/templates/`. Strategist locks structure; identity decided in Eight Confirmations e–g. |
| `kind: deck` | Copy everything (`design_spec.md` + SVGs + logos + assets) into `<project>/templates/`. Strategist locks all segments; Eight Confirmations narrows to deck-content fields (audience / page count / outline / tone tweaks). |

```bash
TEMPLATE_DIR=<user-supplied path>
cp -r ${TEMPLATE_DIR}/* <project_path>/templates/
```

The single-line copy suffices for all three kinds — the spec's `kind` field tells Strategist how to read it; downstream code doesn't distinguish.

#### Multi-path fusion

When the user gives two or more paths of **different kinds**, Step 3 fuses them into a single `<project>/templates/design_spec.md`. **Default granularity is segment-level integer replacement** — entire identity / structure / middle segments are taken from the highest-priority source for that segment, no implicit field-level mixing.

Override priority by segment:

| Combination | Identity from | Structure from | Middle from |
|---|---|---|---|
| brand only | brand | (free design) | (none) |
| layout only | (free design) | layout | (none) |
| deck only | deck | deck | deck |
| brand + layout | brand | layout | (none) |
| brand + deck | brand (overrides deck) | deck | deck |
| layout + deck | deck | layout (overrides deck) | deck |
| brand + layout + deck | brand | layout | deck |

Field-level micro-adjustment (e.g. "use anthropic brand but primary changed to #FF0000") is **not** part of Step 3 fusion — it flows into Strategist Eight Confirmations e–g as a normal user request.

#### Same-kind multiple paths — conflict resolution

When the user gives two paths of the **same kind** (e.g. `brands/anthropic` + `brands/google`), Step 3 surfaces a conflict prompt before fusing — like resolving a git merge conflict:

```
AI: 你给了两个 brand，检测到段级冲突：
    - Color Scheme（Anthropic 橙红 vs Google 多色）
    - Typography（Styrene/AnthropicSans vs GoogleSans/Roboto）
    - Logo（Anthropic 标 vs Google 标）
    - Voice & Tone（restrained vs friendly）
    - Icon Style（stroke vs filled）

    要 (a) 全部按 Anthropic / (b) 全部按 Google / (c) 逐段挑？
```

Rules:
- Default: no implicit ordering — every cross-source segment difference is reported as a conflict
- Only when the user picks `(c)` does AI walk through each segment one by one
- Field-level conflicts are out of scope — segment-level only
- Three or more same-kind paths are not supported — ask the user to converge to at most two

#### Fused spec provenance

When fusion happens (any multi-path case), the resulting `<project>/templates/design_spec.md` carries a provenance block immediately under its H1:

```markdown
> **Fused from:**
> - deck: `templates/decks/招商银行/` （base）
> - brand: `templates/brands/anthropic/` （identity override）
> - layout: `templates/layouts/academic_defense/` （structure override）
> - conflicts resolved: Color Scheme from anthropic（user picked a）
```

Single-path Step 3 does **not** add provenance (the source is self-evident from the copied files).

**✅ Checkpoint — Default path proceeds to Step 4 without user interaction. If the user supplied one or more explicit template paths, those have been dispatched (or fused) into `<project_path>/templates/` before advancing.**

---

### Step 4: Strategist Phase (MANDATORY — cannot be skipped)

🚧 **GATE**: Step 3 complete; default free-design path taken, or (if triggered) template files copied into the project.

First, read the role definition:
```
Read references/strategist.md
```

> ⚠️ **Mandatory gate**: before writing `design_spec.md`, Strategist MUST `read_file templates/design_spec_reference.md` and follow its full I–XI section structure. See `strategist.md` Section 1.

**Eight Confirmations** (full template: `templates/design_spec_reference.md`):

⛔ **BLOCKING**: present the Eight Confirmations as a single bundled recommendation set and **wait for explicit user confirmation or modification** before outputting Design Specification & Content Outline. This is the single core confirmation point — once confirmed, all subsequent steps proceed automatically.

> **Auto-bypass for simple tasks**: When the request is trivially simple — clearly fits on ≤2 pages with no ambiguity — auto-decide all eight items with sensible defaults and proceed directly to `design_spec.md` + `spec_lock.md` without pausing. For multi-page decks, ambiguous briefs, or anything that benefits from user input, stop and confirm.

1. Canvas format
2. Page count range
3. Target audience
4. Style objective
5. Color scheme
6. Icon usage approach
7. Typography plan, including formula rendering policy
8. Image usage approach

**Mandatory — split-mode note** (not a ninth confirmation): after listing the eight confirmation details, you MUST append exactly one short line (rendered in the user's language, prefixed with 💡) about generation mode. Pick the variant by qualitative read of Phase A signals — recommended page count, source-material bulk, whether `topic-research` ran with substantial web-fetch accumulation:

| Signal read | Line content |
|---|---|
| Heavy (long page count / bulky sources / heavy web-fetch accumulation) | State estimated page count and large source size; recommend switching to [split mode](workflows/resume-execute.md) after Step 5 — stop this chat, open a fresh window and input `继续生成 $WORK_DIR` to enter Phase B (SVG generation + export); no response or "continue" = default continuous mode. |
| Normal (default) | State scale is moderate, default continuous mode generates in one go; if mid-way window switch is desired, input `继续生成 $WORK_DIR` after Step 5 to switch to [split mode](workflows/resume-execute.md). |

This line is required output every run — the user must always see the mode choice exists. Whether to act on it is the user's call.

**Formula rendering policy lives inside item 7 (Typography plan)**:

| Policy | Behavior |
|---|---|
| `mixed` (default) | Strategist renders complex formula-worthy expressions as PNG assets; simple inline expressions remain editable text / Unicode |
| `render-all` | Strategist renders every formula-worthy expression as PNG assets |
| `text-only` | No formula rendering; formulas remain editable text / Unicode |

After the Eight Confirmations are approved and **before outputting `design_spec.md` / `spec_lock.md`**, if the confirmed formula policy is `mixed` or `render-all` and the content contains formula-worthy expressions, Strategist MUST:

1. Identify explicit LaTeX and any source expressions that should be faithfully structured as formulas.
2. Write `$WORK_DIR/images/formula_manifest.json` using the `file_write` tool.
3. Run latex_render.py directly:
   ```bash
   python3 ${SKILL_DIR}/scripts/latex_render.py "$WORK_DIR"
   ```
4. Include the rendered formula PNGs as `Acquire Via: formula`, `Status: Rendered`, `Type: Latex Formula` rows in `design_spec.md §VIII Image Resource List`; also list them in `spec_lock.md images` with `| no-crop`.

The formula renderer uses a provider fallback chain by default: `codecogs,quicklatex,mathpad,wikimedia`. Do not scan `spec_lock.md` for `$...$` or `$$...$$` — the renderer consumes the explicit manifest.

If the user provided images or formula PNGs were rendered, run analysis **before outputting the design spec**:
```bash
python3 ${SKILL_DIR}/scripts/analyze_images.py "$WORK_DIR/images"
```

> ⚠️ **Image handling**: NEVER directly read / open / view image files. All image info comes from `analyze_images.py` output or the Design Spec's Image Resource List.

**Output** — write both files into `$WORK_DIR` using the `file_write` tool:
```
file_write(path="$WORK_DIR/design_spec.md", content="...design spec content...")
file_write(path="$WORK_DIR/spec_lock.md",   content="...spec lock content...")
```

**✅ Checkpoint — Phase deliverables complete, auto-proceed to next step**:
```markdown
## ✅ Strategist Phase Complete
- [x] Eight Confirmations completed (user confirmed)
- [x] Split-mode note appended below the eight items (heavy or normal variant)
- [x] Design Specification & Content Outline generated
- [x] Execution lock (spec_lock.md) generated
- [ ] **Next**: Auto-proceed to [Image_Generator / Executor] phase
```

---

### Step 5: Image Acquisition Phase (Conditional)

🚧 **GATE**: Step 4 complete; Design Specification & Content Outline generated and user confirmed. Any formula rows already have `Acquire Via: formula` and `Status: Rendered`.

> **Trigger**: At least one row in the resource list has `Acquire Via: ai` and/or `Acquire Via: web`. If every row is `user`, `formula`, or `placeholder`, skip to Step 6.

**Always load the common framework**:

```
Read references/image-base.md
```

Then **lazy-load the path-specific reference** for each row that actually needs it:

| Acquire Via | Load reference (only if any such row exists) | Run |
|---|---|---|
| `ai` | `references/image-generator.md` | `python3 ${SKILL_DIR}/scripts/image_gen.py --manifest <project_path>/images/image_prompts.json` |
| `web` | `references/image-searcher.md` | `python3 ${SKILL_DIR}/scripts/image_search.py ...` |
| `user` / `placeholder` | (skip) | (skip) |

A deck with only `ai` rows never loads `image-searcher.md`; a deck with only `web` rows never loads `image-generator.md`. A mixed deck loads both, processes each row through its own path, and writes both `image_prompts.json` and `image_sources.json`.

> ⚠️ **In-pipeline ai path MUST use manifest mode** — even when only 1 ai row exists. Write `images/image_prompts.json` first, then run `image_gen.py --manifest`, then `image_gen.py --render-md` to produce the `image_prompts.md` sidecar. The positional form (`image_gen.py "prompt" ...`) is reserved for **out-of-pipeline one-off testing / single-image fixups** — it skips manifest + sidecar, leaving no audit trail.

Workflow:

1. Extract all rows with `Status: Pending` and `Acquire Via ∈ {ai, web}` from the design spec
2. Generate prompts (ai rows) and/or run search (web rows) per [image-base.md](references/image-base.md) §2 dispatch table
3. Verify every row reaches a terminal status: `Generated` (ai success), `Sourced` (web success), or `Needs-Manual`

**✅ Checkpoint — Confirm acquisition attempted for every row**:
```markdown
## ✅ Image Acquisition Phase Complete
- [x] image_prompts.json created (when any ai rows processed)
- [x] image_prompts.md sidecar rendered (when any ai rows processed)
- [x] image_sources.json created (when any web rows processed)
- [x] Each row: status is `Generated` / `Sourced` / `Needs-Manual` (no `Pending` remaining)
```

**Default — auto-proceed to Step 6.** Only when the user's Step 4 response explicitly opted into split mode (in reply to the optional hint), output the Phase A hand-off below and stop this conversation:

  ```markdown
  ## ✅ Phase A Complete
  - [x] Spec: `design_spec.md`, `spec_lock.md`
  - [x] Resources: `sources/`, `images/`, `templates/`
  - [x] Working directory: `$WORK_DIR`
  - [ ] **Next**: open a fresh chat window and input `继续生成 <WORK_DIR路径>` to enter Phase B via the [`resume-execute`](workflows/resume-execute.md) workflow.
  ```

> On acquisition failure, do NOT halt — follow the Failure Handling rule in [image-base.md](references/image-base.md) §5: retry once, then mark the row `Needs-Manual`, report to user, and continue to the checkpoint above.

---

### Step 6: Executor Phase

🚧 **GATE**: Step 4 (and Step 5 if triggered) complete; all prerequisite deliverables are ready.

Read the role definition based on the selected style:
```
Read references/executor-base.md          # REQUIRED: common guidelines
Read references/shared-standards.md       # REQUIRED: SVG/PPT technical constraints
Read references/executor-general.md       # General flexible style
Read references/executor-consultant.md    # Consulting style
Read references/executor-consultant-top.md # Top consulting style (MBB level)
```

> Only read executor-base + shared-standards + one style file.

**Design Parameter Confirmation (Mandatory)**: before the first SVG, output key design parameters from the spec (canvas dimensions, color scheme, font plan, body font size). See executor-base.md §2.

**Live Preview Auto-Startup**: skipped in server/pod deployment (no accessible localhost). If running locally, see `workflows/live-preview.md`.

**Pre-generation Batch Read (Mandatory)**: before the first SVG, read `spec_lock.md` and every distinct layout/chart SVG referenced in it using the `file_read` tool:
```
file_read(path="$WORK_DIR/spec_lock.md")
```
One read per file, up front — do not re-read layout/chart templates during page generation. See executor-base.md §1.0.

**Per-page spec_lock re-read (Mandatory)**: before **each** SVG page, re-read `spec_lock.md` from the working directory:
```
file_read(path="$WORK_DIR/spec_lock.md")
```
Use only its colors / fonts / icons / images, plus the per-page `page_rhythm` / `page_layouts` / `page_charts` lookups. Resists context-compression drift on long decks. See executor-base.md §2.1.

> ⚠️ **Main-agent only**: SVG generation MUST stay in the current main agent — page design depends on full upstream context. Do NOT delegate to sub-agents.
> ⚠️ **Generation rhythm**: generate pages sequentially, one at a time, in the same continuous context. Do NOT batch (e.g., 5 per group).

**Visual Construction Phase**: generate SVG pages sequentially, one at a time, write each to `$WORK_DIR/svg_output/` using the `file_write` tool:
```
file_write(path="$WORK_DIR/svg_output/slide_01.svg", content="<svg xmlns='...' viewBox='0 0 1280 720'>...</svg>")
```

**Quality Check Gate (Mandatory)** — after all SVGs, BEFORE annotation handling and speaker notes:
```bash
python3 ${SKILL_DIR}/scripts/svg_quality_checker.py "$WORK_DIR"
```
- Any `error` (banned SVG features, viewBox mismatch, spec_lock drift, etc.) MUST be fixed before proceeding — regenerate the affected page via `file_write`, re-run check.
- `warning` entries: fix when straightforward, otherwise acknowledge and release.
- Run against `svg_output/` (not after `finalize_svg.py` — finalize rewrites SVG and masks violations).

**Logic Construction Phase**: generate speaker notes and write to working directory:
```
file_write(path="$WORK_DIR/notes/total.md", content="...speaker notes content...")
```

**✅ Checkpoint — Confirm all SVGs and notes are fully generated and quality-checked. Proceed directly to Step 7 post-processing**:
```markdown
## ✅ Executor Phase Complete
- [x] All SVGs generated to $WORK_DIR/svg_output/
- [x] svg_quality_checker.py passed (0 errors)
- [x] Speaker notes generated at $WORK_DIR/notes/total.md
```

> **Chart pages?** If this deck contains data charts (bar / line / pie / radar / etc.), run the standalone [`verify-charts`](workflows/verify-charts.md) workflow before Step 7 to calibrate coordinates. AI models routinely introduce 10–50 px errors when mapping data to pixel positions; verify-charts eliminates that class of error. Skip if no chart pages.

> **Visual self-check (opt-in)?** If the user explicitly asked for a per-page visual re-pass on the SVGs ("跑一下视觉自检 / 视觉回看", "visual review", "check pages visually", etc.), run the standalone [`visual-review`](workflows/visual-review.md) workflow before Step 7. Do NOT run it by default and do NOT recommend it based on inferred model capability or deck size — trigger is user request only.

---

### Step 7: Post-processing & Export

🚧 **GATE**: Step 6 complete; all SVGs generated to `svg_output/`; speaker notes `notes/total.md` generated.

🚧 **Image readiness GATE** (when Step 5 left ai rows in `Needs-Manual`): verify all expected image files exist before running 7.1:
```bash
ls "$WORK_DIR/images/"
```
If files are missing: PAUSE, list the missing filenames, point the user to `$WORK_DIR/images/image_prompts.md`, and ask them to supply the images. Move each uploaded image into `$WORK_DIR/images/<filename>`. Resume Step 7.1 only after all expected files are in place.

> ⚠️ Run the three sub-steps **one at a time** — each must complete successfully before the next.
> ❌ **NEVER** combine them into a single code block or shell invocation.

Canonical three-command pipeline (mirrors `references/shared-standards.md` §5):

**Step 7.1** — Split speaker notes:
```bash
python3 ${SKILL_DIR}/scripts/total_md_split.py "$WORK_DIR"
```

**Step 7.2** — SVG post-processing (icon embedding / image crop & embed / text flattening / rounded rect to path):
```bash
python3 ${SKILL_DIR}/scripts/finalize_svg.py "$WORK_DIR"
```

**Step 7.3** — Export PPTX, upload to MinIO, then delete working directory:
```bash
# 1. Generate PPTX
python3 ${SKILL_DIR}/scripts/svg_to_pptx.py "$WORK_DIR"

# 2. Upload the generated PPTX to MinIO (file will appear in user's "我的文件")
PPTX_FILE=$(find "$WORK_DIR/exports" -name "*.pptx" -not -name "*_svg.pptx" | head -1)
if [ -z "$PPTX_FILE" ]; then
    echo "ERROR: No PPTX file found in $WORK_DIR/exports/" >&2
    python3 ${SKILL_DIR}/scripts/minio_project.py cleanup --work-dir "$WORK_DIR"
    exit 1
fi
python3 ${SKILL_DIR}/scripts/minio_project.py upload-result "$PPTX_FILE"

# 3. Explicitly delete working directory
#    upload-result cleans up the work_dir it inferred from the PPTX path,
#    but explicit cleanup ensures it's gone even if inference failed.
python3 ${SKILL_DIR}/scripts/minio_project.py cleanup --work-dir "$WORK_DIR"
```

> **Cleanup guarantee**: `upload-result` always deletes the working directory it inferred
> from the PPTX file path (even on upload failure). The explicit `cleanup` call after it
> is a safety net — if `$WORK_DIR` was already deleted, it exits cleanly. If you ever find
> orphaned directories under `tmp-doc/`, run:
> ```bash
> python3 ${SKILL_DIR}/scripts/minio_project.py cleanup-stale --max-age-hours 24
> ```

> **Paragraph editability vs line fidelity** — by default every dy-stacked line is
> its own PowerPoint text frame, preserving exact SVG layout. Add `--merge-paragraphs`
> only when the user explicitly asks for an editable / wrap-friendly export.

**Optional animation flags** (the defaults already enable rich entrance animations — adjust only when the user asks for something different):
- `-t <effect>` — page transition. Default `fade`. Options: `fade` / `push` / `wipe` / `split` / `strips` / `cover` / `random` / `none`.
- `-a <effect>` — per-element entrance animation. Default `auto`.
- `--animation-trigger {on-click,with-previous,after-previous}` — Start mode. Default `after-previous`.
- `--animation-config <path>` — optional object-level sidecar. Use `"$WORK_DIR/animations.json"`.
- `--auto-advance <seconds>` — kiosk-style auto-play.

**Optional custom animations** (only when the user asks to tune animation order/effects/timing for specific objects):

Run the standalone [`customize-animations`](workflows/customize-animations.md) workflow. Default export already has global entrance animation; do not create `animations.json` unless object-level customization was requested.

**Optional recorded narration** (only when the user asks for narrated/video export):

Run the standalone [`generate-audio`](workflows/generate-audio.md) workflow. The AI picks a narration backend (`edge` by default, or a configured cloud provider such as ElevenLabs / MiniMax / Qwen / CosyVoice for high-quality or cloned voices), asks the user once (backend + voice + rate/settings + embed-or-not, all with recommended values), then executes `notes_to_audio.py` and (if chosen) re-exports the PPTX with `--recorded-narration audio`.

Do NOT call `notes_to_audio.py` directly without going through the workflow — `--voice` / `--voice-id` is required and the workflow produces the locale/provider-aware recommendation that makes the choice meaningful.

Full effect list, anchor logic, and limits: [`references/animations.md`](references/animations.md).

> ❌ **NEVER** substitute `cp` for `finalize_svg.py` — finalize performs multiple critical processing steps
> ❌ **NEVER** force `-s output` for the legacy/preview pptx (PowerPoint's internal SVG parser drops icons and rounded corners). The default auto-split already gives native the high-fidelity source it needs without touching legacy.
> ❌ **NEVER** use `--only` (it suppresses one of the two output files)

> **Post-export annotation window**: the preview service from Step 6 typically remains running after export. If the user submitted annotations in the browser (during Executor or after export) and now asks to apply them — they may quote the browser prompt (`Annotations saved. ... apply my annotations`), say "apply my annotations" / "应用注解" / equivalent — run [`live-preview`](workflows/live-preview.md) Step 2 to apply and re-export. Annotations submitted during generation are also handled here, not earlier.

> **Preview not running?** Any time the user mentions "live preview", "preview", "看效果", or wants to select/click a slide element and the service is not running, run [`live-preview`](workflows/live-preview.md) Step 1 to start it. If the service is already running, just point them at the URL — do not restart.

---

## Role Switching Protocol

Before switching roles, **MUST first read** the corresponding reference file. Output marker:

```markdown
## [Role Switch: <Role Name>]
📖 Reading role definition: references/<filename>.md
📋 Current task: <brief description>
```

---

## Reference Resources

| Resource | Path |
|----------|------|
| Shared technical constraints | `references/shared-standards.md` |
| Canvas format specification | `references/canvas-formats.md` |
| Image-text layout patterns (Primary structures + Modifier layers — combine freely) | `references/image-layout-patterns.md` |
| Image layout sizing (math for side-by-side container dimensions) | `references/image-layout-spec.md` |
| SVG image embedding | `references/svg-image-embedding.md` |
| Icon library | `templates/icons/README.md` |

---

## Notes

- Local preview: `python3 -m http.server -d <project_path>/svg_final 8000`
- **Troubleshooting**: on generation issues (layout overflow, export errors, blank images, etc.), check `docs/faq.md` for known solutions
