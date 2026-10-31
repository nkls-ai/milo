// The card that springs out of Milo when he's done something (the app's DoneCardViews.swift): a small
// picture of the thing on the left, its title and when, a check that draws itself in, and Undo.
// One builder for both the page's server render and the demos' script, so the two can't drift apart.

export type Kind = 'event' | 'todo' | 'timer' | 'note' | 'reminder' | 'draft' | 'music' | 'opened';

export interface Done {
  kind: Kind;
  title: string;
  /** The line under the title: an event's time, where a to-do went, when a timer rings. */
  line: string;
  /** An event's calendar page: "Thu" and "5". */
  day?: [string, string];
  /** A timer's minutes left, shown in its ring. */
  left?: string;
  /** Whether the card has an Undo button. */
  undo?: boolean;
}

const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]!);

const symbols: Partial<Record<Kind, string>> = {
  reminder: '<path d="M12 3.6a5 5 0 0 0-5 5v3.1l-1.6 3.1a.8.8 0 0 0 .7 1.2h11.8a.8.8 0 0 0 .7-1.2L17 11.7V8.6a5 5 0 0 0-5-5Z"/><path d="M9.8 18.3a2.2 2.2 0 0 0 4.4 0Z"/>',
  draft: '<rect x="3.2" y="5.6" width="17.6" height="12.8" rx="2.2"/><path d="m4 7.2 8 5.6 8-5.6" fill="none" stroke="var(--dc-tile)" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>',
  music: '<path d="M9.2 17V6.6l9.6-2.1v10.3" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><circle cx="7" cy="17.2" r="2.6"/><circle cx="16.6" cy="15" r="2.6"/>',
  opened: '<g fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="8"/><path d="M4 12h16M12 4c2.4 2.3 3.5 5 3.5 8s-1.1 5.7-3.5 8c-2.4-2.3-3.5-5-3.5-8s1.1-5.7 3.5-8Z"/></g>',
};

function glyph(d: Done): string {
  switch (d.kind) {
    case 'event':
      return `<span class="dc-cal"><b>${esc(d.day?.[0] ?? '')}</b><span>${esc(d.day?.[1] ?? '')}</span></span>`;
    case 'todo':
      return '<span class="dc-tile dc-todo"><i></i><span><i></i><i></i></span></span>';
    case 'timer':
      return `<span class="dc-ring"><svg viewBox="0 0 36 36"><circle cx="18" cy="18" r="14" pathLength="1"/><circle class="dc-ring-run" cx="18" cy="18" r="14" pathLength="1"/></svg><span>${esc(d.left ?? '')}</span></span>`;
    case 'note':
      return '<span class="dc-note"><i></i><i></i><i></i></span>';
    default:
      return `<span class="dc-tile"><svg viewBox="0 0 24 24">${symbols[d.kind] ?? ''}</svg></span>`;
  }
}

const undoArrow = '<svg viewBox="0 0 24 24"><path d="M9.5 6.5 5.5 10.5l4 4"/><path d="M6 10.5h8.2a4.3 4.3 0 0 1 0 8.6H12"/></svg>';

/** The card's inner HTML. `buttons`: a real Undo button (in a demo), or a drawing of one (in a picture). */
export function cardHTML(d: Done, { buttons = false } = {}): string {
  const undo = !d.undo
    ? ''
    : buttons
      ? `<button type="button" class="dc-undo" data-undo aria-label="Undo “${esc(d.title)}”">${undoArrow}<span class="dc-spin" aria-hidden="true"></span></button>`
      : `<span class="dc-undo" aria-hidden="true">${undoArrow}</span>`;
  return (
    `<span class="dc-glyph" aria-hidden="true">${glyph(d)}</span>` +
    `<span class="dc-text"><b>${esc(d.title)}</b><span>${esc(d.line)}</span></span>` +
    undo +
    '<span class="dc-check" aria-hidden="true"><svg viewBox="0 0 20 20"><path d="M6 10.4l2.8 2.9L14.2 7" pathLength="1"/></svg></span>'
  );
}

/** What a screen reader hears for a card, as the app's DoneCardText.spoken says it. */
export function spoken(d: Done): string {
  const what: Record<Kind, string> = {
    event: 'Added to your calendar', todo: 'Added to your to-dos', timer: 'Timer set', note: 'Note written',
    reminder: 'Reminder set', draft: 'Draft written', music: 'Playing', opened: 'Opened',
  };
  return `${what[d.kind]}: ${d.title}, ${d.line}`;
}
