---
description: Phase B entry — resume PPT execution in a fresh chat after Phase A (SKILL.md Step 1-5) completed in a previous session. Reads project state from the tmp-doc working directory and runs Step 6 + Step 7 with no Phase-A context carry-over.
---

# Resume Execute Workflow

> Standalone Phase-B entry. Run when Phase A (SKILL.md Step 1–5) completed in a previous session and the user wants to continue with SVG generation + export. Loads project state from the working directory and runs Step 6 + Step 7 in a clean session.

This workflow is **independent**: it owns Phase B starting from a fresh chat — no upstream conversation context required. By isolating SVG generation in its own session, the model gains 20–40K context headroom by not carrying Phase A's eight-confirmation dialogue, image search/fetch results, or Strategist references.

## When to Run

The user opens a new chat and gives a phrase that names a working directory path and signals continuation. Recognize any of:

| Pattern | Example |
|---|---|
| `继续生成 <work_dir_path>` | `继续生成 /app/tmp-doc/42_a3f7c891b2d4...` |
| `resume execution <work_dir_path>` | `resume execution /app/tmp-doc/42_a3f7c891b2d4...` |
| Path containing `tmp-doc/` + any "继续 / 恢复 / 继续做 / 接着做" semantic | `把 /app/tmp-doc/42_a3f7c891b2d4 继续做完` |

Extract the path and treat it as `$WORK_DIR` for the remainder of this workflow.

**Prerequisite**: Phase A must have completed in the named working directory. Verified by file presence in Step 1; do NOT auto-trigger Phase A on missing state.

---

## Step 1: Sanity check

Set `$WORK_DIR` to the path the user provided, then verify Phase-A artifacts:

```bash
export WORK_DIR="<path from user>"
```

| File / Directory | Required when | Reason |
|---|---|---|
| `$WORK_DIR/spec_lock.md` | Always | Strategist's execution contract; Executor reads it per page |
| `$WORK_DIR/design_spec.md` | Always | Section IX page outline; Executor cross-references it |
| `$WORK_DIR/images/` | `spec_lock images` references any image | Images must exist for embedding |
| `$WORK_DIR/templates/` | `spec_lock page_layouts` / `page_charts` references any | Layout / chart SVGs needed for batch read |

If any required artifact is missing → report which one(s) and stop. Do NOT auto-fall-back into Phase A; the user must either complete Phase A in the original session or explicitly restart.

---

## Step 2: Load SKILL.md, proceed from Step 6

```
Read skills/ppt-master/SKILL.md
```

Then jump to `### Step 6: Executor Phase` and run the documented pipeline with `$WORK_DIR` already set:

- Read references (executor-base + shared-standards + chosen style file)
- Design Parameter Confirmation
- Pre-generation Batch Read (every layout / chart SVG referenced in `spec_lock`)
- Per-page `spec_lock` re-read + sequential page generation
- Quality Check Gate
- Speaker notes generation
- Step 7: Post-processing & Export (`total_md_split` → `finalize_svg` → `svg_to_pptx` → `upload-result` → `cleanup`)

The fresh session pays the cost of re-reading references (~14K tokens) but earns back substantially more headroom by dropping Phase A's accumulated context. Net win in both window pressure and reasoning budget per page.

**Source materials**: Phase B is a fresh session; `$WORK_DIR/sources/<file>.md` is NOT in context. The Executor SHOULD read the relevant `sources/` files when crafting per-page content — they hold the concrete facts, quotes, names, and details that turn skeleton outlines into substantive slides.

---

## Step 3: Hand-back

When Step 7 completes, the PPTX is uploaded to MinIO and `$WORK_DIR` is deleted. Report the upload result to the user (file available in "我的文件").

If the deck contains data charts, the [`verify-charts`](verify-charts.md) workflow runs between Step 6 and Step 7 as documented in SKILL.md — resume mode handles it the same way the continuous mode does.
