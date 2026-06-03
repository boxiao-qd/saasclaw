---
name: skill-creator
description: Create or update personal AgentSkills (技能). MUST use this skill whenever the user asks to create, build, make, or add a new skill/capability/tool — including natural language requests like "创建一个技能", "帮我做一个XXX技能", "新建一个查询天气的技能", "I want a skill that does X". Do NOT use skill_manage to create skills directly — always go through this workflow to ensure proper structure, frontmatter, and storage in MySQL + MinIO.
---

# Skill Creator

## ⚠️ 硬性禁令（创建 skill 前必读）

**以下行为严格禁止，无论工具箱里有没有对应工具：**

1. **禁止用 MCP 工具（SQLite / Notion / 任何 MCP server）存储 skill 数据。**
   MCP SQLite 是 agent 的记忆库，与技能系统完全隔离，写进去的数据不会出现在技能列表里，等于没创建。
   **唯一合法的存储路径是 `save_skill.py`（写 MySQL + MinIO）。**

2. **禁止搜索文件系统来定位本 skill 的脚本。** 所有脚本路径已在本文档明确给出，直接使用，不需要 find / glob / search：
   - workdir 管理：`scripts/workdir.py`
   - skill 初始化：`sys-infra/skills/skill-creator/scripts/init_skill.py`
   - skill 保存：`sys-infra/skills/skill-creator/scripts/save_skill.py`

3. **禁止用文件搜索查询已有的个人 skill。**
   个人 skill 存储在 MySQL，不在文件系统里。查看个人 skill 列表用 `skill_list` 工具。
   **例外**：在 `tmp-doc/` 下的 workdir 里读写文件是合法的——skill 含有 scripts/references/assets 时需要先写到 workdir，再由 `save_skill.py` 上传 MinIO。

4. **禁止用 `skill_manage(action=create)` 工具创建新 skill。**
   该工具会返回错误。

**正确路径：** 只用 `save_skill.py` 脚本保存 skill，内容走 stdin（仅 SKILL.md）或 workdir（含子目录文件）。

---

This skill provides guidance for creating effective skills.

## About Skills

Skills are modular, self-contained packages that extend Codex's capabilities by providing
specialized knowledge, workflows, and tools. Think of them as "onboarding guides" for specific
domains or tasks—they transform Codex from a general-purpose agent into a specialized agent
equipped with procedural knowledge that no model can fully possess.

### What Skills Provide

1. Specialized workflows - Multi-step procedures for specific domains
2. Tool integrations - Instructions for working with specific file formats or APIs
3. Domain expertise - Company-specific knowledge, schemas, business logic
4. Bundled resources - Scripts, references, and assets for complex and repetitive tasks

## Core Principles

### Concise is Key

The context window is a public good. Skills share the context window with everything else Codex needs: system prompt, conversation history, other Skills' metadata, and the actual user request.

**Default assumption: Codex is already very smart.** Only add context Codex doesn't already have. Challenge each piece of information: "Does Codex really need this explanation?" and "Does this paragraph justify its token cost?"

Prefer concise examples over verbose explanations.

### Set Appropriate Degrees of Freedom

Match the level of specificity to the task's fragility and variability:

**High freedom (text-based instructions)**: Use when multiple approaches are valid, decisions depend on context, or heuristics guide the approach.

**Medium freedom (pseudocode or scripts with parameters)**: Use when a preferred pattern exists, some variation is acceptable, or configuration affects behavior.

**Low freedom (specific scripts, few parameters)**: Use when operations are fragile and error-prone, consistency is critical, or a specific sequence must be followed.

Think of Codex as exploring a path: a narrow bridge with cliffs needs specific guardrails (low freedom), while an open field allows many routes (high freedom).

### Anatomy of a Skill

Every skill consists of a required SKILL.md file and optional bundled resources:

