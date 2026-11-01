# Milo, for coding agents

This repo is Milo, a voice assistant for the Mac: a Swift app (`app/`) and a Python brain (`brain/`, run with `uv`). You'll be here for one of two jobs:

- **The user asked you to set Milo up on their Mac.** Follow [Set Milo up](#set-milo-up-on-this-mac) below, step by step.
- **You're changing the code.** Read [Working on the code](#working-on-the-code) at the end.

## Set Milo up on this Mac

The goal: `build/Milo.app` running, the brain connected, and the user knowing which switches only they can flip.

### Rules while you do it

- **Ask before you install anything system-wide** (Xcode Command Line Tools, uv, Homebrew packages). Say what it is and roughly how big. Installing into `brain/.venv` with `uv sync` needs no question.
- **Don't overwrite the user's Milo files.** If `~/Milo/` already exists, it's theirs: never replace `~/Milo/config.toml`, `~/Milo/AGENTS.md`, `~/Milo/persona.md` or anything in `~/Milo/memory/`. Edit single keys in `config.toml` only when the user agreed, and keep its comments.
- **Never handle secrets in the chat.** Logins happen in the user's own terminal or browser (`claude`, `codex login`). An API key goes alone in a file in `~/Milo/secrets/`, written by the user or by you from a file they point to, never echoed back.
- **You can't grant macOS permissions.** Microphone, Accessibility and Screen Recording are switches the user clicks. Tell them exactly what to click, then wait for them.
- **Check the disk first.** The models and Python packages need a few GB. If less than 8 GB is free, say so before you download anything.
- Report what you did and what's left in plain words at the end. If a step failed, show the error.

### The short way

`install.sh` at the top of the repo does steps 1 to 5 and the configuration in step 7. The logins open a browser and need the user at the terminal, so do them first, together:

1. Ask which subscription the user has: Claude (Pro or Max), ChatGPT (Plus or Pro), or both. Either CLI can provide talking and helpers; a ChatGPT-only setup can use Codex for both.
2. Have the user log in in their own terminal: `claude auth login` and/or `codex login` (install Claude Code with `curl -fsSL https://claude.ai/install.sh | bash`, Codex with `npm install -g @openai/codex` or the ChatGPT app, after asking). `claude auth status` and `codex login status` tell you when it worked.
3. Tell the user what `--yes` will do without asking (install the Command Line Tools and uv if missing, set "Press fn key to" to Do Nothing) and get their yes. Then run `./install.sh --yes` from the repo. It installs what's missing, downloads the models, picks Claude or Codex for the helpers from what's logged in, builds the app and starts it.
4. Go on with step 6 below.

If a step of the installer fails, its message says which; the steps below do the same by hand.

### 1. Check the Mac

```sh
uname -m                    # must be arm64 (Apple silicon)
sw_vers -productVersion     # must be 14 or later
df -h ~                     # want at least 8 GB free
```

If it's an Intel Mac or older than macOS 14, stop and tell the user Milo doesn't run there yet.

### 2. Check the tools

```sh
xcode-select -p && swift --version   # Swift for the app
uv --version                         # Python for the brain
```

- No Command Line Tools: `xcode-select --install` opens a macOS dialog. Ask the user to click Install and tell you when it's done (it takes a few minutes).
- No uv: `curl -LsSf https://astral.sh/uv/install.sh | sh`, after asking. It installs to `~/.local/bin/uv`, which is one of the places the app looks (also `/opt/homebrew/bin` and `/usr/local/bin`). Use uv for every Python step, never pip or conda.

### 3. Check the models Milo thinks with

Milo needs two things online, both through CLIs the user is logged in to:

| Part | Default | Check | If missing |
|---|---|---|---|
| Chat model (what he says) | Claude via `claude`, or Codex via `codex` | `claude --version` or `codex --version` | The user signs in through `claude auth login` or `codex login` in their own terminal |
| Helpers (real work) | Codex | `codex --version`, or `/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex` exists | The user runs `codex login`, or uses Claude Code for helpers too (step 7) |

Ask the user which they have. One Claude Code login is enough if helpers are switched to Claude in step 7. One Codex login is enough with `[chat] use = "codex_live"` and `[harness] use = "codex"`. Talking and helpers are independent choices; Settings offers the talking-provider selector and needs a brain restart after a change. For another provider (OpenAI, OpenRouter, a local Ollama or LM Studio), the chat model can be `openai_compat`; see `[chat.openai_compat]` in `brain/src/milo/workspace_template/config.toml`.

### 4. Install the brain

```sh
cd brain && uv sync --extra omnivoice --extra pocket
```

About 1.5 GB of packages. `pocket` is the voice (Kyutai's Pocket TTS on the CPU), `omnivoice` the slower cloned-voice fallback. The app always starts the brain with both extras, so install both.

Optional, to show it works before building: `uv run pytest -q` in `brain/`. If tests fail, show the user the failing names and carry on only if they say so.

### 5. Build and start the app

```sh
scripts/make-signing-identity.sh   # once per Mac: a self-signed "Milo Dev" identity in the login keychain
scripts/build-app.sh --open        # builds build/Milo.app, signs it and starts it
```

The signing identity keeps macOS permissions across rebuilds; without it they reset every build. macOS may ask for the login keychain password; that prompt is the user's.

The first start downloads Whisper (about 1.8 GB) and the voice models to `~/.cache/huggingface`, so the first answer takes a while. Milo creates `~/Milo/` from `brain/src/milo/workspace_template/` if it isn't there.

### 6. Hand over to the user

Tell the user, in this order:

1. **The setup window** that just opened: click each button and turn Milo on in the list that appears. Microphone, Accessibility and Screen Recording are needed; Calendars, Reminders, Mail and Notes are optional. If Milo shows as on but gets no tick, press *Fix it*. Screen Recording wants a restart of Milo, which the window offers.
2. **System Settings › Keyboard › "Press 🌐 key to" › Do Nothing**, so the fn key belongs to Milo.
3. **Quit Wispr Flow** or any other dictation app using fn.
4. Then try it: hold **fn** and speak to dictate into any app; hold **right ⌥** and talk to Milo.

### 7. Configure, if needed

After the first start, `~/Milo/config.toml` exists. Change only what the user asked for:

- Helpers through Claude Code instead of Codex: `[harness] use = "claude"`.
- Talking through Codex CLI: `[chat] use = "codex_live"`; the user signs in with `codex login`. An empty `[chat.codex_live] model` uses the CLI's model selection.
- Talking through Claude CLI: `[chat] use = "claude_live"`.
- Dictation without a talking model: `[chat] use = "none"`.
- Another chat model: `[chat] use = "openai_compat"` and uncomment `[chat.openai_compat]`; the key goes in `~/Milo/secrets/<key_ref>`.
- Another voice: `[tts] use = "omnivoice"`, `"elevenlabs"` (key in `~/Milo/secrets/elevenlabs.key`) or `"say"`.

Then restart the brain: menu bar item › Restart brain.

### 8. Check that it runs

```sh
ls ~/Milo/run/brain.sock                      # the brain is up
tail -n 40 ~/Milo/logs/brain.log              # no errors at the end
scripts/drive-milo.py "hi" --wait 15          # a typed turn; prints what Milo says
```

`drive-milo.py` talks to the real running Milo. Use a harmless message like "hi"; never one that sends, deletes or buys.

### When something goes wrong

| Symptom | Likely cause | Fix |
|---|---|---|
| Milo appears but never answers | brain not running, or `uv` not found by the app | check `~/Milo/logs/brain.stdout.log`; install uv to `~/.local/bin`; or run `cd brain && uv run --extra omnivoice --extra pocket milo` in a terminal and the app joins it |
| fn does nothing | macOS still uses fn for emoji or dictation | step 6.2, and quit other dictation apps |
| Permissions gone after a rebuild | ad-hoc signature | run `scripts/make-signing-identity.sh`, rebuild, add Milo once more in Privacy & Security |
| He answers but helpers fail | Codex not logged in | `codex login`, or `[harness] use = "claude"` |
| First answer very slow | models still downloading | wait; `~/.cache/huggingface` grows while it downloads |

## Working on the code

- Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) first, and [ADR 34](docs/adr/0034-one-place-for-each-thing.md) for where new code goes: lines Milo says in `brain/src/milo/core/words`, times in `core/times.py`, tag rules in `services/tag_policy.py`.
- The brain core stays platform-neutral: OS-specific code lives in adapters ([ADR 27](docs/adr/0027-a-platform-boundary.md)).
- The wire protocol is `protocol/messages.json`; both test suites decode it.
- Python through `uv` only (`uv run`, `uv add`), never pip.
- Tests: `cd brain && uv run pytest -q` and `cd app && swift test`.
- Check a change on the real app with `scripts/drive-milo.py` before calling it done.
- Other agents may be editing this repo at the same time: look at `git status` before you start and don't revert changes you didn't make.
- The homepage is `site/` (Astro on Bun); see [site/README.md](site/README.md).
