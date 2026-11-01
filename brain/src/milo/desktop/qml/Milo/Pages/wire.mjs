// Commands the pages send, shaped exactly as protocol/messages.json's app_to_brain. One place, so a page can't
// drift from the wire.

// confirmation_answer in desktop/model.py: only a real button gets here, and a money question has no other way in.
export function confirmAnswer(question, choice) {
    const offered = (question.choices && question.choices.length ? question.choices
                     : [{ id: "yes" }, { id: "no" }].concat(question.always ? [{ id: "always" }] : [])).map(c => String(c.id))
    if (offered.indexOf(choice) < 0) throw new Error("That answer isn't offered by this question")
    return { type: "confirm_answer", id: String(question.id), yes: choice === "yes" || choice === "always",
             always: choice === "always", choice: choice }
}

export function stopHelper(id) { return { type: "stop_helper", id: id } }
export function undoTask(id) { return { type: "undo_task", id: id } }
export function routine(id, action) { return { type: "routine", id: id, action: action } }
export function draftAnswer(id, save) { return { type: "routine_draft_answer", id: id, save: save } }
export function setSetting(section, key, value) { return { type: "set_setting", section: section, key: key, value: value } }
export function text(text, conversation) {
    const message = { type: "text", text: text, speak: false }
    if (conversation) message.conversation = conversation
    return message
}
