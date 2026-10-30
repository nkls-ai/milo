# Message Milo from your phone

Write to Milo in Telegram, and Milo on your Mac does the work and answers there: "send me the slides from today's meeting", "what's on my calendar tomorrow?", "remind me to call Anna at 5". When something is risky, he asks you in the chat first.

Your Mac has to be on and Milo running. Nothing on your Mac is opened to the internet: Milo asks Telegram for new messages, Telegram never connects to your Mac.

## Telegram

1. **Make a bot.** In Telegram, open a chat with [@BotFather](https://t.me/BotFather), send `/newbot`, and pick a name and a username (it has to end in `bot`). BotFather answers with a token that looks like `123456789:AAE…`. Treat it like a password: whoever has it can read what Milo sends.
2. **Give Milo the token.** In Terminal:

   ```sh
   (umask 077 && pbpaste > ~/Milo/secrets/telegram-token)    # after copying the token
   ```

   The file is readable by you only (`chmod 600`); Milo refuses a token file that others on your Mac could read.
3. **Switch it on.** In `~/Milo/config.toml`, under `[messages]`, set `enabled = true`. A config from before this feature has no `[messages]` section: add these two lines at the end. Then restart the brain from Milo's menu bar item.

   ```toml
   [messages]
   enabled = true
   ```
4. **Send Milo the code.** Message your bot from your phone (`/start` or anything). Milo shows a 6-digit code on your Mac, in his bubble and the Milo window. Send that code to the bot. Done: only your chat can reach Milo now.

The menu bar item now shows "Telegram: connected" and two new items:

- **Pause messages from your phone**: Milo ignores your phone until you switch it off again. You can also send `/pause` from your phone, but only the Mac can switch it back on.
- **Disconnect phone…**: forget your chat. Connecting again needs a new code shown on the Mac.

## What to know

- **Questions come to your phone.** When nobody has used your Mac for 5 minutes (`away_after_min`), Milo asks you in the chat before anything risky, with Yes and No buttons, and only your phone can answer. No answer within 150 seconds means no.
- **Files only after your yes.** Milo never sends files from private places (keys, passwords, his own settings) and never files over 45 MB.
- **What you forward is not an order.** When you forward a message or paste a long text, Milo reads it, but anything he'd do because of it waits for your yes.
- **Your settings stay put.** While you're away, nobody can change Milo's settings through him: changes to `config.toml` are put back.
- **A morning brief**, if you like: `brief_at = "07:30"` sends today's calendar, reminders and helpers every morning. It costs nothing.
- **Telegram isn't end-to-end encrypted.** Telegram's servers see what you and Milo write and the files he sends. If that matters, use iMessage (below) or keep sensitive files off the chat.
- `/status` shows what Milo's helpers are doing, `/help` the commands.

## iMessage (experimental)

Milo can also use your own iMessage chat ("message yourself"). It needs more permissions and hasn't been tested with the real Messages app yet.

1. In `config.toml`: `use = "imessage"`, and under `[messages.imessage]` your own phone number or Apple ID email as `handle`.
2. Allow Milo in System Settings › Privacy & Security › **Full Disk Access**, so he can read your messages database. He only reads the chat with yourself.
3. Restart the brain. The first time Milo answers, macOS asks whether Milo may control Messages: allow it.
4. Message yourself from your phone and send back the code Milo shows, as with Telegram.

WhatsApp and Signal aren't supported: see [research/messaging.md](../research/messaging.md) for why.
