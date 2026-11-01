#!/bin/sh
# Milo's installer: everything local in one go, then the subscription Milo thinks with.
#
#   curl -fsSL https://nkls-ai.github.io/milo/install.sh | sh
#
# or, from a checkout, ./install.sh. Run it again to update.
#
# What it does on a Mac: checks the Mac, installs Apple's Command Line Tools and uv if they're missing (asking
# first), gets Milo's source, installs the brain, downloads the speech models (hearing, voice, memory), asks which
# subscription to connect (Claude, ChatGPT or both) and logs in, builds the app and starts it.
# For Windows/Linux, use the shared desktop distribution or scripts/start-desktop.* from a checkout.
#
# Options:
#   --yes       ask nothing: install what's missing, connect only what's already logged in
#   --no-app    the brain and the models only, no app (for a machine that runs a brain without the Mac app)
#   --help
# Settings, as environment variables:
#   MILO_REPO   where the source comes from      (default https://github.com/nkls-ai/milo.git)
#   MILO_REF    the branch or tag                (default main)
#   MILO_SRC    where the source goes            (default ~/.milo/src; a checkout you run this from is used as is)
#   MILO_HOME   Milo's workspace                 (default ~/Milo)

# Everything is in functions and main runs on the last line, so a download cut off halfway runs nothing.

set -eu

MILO_REPO=${MILO_REPO:-https://github.com/nkls-ai/milo.git}
MILO_REF=${MILO_REF:-main}
MILO_SRC=${MILO_SRC:-$HOME/.milo/src}
MIN_FREE_GB=8
CODEX_IN_CHATGPT=/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex
BUNDLE_ID=dev.nkls.milo

YES=0
NO_APP=0
SRC=""
FROM_CHECKOUT=0
UV=""
CLAUDE=""
CODEX=""

# ---------------------------------------------------------------- talking to the person installing

if [ -t 1 ]; then
  BOLD=$(printf '\033[1m'); DIM=$(printf '\033[2m'); PURPLE=$(printf '\033[38;5;98m'); GREEN=$(printf '\033[32m')
  YELLOW=$(printf '\033[33m'); RED=$(printf '\033[31m'); RESET=$(printf '\033[0m')
else
  BOLD=""; DIM=""; PURPLE=""; GREEN=""; YELLOW=""; RED=""; RESET=""
fi

step() { printf '\n%s==>%s %s%s%s\n' "$PURPLE" "$RESET" "$BOLD" "$*" "$RESET"; }
say() { printf '    %s\n' "$*"; }
ok() { printf '    %s✓%s %s\n' "$GREEN" "$RESET" "$*"; }
warn() { printf '    %s!%s %s\n' "$YELLOW" "$RESET" "$*"; }
die() { printf '\n%sMilo could not be installed:%s %s\n' "$RED" "$RESET" "$*" >&2; exit 1; }

# Questions read the terminal, not stdin: under `curl | sh` stdin is this script.
has_tty() { [ "$YES" = 0 ] && ( : </dev/tty ) 2>/dev/null; }

# ask "question" default -> the answer in $REPLY
ask() {
  REPLY=$2
  has_tty || return 0
  printf '    %s%s%s [%s] ' "$BOLD" "$1" "$RESET" "$2"
  read -r REPLY </dev/tty || REPLY=$2
  [ -n "$REPLY" ] || REPLY=$2
}

# confirm "question" -> true for yes (the default)
confirm() {
  ask "$1 (Y/n)" "y"
  case $REPLY in [Nn]*) return 1 ;; *) return 0 ;; esac
}

usage() { sed -n '2,22p' "$0" 2>/dev/null | sed 's/^# \{0,1\}//'; exit 0; }

# ---------------------------------------------------------------- the platform

detect_platform() {
  os=$(uname -s)
  arch=$(uname -m)
  case $os in
    Darwin) echo "macos-$arch" ;;
    Linux) echo "linux-$arch" ;;
    MINGW* | MSYS* | CYGWIN*) echo "windows-$arch" ;;
    *) echo "unknown-$os" ;;
  esac
}

not_yet() {
  printf '\n%sMilo runs on Macs with Apple silicon for now.%s\n' "$BOLD" "$RESET"
  say "$1 needs its own local hearing and voice first; the brain is ready for them"
  say "(see brain/src/milo/adapters/platform.py). Nothing was installed."
  exit 1
}

# ---------------------------------------------------------------- Mac checks

