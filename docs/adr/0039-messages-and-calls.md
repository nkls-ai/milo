# 39. Text someone and call them, and always ask first

Date: 2026-11-01. Status: accepted. Builds on [ADR 29](0029-quick-actions-from-the-talker.md), [ADR 23](0023-stop-for-what-cant-be-undone.md), [ADR 25](0025-the-systems-permissions-before-milo-needs-them.md) and [ADR 27](0027-a-platform-boundary.md). Changes ADR 29's consequence "Messages (iMessage) can't be drafted": they can't, but now they can be sent, after a yes.

## Context

"Text Anna I'm late" and "call Mum" are among the most common things people say to a voice assistant. Milo had neither. A helper could only say that Messages has no draft to script, and nothing could start a call.

Both go to another person and nothing takes them back. ADR 23 already says sending asks in every mode. A message also needs a person: "Anna" is a name in the user's address book, "Mum" is whoever their own card names as their mother, and two Annas are a question, not a guess.

## Decision

**Two act tags.** `<message to="Anna">I'm running ten minutes late</message>` and `<call to="Mum"/>` (`video="yes"` for a video call, `facetime="yes"` for an internet audio call). They are quick actions like the others (ADR 29): `ReplyParser` collects them, `QuickActions` plans and runs them, and the model says nothing about them. The talker's rules separate `<message>` from `<write>` (ADR 33): "text Anna …" or "send it to Anna" is a message; "write Anna that …" is text pasted where the cursor is.

**Who it is** (`services/people.py`). A phone number or an address said outright is used as it is, without the address book. Otherwise the `Contacts` port finds everyone whose name, a word of it or their nickname starts like each word said, case and accents aside. Family words in English and German ("Mum", "Mama", "Mutti", "Papa", "my sister", "meine Frau") also send a relation ("mother"), and the app adds whom the user's own card names with it, or with the word itself as the label ("Mum"). The brain then picks: the relation, then the exact full name or nickname, then a first name that is the word said, then everyone found. The same name on two cards is one person. Different names left over are an `Answer`: "Which Anna: “Anna Berg” or “Anna Kim”?". Nobody is "I can't find Bob in your contacts.", and no number or address is a line too. The user's next words make the model write the tag again with the name they picked.

**Which number.** A mobile number first (the label says mobile, iPhone, cell or Handy). For a message or an internet call, then an email address, which iMessage and FaceTime reach. Then any other number. A phone call to someone with only an address becomes an internet audio call, and the question says so.

**Always asks** (`_Plan.always`). Every message and every call asks, every time, in every mode, at the Mac and from the phone, through `Approvals.confirm`: no Allow always, no scope, and a `send` or `call` level lowered in config.toml doesn't skip it. Only `never` for the kind refuses without a question. The question names the person, the number or address, and the whole text: "Send this to Anna Berg (+49 170 1234567)? “I'm running ten minutes late”", "Call Mum (Jane Doe, +49 160 2222222)?". A message is the `send` kind; a call is a new kind, `call` (`ask_first`), so `call = "never"` in `[approvals.levels]` turns calls off.

**No Undo.** The card (`action_done` kind `message` or `call`) says what went, to whom: the text or the number as its detail. It records no Undo, so the card has no Undo button and "undo that" doesn't reach it.

**Permissions** (ADR 25). Reading the address book is a new need, `contacts`, which the system asks about in a dialog once. Before the first look `AccessGate.need(Need.CONTACTS)` checks it: `ask` says "macOS will ask once whether I may look in your contacts. Please allow it." and lets the system ask; `no` shows the Fix it note and Milo says "I can't look in your contacts, so I don't know who Anna is. A number works." Fix it opens Privacy & Security › Contacts. The setup window lists Contacts as optional, with its own little scene. Sending goes through `AccessGate` for Messages (Automation), after the user's yes, like Notes and Mail. A call opens a link and needs no permission.

**The ports and the adapters.** `core/ports.py` has `Contacts.find(name, relation)`, `Messages.send(to, text)` and `Calls.call(to, how)`, and `Connections` has `contacts`, `messages` and `calls`. On the Mac:

- Contacts is in the app: `contacts.find` {name, relation?} on `ContactsRequests` over `SystemContactBook` (CNContactStore, with the user's own card from `unifiedMeContactWithKeys`). The brain reaches it on AppBridge (`AppContacts`, `in_brain`), like Calendar. CNContactStore was chosen over scripting Contacts.app: it doesn't start the app, it is one system question in the setup window's terms, and it reads the relations.
- `AppleMessages` scripts Messages: iMessage first, then the SMS account (Text Message Forwarding from an iPhone) when the iMessage send fails in the script.
- `FaceTimeCalls` opens `tel:` (a phone call through the iPhone, or FaceTime audio where that isn't set up), `facetime-audio://` or `facetime://` with `open`.

The fakes keep `contacts`, `messages_sent` and `calls` in world.json; nothing leaves and nothing rings. `[connections]` has `contacts`, `messages` and `calls` switches.

## Consequences

- "Text Anna I'm late" takes the talker's reply, one `contacts.find` (an enumeration of the address book, usually well under 0.5 s), the question and the user's yes. A helper isn't involved.
- Every message and every call costs a yes, even in auto mode. That is the point: the user asked for it in ADR 23, and a wrong number or a misheard text can't be taken back.
- The talker model never reads the address book: the brain looks up the name the model wrote.
- The family words are a short English and German list, and each maps to the address book's standard relation ("Mum", "Mom" and "Mama" are all "mother"). A label the user typed on their card ("Mutsch") is found only when they say that word. Other languages say the name.
- Not run on a real Mac, on purpose (no real message or call in tests): the CNContactStore reading, the Contacts permission dialog and the setup row, the Messages script and its SMS fallback, and the `tel:` and `facetime` links. The Swift compiles and `ContactsRequests` is tested with a fake book; the brain is tested on the fake connections.
- Messages' scripting can't tell beforehand whether a number has iMessage. A send to a number without it may fail only in Messages, later, with "Not Delivered", while Milo has already said "Sent to Anna." The SMS fallback only runs when the script itself fails.
- Opening `tel:` or `facetime://` from another app may make FaceTime show its own Call button before it rings, so a call can take one more click after Milo's yes.
- A contact found only through the relation needs a relation on the user's own card in Contacts ("mother: Jane Doe"), or a card with the nickname "Mum".