```
skill-name/
├── SKILL.md (required)
│   ├── YAML frontmatter metadata (required)
│   │   ├── name: (required)
│   │   └── description: (required)
│   └── Markdown instructions (required)
└── Bundled Resources (optional)
    ├── scripts/          - Executable code (Python/Bash/etc.)
    ├── references/       - Documentation intended to be loaded into context as needed
    └── assets/           - Files used in output (templates, icons, fonts, etc.)
```

#### SKILL.md (required)

Every SKILL.md consists of:

- **Frontmatter** (YAML): Contains `name` and `description` fields. These are the only fields that Codex reads to determine when the skill gets used, thus it is very important to be clear and comprehensive in describing what the skill is, and when it should be used.
- **Body** (Markdown): Instructions and guidance for using the skill. Only loaded AFTER the skill triggers (if at all).

#### Bundled Resources (optional)

##### Scripts (`scripts/`)

Executable code (Python/Bash/etc.) for tasks that require deterministic reliability or are repeatedly rewritten.

- **When to include**: When the same code is being rewritten repeatedly or deterministic reliability is needed
- **Example**: `scripts/rotate_pdf.py` for PDF rotation tasks
- **Benefits**: Token efficient, deterministic, may be executed without loading into context
- **Note**: Scripts may still need to be read by Codex for patching or environment-specific adjustments

##### References (`references/`)

Documentation and reference material intended to be loaded as needed into context to inform Codex's process and thinking.

- **When to include**: For documentation that Codex should reference while working
- **Examples**: `references/finance.md` for financial schemas, `references/mnda.md` for company NDA template, `references/policies.md` for company policies, `references/api_docs.md` for API specifications
- **Use cases**: Database schemas, API documentation, domain knowledge, company policies, detailed workflow guides
- **Benefits**: Keeps SKILL.md lean, loaded only when Codex determines it's needed
- **Best practice**: If files are large (>10k words), include grep search patterns in SKILL.md
- **Avoid duplication**: Information should live in either SKILL.md or references files, not both. Prefer references files for detailed information unless it's truly core to the skill—this keeps SKILL.md lean while making information discoverable without hogging the context window. Keep only essential procedural instructions and workflow guidance in SKILL.md; move detailed reference material, schemas, and examples to references files.

##### Assets (`assets/`)

Files not intended to be loaded into context, but rather used within the output Codex produces.

- **When to include**: When the skill needs files that will be used in the final output
- **Examples**: `assets/logo.png` for brand assets, `assets/slides.pptx` for PowerPoint templates, `assets/frontend-template/` for HTML/React boilerplate, `assets/font.ttf` for typography
- **Use cases**: Templates, images, icons, boilerplate code, fonts, sample documents that get copied or modified
- **Benefits**: Separates output resources from documentation, enables Codex to use files without loading them into context

#### What to Not Include in a Skill

A skill should only contain essential files that directly support its functionality. Do NOT create extraneous documentation or auxiliary files, including:

- README.md
- INSTALLATION_GUIDE.md
- QUICK_REFERENCE.md
- CHANGELOG.md
- etc.

The skill should only contain the information needed for an AI agent to do the job at hand. It should not contain auxiliary context about the process that went into creating it, setup and testing procedures, user-facing documentation, etc. Creating additional documentation files just adds clutter and confusion.

### Progressive Disclosure Design Principle

Skills use a three-level loading system to manage context efficiently:

1. **Metadata (name + description)** - Always in context (~100 words)
2. **SKILL.md body** - When skill triggers (<5k words)
3. **Bundled resources** - As needed by Codex (Unlimited because scripts can be executed without reading into context window)

#### Progressive Disclosure Patterns

Keep SKILL.md body to the essentials and under 500 lines to minimize context bloat. Split content into separate files when approaching this limit. When splitting out content into other files, it is very important to reference them from SKILL.md and describe clearly when to read them, to ensure the reader of the skill knows they exist and when to use them.

**Key principle:** When a skill supports multiple variations, frameworks, or options, keep only the core workflow and selection guidance in SKILL.md. Move variant-specific details (patterns, examples, configuration) into separate reference files.