check_mac() {
  step "Checking this Mac"
  version=$(sw_vers -productVersion)
  major=${version%%.*}
  [ "$major" -ge 14 ] || die "Milo needs macOS 14 Sonoma or later; this Mac has $version."
  ok "macOS $version on Apple silicon"
  free_gb=$(df -g "$HOME" | awk 'NR==2 {print $4}')
  if [ "$free_gb" -lt "$MIN_FREE_GB" ]; then
    die "Milo needs about $MIN_FREE_GB GB free for his speech models; this Mac has $free_gb GB. Free some space and run this again."
  fi
  ok "$free_gb GB free"
}

ensure_command_line_tools() {
  if xcode-select -p >/dev/null 2>&1 && /usr/bin/xcrun --find swift >/dev/null 2>&1; then
    ok "Apple's Command Line Tools"
    return
  fi
  say "Milo's app is built with Apple's Command Line Tools (Swift and git, about 2 GB)."
  confirm "Install them now?" || die "the Command Line Tools are needed. Run: xcode-select --install"
  xcode-select --install >/dev/null 2>&1 || true
  say "A macOS window just opened: click ${BOLD}Install${RESET} and agree. Waiting for it to finish…"
  waited=0
  until xcode-select -p >/dev/null 2>&1 && /usr/bin/xcrun --find swift >/dev/null 2>&1; do
    sleep 10
    waited=$((waited + 10))
    [ "$waited" -lt 3600 ] || die "the Command Line Tools didn't finish within an hour. Run this again once they have."
  done
  ok "Apple's Command Line Tools"
}

ensure_uv() {
  for candidate in "$(command -v uv 2>/dev/null || true)" "$HOME/.local/bin/uv" /opt/homebrew/bin/uv /usr/local/bin/uv; do
    if [ -n "$candidate" ] && [ -x "$candidate" ]; then UV=$candidate; ok "uv $("$UV" --version | cut -d' ' -f2)"; return; fi
  done
  say "Milo's brain runs on Python through uv (a small tool, about 40 MB, in ~/.local/bin)."
  confirm "Install uv now?" || die "uv is needed: https://docs.astral.sh/uv/"
  curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null
  UV="$HOME/.local/bin/uv"
  [ -x "$UV" ] || die "uv didn't install. Try: curl -LsSf https://astral.sh/uv/install.sh | sh"
  ok "uv $("$UV" --version | cut -d' ' -f2)"
}

# ---------------------------------------------------------------- the source and the brain

fetch_source() {
  step "Getting Milo"
  # Run from a checkout (./install.sh): use it as it is.
  here=$(cd "$(dirname "$0")" 2>/dev/null && pwd || true)
  if [ -n "$here" ] && [ -f "$here/brain/pyproject.toml" ] && [ -f "$here/app/Package.swift" ]; then
    SRC=$here
    FROM_CHECKOUT=1
    ok "using this checkout: $SRC"
    return
  fi
  SRC=$MILO_SRC
  if [ -d "$SRC/.git" ]; then
    if [ -n "$(git -C "$SRC" status --porcelain)" ]; then
      warn "$SRC has local changes, so it stays as it is"
    else
      git -C "$SRC" fetch --quiet --depth 1 origin "$MILO_REF"
      git -C "$SRC" checkout --quiet -B "$MILO_REF" FETCH_HEAD
      ok "updated $SRC to the newest $MILO_REF"
    fi
  else
    mkdir -p "$(dirname "$SRC")"
    git clone --quiet --depth 1 --branch "$MILO_REF" "$MILO_REPO" "$SRC" \
      || die "couldn't download Milo from $MILO_REPO"
    ok "downloaded to $SRC"
  fi
}

install_brain() {
  step "Installing Milo's brain"
  say "Python and the speech libraries, about 1.5 GB the first time."
  "$UV" sync --quiet --project "$SRC/brain" --extra omnivoice --extra pocket || die "the brain's packages didn't install"
  ok "brain installed"
}

milo_py() { "$UV" run --quiet --project "$SRC/brain" --extra omnivoice --extra pocket python -m milo.install "$@"; }

download_models() {
  step "Downloading his ears, voice and memory"
  say "Whisper hears you, Pocket TTS is his voice, e5 finds his memories. All three run on this Mac,"
  say "so your recordings never leave it. About 2 GB, once."
  if milo_py models; then
    ok "hearing, voice and memory ready"
  else
    warn "a model didn't load; Milo tries again when he starts. Details above."
  fi
}

# ---------------------------------------------------------------- the subscriptions Milo thinks with

find_claude() {
  for candidate in "$(command -v claude 2>/dev/null || true)" "$HOME/.local/bin/claude" "$HOME/.claude/local/claude"; do
    if [ -n "$candidate" ] && [ -x "$candidate" ]; then CLAUDE=$candidate; return 0; fi
  done
  CLAUDE=""
  return 1
}

