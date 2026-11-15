# PDF Human Review

A plugin that lets a person review a PDF in the browser and hand their comments back to the agent that asked.

The review page shows the PDF itself, drawn by PDF.js. The reviewer selects text, or presses the area button and drags a box around a figure, table or equation, and writes a comment in the margin. Comments can be edited and deleted. Pressing **Submit comments** sends them to the agent:

```
Feedback for path/xyz.pdf from human reviewer
> [page 4] the text the reviewer selected
The reviewer's comment

> [page 4] [Comment on the Figure itself] Figure 2: the caption (image of the boxed area: /tmp/pdf-human-review/xyz-1a2b3c4d/region-1.png)
The reviewer's comment on the figure
```

The plugin stops there. Finding the passage in a LaTeX source, editing and recompiling are left to the calling agent.

## Install (Claude Code)

```bash
claude plugin marketplace add /path/to/pdf-human-review
```

```bash
claude plugin install pdf-human-review@pdf-human-review
```

## Other agents

The skill in `skills/pdf-human-review/` is in the shared agent-skill format, and its scripts are plain Python. Each agent finds it through its own manifest:

| Agent | Manifest |
|---|---|
| Claude Code, Cowork | `.claude-plugin/plugin.json` |
| Codex | `.codex-plugin/plugin.json`, with a local marketplace in `.agents/plugins/marketplace.json` |
| Antigravity | `.antigravity-plugin/plugin.json` (install with `agy plugin install <repository URL or path>`) |

Only the Claude Code install has been tested. The Codex and Antigravity manifests follow the layout other multi-agent plugins use and have not been tried on those agents. An agent with no plugin system can still use the skill if the `skills/pdf-human-review/` folder is copied into its skills location.

## Use

`/pdf-human-review <file.pdf>` starts a review. Saying "I want to do a human review of this PDF" also works, and the agent asks before starting. One PDF is reviewed at a time. There is nothing to set up.

## How it works

| File | Job |
|---|---|
| `skills/pdf-human-review/SKILL.md` | The workflow the agent follows. |
| `scripts/review_server.py` | Builds the page, serves it on `127.0.0.1`, waits for Submit, prints the feedback. `collect` reads the feedback from the working folder or, failing that, from the clipboard. `clean` removes working files. |
| `scripts/build_review.py` | Embeds the PDF in the review page, giving one self-contained HTML file. |
| `assets/review_template.html` | The page and its commenting UI. |

The scripts use only the Python standard library. The page loads PDF.js 3.11 from jsDelivr, so the reviewer's browser needs an internet connection.

If the page cannot reach the local server, Submit copies the feedback to the clipboard, and the agent reads it from there when the reviewer says they have submitted.

## Files and cleanup

Nothing is written into your project. Working files for a review go in a folder for that PDF under the system temporary folder.

- Each review of the same PDF empties the folder first, so rounds of an iterative review do not pile up.
- After Submit the folder holds only `feedback.md`, `feedback.json` and one `region-N.png` per boxed area, which the agent opens to see what was boxed. If the server is stopped before Submit, the folder is removed.
- Folders of other reviews untouched for a week are removed when a new review starts, and the operating system clears its temporary folder as usual.
- `python3 scripts/review_server.py clean` removes everything at once.

## Development

The version number lives in three files, which need changing together on each release:

- `.claude-plugin/plugin.json`
- `.codex-plugin/plugin.json`
- `.antigravity-plugin/plugin.json`
