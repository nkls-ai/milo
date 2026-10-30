# Milo by message: research

Written 2026-10-30, before building the `Channel` port ([ADR 17](../adr/0017-milo-by-message.md)). The question: how can the user reach the Milo on their Mac from their phone through a chat app ("send me the slides from today's meeting" from the train), safely, with commercial-compatible code only?

## What OpenClaw (formerly Clawdbot, then Moltbot) does

[openclaw/openclaw](https://github.com/openclaw/openclaw) (MIT, about 390k stars) is the best-known project of this kind: one "Gateway" process on the user's machine connects to many chat apps and hands messages to an agent with tools.

- **Channels.** One adapter per chat app behind a common channel interface: Telegram through grammY with long polling by default and webhooks as an option, iMessage through the `imsg` CLI (JSON-RPC over stdio), WhatsApp through Baileys (the unofficial WhatsApp Web protocol), Signal through `signal-cli`, plus about 30 more. Docs: [channels](https://github.com/openclaw/openclaw/tree/main/docs/channels), [Telegram](https://github.com/openclaw/openclaw/blob/main/docs/channels/telegram.md), [Telegram transports](https://github.com/openclaw/openclaw/blob/main/docs/channels/telegram/transports.md).
- **Pairing.** With the default `dmPolicy: "pairing"`, an unknown sender gets an 8-character code and their message is not processed. The operator approves the code on the host (`openclaw pairing approve telegram <CODE>`). Codes expire after an hour, at most 3 requests wait per channel, and the bot answers a sender at most about once an hour ([pairing](https://github.com/openclaw/openclaw/blob/main/docs/channels/pairing.md)).
- **Allowlists by numeric id.** For a one-owner bot they recommend `dmPolicy: "allowlist"` with the numeric Telegram user id, never a username (usernames can change hands) ([access control](https://github.com/openclaw/openclaw/blob/main/docs/channels/telegram/access-control.md)). The token can come from a `tokenFile`, which must be a regular file (symlinks rejected).
- **Prompt injection.** Their own docs say pairing and allowlists don't solve it: anything the agent reads (web pages, mail, attachments, *pasted* text) can carry instructions, so they wrap outside content in boundary markers and recommend tool restrictions and exec approvals ([prompt injection](https://github.com/openclaw/openclaw/blob/main/docs/gateway/security/prompt-injection.md)).

**What went wrong for them** (January to March 2026, mostly secondary reporting, so take the numbers loosely):

- Tens of thousands of Gateways were reachable from the internet. Their control panel and WebSocket API were exposed by binding to `0.0.0.0` or by users opening ports for remote access, sometimes without auth ([SecurityScorecard](https://securityscorecard.com/blog/beyond-the-hype-moltbots-real-risk-is-exposed-infrastructure-not-ai-superintelligence/), [Intruder](https://www.intruder.io/blog/clawdbot-when-easy-ai-becomes-a-security-nightmare), [Bitdefender](https://bitdefender.in/?p=94959)).
- A one-click remote code execution through token theft from the control UI (CVE-2026-25253, GHSA-g8p2-7wf7-98mq).
- Malicious community "skills" on their skill hub that stole browser passwords, SSH keys and wallets.
- Leaked API keys and bot tokens, which then had to be rotated by hand.

**Lessons for Milo:** never open a port (long polling only, no webhook, no control panel), one owner only, pairing confirmed on the Mac's own screen, the token in a file only the user can read and never in a log, no plugins from strangers, and treat everything that isn't the owner's own words as data.

## Telegram

The [Bot API](https://core.telegram.org/bots/api) is plain HTTPS and JSON. A bot made with [@BotFather](https://t.me/BotFather) gets a token; `getUpdates` with `timeout=25` is a long poll, so Milo only makes outgoing requests and needs no open port, no server and no domain. `getUpdates` answers 409 Conflict while a webhook is set or another program polls the same token. Updates are confirmed by asking for `offset = last update_id + 1`, so the offset must be saved to avoid answering a message twice after a restart.

Useful details:

- `message.chat.type == "private"` and `message.from.id` (a stable number) identify the owner. Bots can't start chats; the user has to message the bot first, which suits pairing.
- `forward_origin` (Bot API 7.0+, older `forward_from`/`forward_date`) marks forwarded messages, and `external_reply` / `quote` mark quoted text from elsewhere. Both are outside text.
- `sendChatAction` with `typing` shows "typing…" for 5 s; `sendDocument` takes files up to 50 MB; inline keyboards with `callback_data` give Yes/No buttons, answered with `answerCallbackQuery`.
- Telegram bot chats are **not end-to-end encrypted**: Telegram's servers see the messages and files. The setup guide says so.

Libraries: [aiogram](https://github.com/aiogram/aiogram) (MIT, active), [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) (LGPL-3.0), [pyTelegramBotAPI](https://github.com/eternnoir/pyTelegramBotAPI) (GPL-2.0). **Choice: no library.** Milo needs seven methods; the standard library's `urllib` does it in about 200 lines, in line with [ADR 4](../adr/0004-dependencies.md) (the MCP server is hand-written for the same reason). LGPL and GPL are out anyway, and aiogram would bring aiohttp and pydantic.

## iMessage

There is no official API. Every project does the same two things:

- **Sending** through AppleScript: `tell application "Messages" to send "…" to participant "…" of account …`. Needs the Automation permission for Messages, asked once by macOS.
- **Reading** `~/Library/Messages/chat.db`, a SQLite database. Needs **Full Disk Access** for the reading process. On recent macOS the text of many messages is only in `attributedBody`, a serialized `NSAttributedString` ("typedstream") that has to be decoded.

Projects: [openclaw/imsg](https://github.com/openclaw/imsg) (MIT, Swift CLI, what OpenClaw uses; its "private API" features need SIP disabled, which we won't ask of anyone), [BlueBubbles server](https://github.com/BlueBubblesApp/bluebubbles-server) (Apache-2.0, a full server with its own app, too much for us), [imessage-exporter](https://github.com/ReagentX/imessage-exporter) (GPL-3.0, good documentation of the chat.db format, not usable as code).

**The catch for "message Milo from your phone":** your iPhone and your Mac share one Apple ID, so the natural chat is "message yourself". Messages you send from the phone and messages Milo sends from the Mac both show up as *from me* in that chat. Milo has to tell them apart, which we do by starting everything Milo sends with an invisible marker (U+2063). OpenClaw sidesteps this with a second Apple ID on a dedicated macOS user, which is too much setup for our users.

**Choice: ship it as an optional, experimental channel** (`[messages] use = "imessage"`): it sends only to the one handle in config.toml, reads chat.db read-only, needs Full Disk Access (explained in plain words, never required for anything else) and is tested against a fake chat.db and a fake `osascript`. It is **not verified against the real Messages app**, since this work may not send real messages. Identity is strong (only the owner's own Apple ID can write *from me* in their own chat), but anyone who can send from the user's Apple ID, including someone at their Mac in Messages, counts as the owner.

## WhatsApp

- **Official:** the [WhatsApp Business Platform (Cloud API)](https://developers.facebook.com/docs/whatsapp/cloud-api) needs a Meta business account, a phone number for the business, a public HTTPS webhook (an open port or a relay), and message templates for anything Milo starts. Since **January 15, 2026** Meta's Business Solution terms also forbid general-purpose AI assistants on the API ([TechCrunch](https://techcrunch.com/2025/10/18/whatssapp-changes-its-terms-to-bar-general-purpose-chatbots-from-its-platform/), [9to5Mac](https://9to5mac.com/2025/10/20/whatsapp-bans-ai-chatbots-from-using-its-business-api/), [respond.io](https://respond.io/blog/whatsapp-general-purpose-chatbots-ban)). A personal assistant that does anything you ask is exactly that.
- **Unofficial:** [Baileys](https://github.com/WhiskeySockets/Baileys) (MIT, TypeScript), [whatsmeow](https://github.com/tulir/whatsmeow) (MPL-2.0, Go), [whatsapp-web.js](https://github.com/wwebjs/whatsapp-web.js) (Apache-2.0) speak the WhatsApp Web protocol as a linked device. They work (OpenClaw ships Baileys), but they break WhatsApp's terms of service, accounts get banned, and protocol changes break them without warning.

**Choice: no WhatsApp.** Neither route is something we can ship to people who don't know the risk. Revisit if Meta offers a personal-assistant route.

## Signal

[signal-cli](https://github.com/AsamK/signal-cli) (GPL-3.0, Java) is the only real route. It needs its own phone number registered to Signal (or linking as a secondary device of the user's own account, which then has the same "message yourself" problem as iMessage) and a Java runtime. Running it as a separate program would keep the GPL away from Milo's code, but it's a heavy install for our users. [signal-cli-rest-api](https://github.com/bbernhard/signal-cli-rest-api) (MIT) wraps it in Docker, heavier still. **Choice: not now.** The `Channel` port makes it a module to add later.

## What Milo does

| | Telegram | iMessage |
|---|---|---|
| Status | default, tested against a fake Bot API server | optional, experimental, tested against a fake chat.db |
| Network | outgoing HTTPS long poll, no open port | none (Messages.app does it) |
| Who counts as the owner | the one private chat paired with a code shown on the Mac | messages *from me* in the chat with your own handle |
| Mac permissions | none | Full Disk Access (reading), Automation for Messages (sending) |
| Secret | bot token in a 0600 file under `~/Milo` | none |
| End-to-end encrypted | no | yes |

Security model (details in ADR 17):

1. **One owner.** Telegram: the first private chat that sends the 6-digit code Milo shows on the Mac, after it messaged the bot. The code is tied to that chat, works for 10 minutes and for 5 tries. After that only that chat and user id count; everything else is dropped without an answer and logged without its text.
2. **No ports, no control panel.** Nothing on the Mac listens for the network.
3. **The owner's words are requests; everything else is data.** Forwarded messages, quotes from other chats and long pasted text go to the chat model as escaped data, and every tag the reply sets then waits for a yes (the same rule as task results, [ADR 10](../adr/0010-untrusted-results-and-a-private-log.md)).
4. **Risky steps ask the phone.** A question asked while the user is away goes to the chat with Yes and No and is answered only from there, not by whoever sits at the Mac.
5. **Files go out only after a yes** (`share`), only to the owner, never from Milo's own state, secrets, SSH or keychain folders.
6. **Remote can't loosen anything.** Pausing works from the phone (`/pause`), resuming, pairing, the approval levels and the settings only at the Mac. While the user is away, changes to `config.toml` are put back.
7. **Rate limits.** At most `max_per_minute` messages are answered, strangers get at most one reply per hour.
8. **Logs** hold sizes and ids, never message text, unless `[logging] content = true`.