find_codex() {
  for candidate in "$(command -v codex 2>/dev/null || true)" "$CODEX_IN_CHATGPT"; do
    if [ -n "$candidate" ] && [ -x "$candidate" ]; then CODEX=$candidate; return 0; fi
  done
  CODEX=""
  return 1
}

claude_logged_in() { [ -n "$CLAUDE" ] && "$CLAUDE" auth status --json 2>/dev/null | grep -q '"loggedIn": *true'; }
codex_logged_in() { [ -n "$CODEX" ] && "$CODEX" login status 2>&1 | grep -qi '^logged in'; }  # it prints to stderr

connect_claude() {
  if ! find_claude; then
    confirm "Install Claude Code (Anthropic's app for your Claude subscription)?" || return 1
    curl -fsSL https://claude.ai/install.sh | bash || { warn "Claude Code didn't install"; return 1; }
    find_claude || { warn "Claude Code installed, but isn't on PATH yet. Open a new terminal and run this again."; return 1; }
  fi
  if ! claude_logged_in; then
    has_tty || { warn "Claude isn't logged in. Run: claude auth login"; return 1; }
    say "Your browser opens to log in to Claude. Come back here when it says you're done."
    "$CLAUDE" auth login </dev/tty || true
  fi
  if claude_logged_in; then ok "Claude connected"; else warn "Claude isn't logged in. Run: claude auth login"; return 1; fi
}

connect_codex() {
  if ! find_codex; then
    if command -v npm >/dev/null 2>&1 && confirm "Install Codex (OpenAI's app for your ChatGPT subscription) with npm?"; then
      npm install -g @openai/codex >/dev/null 2>&1 || warn "npm couldn't install Codex"
    elif command -v brew >/dev/null 2>&1 && confirm "Install Codex (OpenAI's app for your ChatGPT subscription) with Homebrew?"; then
      brew install --cask codex >/dev/null 2>&1 || warn "Homebrew couldn't install Codex"
    fi
    find_codex || { warn "Codex isn't installed. Install the ChatGPT app for Mac, or: npm install -g @openai/codex"; return 1; }
  fi
  if ! codex_logged_in; then
    has_tty || { warn "Codex isn't logged in. Run: codex login"; return 1; }
    say "Your browser opens to log in with ChatGPT. Come back here when it says you're done."
    "$CODEX" login </dev/tty || true
  fi
  if codex_logged_in; then ok "ChatGPT connected"; else warn "ChatGPT isn't logged in. Run: codex login"; return 1; fi
}

connect_accounts() {
  step "Connecting your subscription"
  say "Hearing and voice run on this Mac. For thinking, Milo uses a subscription you already have:"
  say "Claude or ChatGPT can do both the talking and bigger jobs, through the CLI you sign in to."
  find_claude || true
  find_codex || true
  has_claude=0; has_codex=0
  claude_logged_in && has_claude=1 && ok "Claude: logged in"
  codex_logged_in && has_codex=1 && ok "ChatGPT: logged in"

  if [ "$has_claude" = 0 ] || [ "$has_codex" = 0 ]; then
    default=1
    [ "$has_codex" = 1 ] && default=3
    [ "$has_claude" = 1 ] && default=1
    if has_tty; then
      printf '\n'
      say "${BOLD}Which do you have?${RESET}"
      say "  1) Claude (Pro or Max)     he talks and works with it"
      say "  2) ChatGPT (Plus or Pro)   he talks and works with Codex CLI"
      say "  3) Both                    Claude talks, ChatGPT works (recommended if you have both)"
      say "  4) Neither, or later       dictation and his voice work without one"
      ask "1, 2, 3 or 4?" "$default"
      choice=$REPLY
    else
      choice=0  # --yes: only what's already logged in
    fi
    case $choice in
      1) [ "$has_claude" = 1 ] || { connect_claude && has_claude=1; } || true ;;
      2) [ "$has_codex" = 1 ] || { connect_codex && has_codex=1; } || true ;;
      3) [ "$has_claude" = 1 ] || { connect_claude && has_claude=1; } || true
         [ "$has_codex" = 1 ] || { connect_codex && has_codex=1; } || true ;;
      *) ;;
    esac
  fi

  # Prefer Claude talking when both are connected; either CLI works alone.
  chat=none; harness=none
  if [ "$has_codex" = 1 ]; then chat=codex_live; harness=codex; fi
  if [ "$has_claude" = 1 ]; then
    chat=claude_live
    [ "$has_codex" = 1 ] || harness=claude
  fi
  milo_py configure --chat "$chat" --harness "$harness" >/dev/null || warn "couldn't write ~/Milo/config.toml"
  if [ "$has_claude" = 1 ] && [ "$has_codex" = 1 ]; then
    ok "Milo talks with Claude and does bigger jobs with ChatGPT"
  elif [ "$has_claude" = 1 ]; then
    ok "Milo talks and works with Claude"
  elif [ "$has_codex" = 1 ]; then
    ok "Milo talks and works with ChatGPT through Codex CLI"
  else
    warn "No subscription connected yet. Dictation and his voice work; run this again to connect one."
  fi
}