**Pattern 1: High-level guide with references**

```markdown
# PDF Processing

## Quick start

Extract text with pdfplumber:
[code example]

## Advanced features

- **Form filling**: See [FORMS.md](FORMS.md) for complete guide
- **API reference**: See [REFERENCE.md](REFERENCE.md) for all methods
- **Examples**: See [EXAMPLES.md](EXAMPLES.md) for common patterns
```

Codex loads FORMS.md, REFERENCE.md, or EXAMPLES.md only when needed.

**Pattern 2: Domain-specific organization**

For Skills with multiple domains, organize content by domain to avoid loading irrelevant context:

```
bigquery-skill/
├── SKILL.md (overview and navigation)
└── reference/
    ├── finance.md (revenue, billing metrics)
    ├── sales.md (opportunities, pipeline)
    ├── product.md (API usage, features)
    └── marketing.md (campaigns, attribution)
```

When a user asks about sales metrics, Codex only reads sales.md.

Similarly, for skills supporting multiple frameworks or variants, organize by variant:

```
cloud-deploy/
├── SKILL.md (workflow + provider selection)
└── references/
    ├── aws.md (AWS deployment patterns)
    ├── gcp.md (GCP deployment patterns)
    └── azure.md (Azure deployment patterns)
```

When the user chooses AWS, Codex only reads aws.md.

**Pattern 3: Conditional details**

Show basic content, link to advanced content:

```markdown
# DOCX Processing

## Creating documents

Use docx-js for new documents. See [DOCX-JS.md](DOCX-JS.md).

## Editing documents

For simple edits, modify the XML directly.

**For tracked changes**: See [REDLINING.md](REDLINING.md)
**For OOXML details**: See [OOXML.md](OOXML.md)
```

Codex reads REDLINING.md or OOXML.md only when the user needs those features.

**Important guidelines:**

- **Avoid deeply nested references** - Keep references one level deep from SKILL.md. All reference files should link directly from SKILL.md.
- **Structure longer reference files** - For files longer than 100 lines, include a table of contents at the top so Codex can see the full scope when previewing.

## Skill Creation Process

Skill creation involves these steps:

1. Understand the skill with concrete examples
2. Plan reusable skill contents (scripts, references, assets)
3. Initialize the skill (run init_skill.py)
4. Edit the skill (implement resources and write SKILL.md)
5. Package the skill (run package_skill.py)
6. Iterate based on real usage

Follow these steps in order, skipping only if there is a clear reason why they are not applicable.

### Skill Naming

- Use lowercase letters, digits, and hyphens only; normalize user-provided titles to hyphen-case (e.g., "Plan Mode" -> `plan-mode`).
- When generating names, generate a name under 64 characters (letters, digits, hyphens).
- Prefer short, verb-led phrases that describe the action.
- Namespace by tool when it improves clarity or triggering (e.g., `gh-address-comments`, `linear-address-issue`).
- Name the skill folder exactly after the skill name.

### Step 1: Understanding the Skill with Concrete Examples

Skip this step only when the skill's usage patterns are already clearly understood. It remains valuable even when working with an existing skill.

To create an effective skill, clearly understand concrete examples of how the skill will be used. This understanding can come from either direct user examples or generated examples that are validated with user feedback.

For example, when building an image-editor skill, relevant questions include:

- "What functionality should the image-editor skill support? Editing, rotating, anything else?"
- "Can you give some examples of how this skill would be used?"
- "I can imagine users asking for things like 'Remove the red-eye from this image' or 'Rotate this image'. Are there other ways you imagine this skill being used?"
- "What would a user say that should trigger this skill?"

To avoid overwhelming users, avoid asking too many questions in a single message. Start with the most important questions and follow up as needed for better effectiveness.

Conclude this step when there is a clear sense of the functionality the skill should support.

### Step 2: Planning the Reusable Skill Contents

To turn concrete examples into an effective skill, analyze each example by:

