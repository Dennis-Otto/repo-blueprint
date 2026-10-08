# A copy of the blueprint in the terminal, as the documentation shows it: VHS types
# the command and the answers, and records the terminal into a GIF.
# scripts/docs-pictures.sh plays it in the image of the Dockerfile next to it.
# The commands of a tape: https://github.com/charmbracelet/vhs

Output docs/images/copier-copy.gif

# 121 columns, so that the longest question of Copier fits on one line.
Set Shell bash
Set FontFamily "JetBrains Mono"
Set FontSize 18
Set LetterSpacing 0
Set LineHeight 1.2
Set Width 1320
Set Height 720
Set Padding 20
Set Margin 20
Set MarginFill "#0a0f1d"
Set WindowBar Colorful
Set BorderRadius 12
Set Framerate 15
Set TypingSpeed 40ms
Set CursorBlink false
# The dark navy and the colors of the social preview, .github/social-preview.html.
Set Theme { "name": "Repo Blueprint", "background": "#141a26", "foreground": "#e2e8f0", "cursor": "#60a5fa", "cursorAccent": "#141a26", "selection": "#1e293b", "black": "#1e293b", "brightBlack": "#8b95a7", "red": "#f87171", "brightRed": "#fca5a5", "green": "#4ade80", "brightGreen": "#86efac", "yellow": "#fbbf24", "brightYellow": "#fde68a", "blue": "#60a5fa", "brightBlue": "#93c5fd", "magenta": "#c084fc", "brightMagenta": "#d8b4fe", "cyan": "#22d3ee", "brightCyan": "#67e8f9", "white": "#cbd5e1", "brightWhite": "#f8fafc" }

# An empty folder and a short prompt, out of sight.
Hide
Type `cd "$(mktemp -d)" && PS1='\[\e[34m\]$\[\e[0m\] ' && alias ls='ls --color=auto' && clear`
Enter
Sleep 500ms
Show

Type "copier copy gh:Dennis-Otto/repo-blueprint paperless-sync"
Sleep 500ms
Enter

# The answers: the name, the description and the kind of project, and the defaults
# for the rest. Each key waits for its question. Wait+Screen reads only the first
# screen of output, so the last questions wait for the line of the cursor instead,
# or for a moment where that line stays empty.
Wait+Screen@60s /The name of the project/
Sleep 500ms
Type "Paperless Sync"
Sleep 300ms
Enter
Wait+Screen /The name of the repository/
Sleep 800ms
Enter
Wait+Screen /One sentence/
Sleep 300ms
Type "Syncs the documents of Paperless-ngx to a folder."
Sleep 300ms
Enter
Wait+Screen /The kind of project/
Wait+Screen /Use arrow keys/
Sleep 800ms
Down@400ms 3
Sleep 600ms
Enter
Wait+Screen /GitHub account or organization/
Sleep 500ms
Enter
Wait+Screen /The maintainer/
Sleep 500ms
Enter
Wait+Screen /The copyright of the license/
Sleep 500ms
Enter
Wait+Screen /The license/
Wait+Screen /Use arrow keys/
Sleep 500ms
Enter
Wait+Screen /Python package or module/
Sleep 500ms
Enter
Wait+Screen /The languages of the code/
Wait+Screen /to invert/
Sleep 500ms
Enter
Wait+Screen /GitHub Discussions/
Wait /\(Y.n\)$/
Sleep 500ms
Enter
Wait /\(y.N\)$/
Sleep 500ms
Enter
Sleep 700ms
Enter
Sleep 700ms
Enter
Wait /Dennis-Otto$/
Sleep 500ms
Enter
Wait /\(Y.n\)$/
Sleep 500ms
Enter

# Copier writes the files and says what comes next, and the prompt comes back.
Wait@60s /^\$$/
Sleep 4s

Type "ls -A paperless-sync"
Sleep 300ms
Enter
Sleep 3s
Type "ls paperless-sync/.github/workflows"
Sleep 300ms
Enter
Sleep 4s