# ---------------------------------------------------------------- the app

quit_milo() {
  pgrep -xq Milo 2>/dev/null || return 0
  osascript -e "tell application id \"$BUNDLE_ID\" to quit" >/dev/null 2>&1 || true
  sleep 1
}

install_app() {
  step "Building the app"
  say "About a minute. macOS may ask for your login password once, to keep Milo's permissions across updates."
  sh "$SRC/scripts/make-signing-identity.sh" >/dev/null || warn "no signing identity: macOS will ask for permissions again after each update"
  sh "$SRC/scripts/build-app.sh" >/dev/null || die "the app didn't build. Run: sh $SRC/scripts/build-app.sh"
  APP="$SRC/build/Milo.app"
  if [ "$FROM_CHECKOUT" = 0 ]; then
    dest=/Applications
    [ -w "$dest" ] || { dest="$HOME/Applications"; mkdir -p "$dest"; }
    if [ -d "$dest/Milo.app" ] && [ "$(defaults read "$dest/Milo.app/Contents/Info" CFBundleIdentifier 2>/dev/null)" != "$BUNDLE_ID" ]; then
      die "$dest/Milo.app is another app with the same name. Move it, then run this again."
    fi
    quit_milo
    rm -rf "$dest/Milo.app"
    ditto "$APP" "$dest/Milo.app"
    APP="$dest/Milo.app"
  fi
  [ "$FROM_CHECKOUT" = 0 ] || quit_milo
  ok "Milo is in ${APP%/Milo.app}"

  # fn belongs to Milo only if macOS doesn't use it for emoji or dictation.
  if [ "$(defaults read com.apple.HIToolbox AppleFnUsageType 2>/dev/null || echo 1)" != 0 ]; then
    say "Milo uses the ${BOLD}fn${RESET} key for dictation, so macOS shouldn't open emoji or its own dictation with it."
    if confirm "Set \"Press fn key to\" to Do Nothing?"; then
      defaults write com.apple.HIToolbox AppleFnUsageType -int 0
      ok "fn is Milo's (if it still opens emoji, set it in System Settings › Keyboard)"
    fi
  fi
  if pgrep -xq "Wispr Flow" 2>/dev/null; then
    warn "Wispr Flow is running and wants fn too. Quit it before you dictate with Milo."
  fi
  open "$APP"
}

finish() {
  printf '\n%s%sMilo is installed.%s\n\n' "$BOLD" "$PURPLE" "$RESET"
  if [ "$NO_APP" = 0 ]; then
    say "A window opens to ask macOS for three permissions: ${BOLD}Microphone${RESET}, ${BOLD}Accessibility${RESET}"
    say "(keys and pasting) and ${BOLD}Screen Recording${RESET} (looking when you ask). One click each."
    printf '\n'
    say "Then:  hold ${BOLD}fn${RESET} and speak to dictate into any app"
    say "       hold ${BOLD}right ⌥${RESET} and talk to Milo"
  else
    say "Start the brain with: $UV run --project $SRC/brain --extra omnivoice --extra pocket milo"
  fi
  printf '\n'
  say "${DIM}Settings: menu bar › Milo › Settings…, or ~/Milo/config.toml. Run this again to update.${RESET}"
}

# ---------------------------------------------------------------- main

main() {
  for arg in "$@"; do
    case $arg in
      --yes | -y) YES=1 ;;
      --no-app) NO_APP=1 ;;
      --help | -h) usage ;;
      *) die "unknown option $arg (try --help)" ;;
    esac
  done
  printf '\n%s%s  Milo%s %s· a small coworker for your computer%s\n' "$BOLD" "$PURPLE" "$RESET" "$DIM" "$RESET"

  case $(detect_platform) in
    macos-arm64) ;;
    macos-*)
      # A terminal under Rosetta says x86_64 on an Apple silicon Mac.
      [ "$(sysctl -n hw.optional.arm64 2>/dev/null || echo 0)" = 1 ] || die "Milo needs a Mac with Apple silicon (M1 or newer)." ;;
    linux-*) not_yet "Linux" ;;
    windows-*) not_yet "Windows" ;;
    *) not_yet "This system" ;;
  esac

  check_mac
  ensure_command_line_tools
  ensure_uv
  fetch_source
  install_brain
  download_models
  connect_accounts
  [ "$NO_APP" = 1 ] || install_app
  finish
}

main "$@"