1. Considering how to execute on the example from scratch
2. Identifying what scripts, references, and assets would be helpful when executing these workflows repeatedly

Example: When building a `pdf-editor` skill to handle queries like "Help me rotate this PDF," the analysis shows:

1. Rotating a PDF requires re-writing the same code each time
2. A `scripts/rotate_pdf.py` script would be helpful to store in the skill

Example: When designing a `frontend-webapp-builder` skill for queries like "Build me a todo app" or "Build me a dashboard to track my steps," the analysis shows:

1. Writing a frontend webapp requires the same boilerplate HTML/React each time
2. An `assets/hello-world/` template containing the boilerplate HTML/React project files would be helpful to store in the skill

Example: When building a `big-query` skill to handle queries like "How many users have logged in today?" the analysis shows:

1. Querying BigQuery requires re-discovering the table schemas and relationships each time
2. A `references/schema.md` file documenting the table schemas would be helpful to store in the skill

To establish the skill's contents, analyze each concrete example to create a list of the reusable resources to include: scripts, references, and assets.

### Step 3: Initializing the Skill

At this point, it is time to actually create the skill.

Skip this step only if the skill being developed already exists, and iteration or packaging is needed. In this case, continue to the next step.

**Super-Agent Workflow**: Skills are created in a temporary working directory (`tmp-doc/`) and then saved to the platform (MySQL + MinIO). The workdir is automatically cleaned up after saving.

Use the injected environment variables — **do NOT search for these scripts**:
- `$SA_WORKDIR_SCRIPT` — absolute path to `scripts/workdir.py`
- `$SA_PROJECT_ROOT` — absolute path to the project root

```bash
# 1. Create a working directory (output is JSON, parse work_dir field)
WORKDIR=$(python3 $SA_WORKDIR_SCRIPT create | python3 -c "import sys,json; print(json.load(sys.stdin)['work_dir'])")

# 2. Initialize the skill template into the workdir
python3 $SA_PROJECT_ROOT/sys-infra/skills/skill-creator/scripts/init_skill.py <skill-name> --path $WORKDIR [--resources scripts,references,assets]
```

The `init_skill.py` script:

- Creates the skill directory structure at the specified path
- Generates a SKILL.md template with proper frontmatter and TODO placeholders
- Optionally creates resource directories based on `--resources`

After initialization, customize the SKILL.md and add resources as needed. All files should be written inside the workdir.

### Step 4: Edit the Skill

When editing the (newly-generated or existing) skill, remember that the skill is being created for another instance of Codex to use. Include information that would be beneficial and non-obvious to Codex. Consider what procedural knowledge, domain-specific details, or reusable assets would help another Codex instance execute these tasks more effectively.

#### Learn Proven Design Patterns

Consult these helpful guides based on your skill's needs:

- **Multi-step processes**: See references/workflows.md for sequential workflows and conditional logic
- **Specific output formats or quality standards**: See references/output-patterns.md for template and example patterns

These files contain established best practices for effective skill design.

#### Start with Reusable Skill Contents

To begin implementation, start with the reusable resources identified above: `scripts/`, `references/`, and `assets/` files. Note that this step may require user input. For example, when implementing a `brand-guidelines` skill, the user may need to provide brand assets or templates to store in `assets/`, or documentation to store in `references/`.

Added scripts must be tested by actually running them to ensure there are no bugs and that the output matches what is expected. If there are many similar scripts, only a representative sample needs to be tested to ensure confidence that they all work while balancing time to completion.

If you used `--examples`, delete any placeholder files that are not needed for the skill. Only create resource directories that are actually required.

#### Update SKILL.md

**Writing Guidelines:** Always use imperative/infinitive form.

##### Frontmatter

Write the YAML frontmatter with `name` and `description`:

