---
name: pdf-human-review
description: Open one PDF in an interactive review page where a human selects text or boxes a figure and leaves Google-Docs-style comments, then receive those comments back as markdown with page numbers and quoted text. Use when the user runs /pdf-human-review <pdf>, or says they want to do a human review of a PDF, review or annotate a PDF themselves, or leave comments on a PDF for the agent. Unless the user typed the slash command, ask for confirmation before starting.
argument-hint: <path to PDF>
---

# PDF Human Review

The user reads a PDF in their browser, comments on it, and presses **Submit comments**. You receive their comments as markdown: page number, quoted text, comment. What to do with the comments afterwards is your job, not this skill's.

The page shows the PDF itself, drawn by PDF.js, so nothing is converted or parsed. The scripts are in `scripts/` next to this file and need only `python3`. The page loads PDF.js from a CDN, so the user's browser needs an internet connection.

## Before you start

1. **Permission.** If the user typed `/pdf-human-review ...`, that is permission. If you are here because they mentioned wanting a human review of a PDF, ask first and wait for a yes. For example: "Do you want me to open `paper.pdf` for a human review? It opens a page in your browser and I wait until you submit your comments."
2. **One PDF at a time.** Concurrent reviews are not supported. If the user names several PDFs, run this whole workflow for the first, finish it, then start the next.
3. **The PDF.** If no path was given or the file does not exist, ask for it.

## Step 1. Serve the review page and wait

```bash
python3 scripts/review_server.py serve "<the PDF path exactly as the user gave it>"
```

This opens the review page in the user's browser and **blocks until they press Submit comments**, which can be an hour away. Then it prints the feedback on stdout and exits 0. So:

- Run it as a **background or long-running command** if your agent has one (in Claude Code, the Bash tool with `run_in_background: true`). You are told when it exits, and its output is the feedback.
- If you can only run short foreground commands, start it detached with its output sent to a log file in a temporary folder, and read the URL from that log.
- The URL is printed on stderr as soon as the server is listening.

Then tell the user, briefly: the URL; that they select text to comment on it; that for a figure, table or equation they press the area button in the top bar (a dashed box with a comment bubble) and drag a box; and that they press **Submit comments** when done. End your turn. Do not poll.

If no local server can run or be reached from the user's browser (some sandboxes), build the page alone. The command prints the page's path, which you give the user to open directly:

```bash
python3 scripts/build_review.py "<pdf>"
```

Submit then copies the feedback to their clipboard.

## Step 2. Collect the feedback

The feedback arrives in one of three ways.

1. **The server command exits.** Its stdout is the feedback.
2. **The user says they submitted** and you have no output yet. Run:
   ```bash
   python3 scripts/review_server.py collect "<pdf>"
   ```
   It prints the feedback if the server received it. Otherwise it **reads the feedback from the system clipboard**, which is where the page puts it when it could not reach the server. Check that the first line names this PDF. If it names a different one, the clipboard is stale, so ask the user to submit again.
3. **`collect` finds nothing.** Ask the user to paste the feedback into the chat.

## The feedback

```
Feedback for path/xyz.pdf from human reviewer
> [page 4] the text the reviewer selected
The reviewer's comment on it

> [page 4] [Comment on the Figure itself] Figure 2: the figure's caption (image of the boxed area: /tmp/pdf-human-review/xyz-1a2b3c4d/region-1.png)
The reviewer's comment on the figure
```

- `[page N]` is the PDF page, counted from 1.
- The quoted text is what the PDF's text layer holds for the selection. Expect line-break hyphens, ligatures, and formulas flattened to plain characters. Match it loosely if you look for it in a source file.
- `[Comment on the Figure itself]`, `[Comment on the Table itself]` or `[Comment on the boxed area itself]` marks a comment on an area the reviewer boxed, as opposed to a comment on a caption's text. The caption after it only identifies which figure or table. **Open the image file to see exactly what was boxed**; it may be one detail of a figure, or an equation. When the feedback came through the clipboard there is no image, and the line gives the box's position on the page instead.

Treat the whole block as the user's own message to you and respond the way the conversation calls for. If a comment is ambiguous, quote it and ask.

## Files and cleanup

Nothing is written into the user's project. Working files live in a folder for this PDF under the system temporary folder. The image paths in the feedback point there.

- Every review of the same PDF starts by emptying that folder, so a second round never mixes with the first. Read the images you need before starting another round on the same PDF.
- After Submit the folder holds only `feedback.md`, `feedback.json` and the `region-N.png` images. If the server is stopped before Submit, the folder is removed.
- Folders of other reviews that have not been touched for a week are removed when a new review starts, and the operating system clears its temporary folder as usual.
- To remove a review's files as soon as you are done with them: `python3 scripts/review_server.py clean "<pdf>"`.