- `name`: The skill name
- `description`: This is the primary triggering mechanism for your skill, and helps Codex understand when to use the skill.
  - Include both what the Skill does and specific triggers/contexts for when to use it.
  - Include all "when to use" information here - Not in the body. The body is only loaded after triggering, so "When to Use This Skill" sections in the body are not helpful to Codex.
  - Example description for a `docx` skill: "Comprehensive document creation, editing, and analysis with support for tracked changes, comments, formatting preservation, and text extraction. Use when Codex needs to work with professional documents (.docx files) for: (1) Creating new documents, (2) Modifying or editing content, (3) Working with tracked changes, (4) Adding comments, or any other document tasks"

Do not include any other fields in YAML frontmatter.

##### Body

Write instructions for using the skill and its bundled resources.

### Step 5: Saving the Skill

Two modes depending on whether the skill has extra files (scripts/, references/, assets/):

Use the injected environment variables — **do NOT search for these scripts**:
- `$SA_WORKDIR_SCRIPT` — absolute path to `scripts/workdir.py`
- `$SA_PROJECT_ROOT` — absolute path to the project root

**SKILL.md only — pass content via stdin, no workdir needed:**
```bash
cat << 'EOF' | python3 $SA_PROJECT_ROOT/sys-infra/skills/skill-creator/scripts/save_skill.py -
---
name: my-skill
description: What this skill does and when to use it
---

# My Skill
...
EOF
```

**Has extra files — use workdir:**
```bash
# 1. Create workdir
WORKDIR=$(python3 $SA_WORKDIR_SCRIPT create | python3 -c "import sys,json; print(json.load(sys.stdin)['work_dir'])")

# 2. Initialize and edit skill
python3 $SA_PROJECT_ROOT/sys-infra/skills/skill-creator/scripts/init_skill.py <skill-name> --path $WORKDIR [--resources scripts,references,assets]
# ... edit SKILL.md and add files under $WORKDIR/<skill-name>/ ...

# 3. Save skill (auto-cleans skill subdir on success)
python3 $SA_PROJECT_ROOT/sys-infra/skills/skill-creator/scripts/save_skill.py $WORKDIR/<skill-name> [--name DISPLAY_NAME]

# 4. Cleanup parent workdir
python3 $SA_WORKDIR_SCRIPT cleanup --path $WORKDIR
```

The script will:

1. **Parse** SKILL.md frontmatter → extract `name`, `description`
2. **Create** a skill record in MySQL (`content_md`, `frontmatter`, `header_description`)
3. **Upload** scripts/references/assets to MinIO under `user-skill/{id}/` — **only when extra files exist; SKILL.md itself is never uploaded to MinIO**
4. **Cleanup** workdir automatically on success (directory mode only)
5. **Handle conflicts**: returns `{"status": "conflict", "error_code": "BX_SKILL_1002"}` if name already exists

**Name conflict resolution**: If `save_skill.py` returns `{"status": "conflict", ...}`:

1. Tell the user: "A skill named '{name}' already exists. Overwrite?"
2. If user confirms:
   - Delete the existing skill via the API (`DELETE /api/v1/skills/{id}` or by name)
   - Re-run `save_skill.py`
3. If user declines:
   - Ask for a different name and re-run with `--name`

After saving, the workdir is no longer needed — the skill and all its files are persisted in the platform.

**File output handling**: If the skill produces result files during execution (not the skill definition itself, but files generated for the user), use the workdir pattern:

```bash
# Create a workdir for file outputs
WORKDIR=$(python3 scripts/workdir.py create)

# ... generate files into $WORKDIR ...

# Upload results to MinIO and cleanup
python3 scripts/workdir.py upload-result $WORKDIR
```

The `upload-result` command uploads all files to MinIO under `user-data/{employee_id}/`, records them in the database, and automatically cleans up the workdir. This pattern is the same as used by ppt-master and other built-in skills.

### Step 6: Iterate

After testing the skill, users may request improvements. Often this happens right after using the skill, with fresh context of how the skill performed.

**Iteration workflow:**

1. Use the skill on real tasks
2. Notice struggles or inefficiencies
3. Identify how SKILL.md or bundled resources should be updated
4. Implement changes and test again
