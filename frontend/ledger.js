// Ledger view: customer rows, balance bars, timeline panels, and reminder chat
// are styled and animated separately to ease future explanation and maintenance.

export function makeInitials(name = '') {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() || '')
    .join('') || 'K';
}

export function customerColors(name = '') {
  const palette = ['#ffb74d', '#ff8ec9', '#7dd6b7', '#58b3ff', '#ffd166', '#c8a4ff'];
  const code = [...name].reduce((sum, character) => sum + character.charCodeAt(0), 0);
  return palette[code % palette.length];
}

export function createLedgerRow(customer, onOpen) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'ledger-row';

  const summary = document.createElement('div');
  summary.className = 'ledger-summary';

  const avatar = document.createElement('div');
  avatar.className = 'avatar';
  avatar.textContent = makeInitials(customer.name);
  avatar.style.background = `linear-gradient(135deg, ${customerColors(customer.name)}, rgba(255,255,255,0.18))`;

  const nameBlock = document.createElement('div');
  nameBlock.className = 'ledger-name';

  const strong = document.createElement('strong');
  strong.textContent = customer.name;

  const relation = document.createElement('span');
  relation.textContent = customer.balance > 0 ? 'owes you' : customer.balance < 0 ? 'you owe' : 'settled';

  nameBlock.append(strong, relation);
  summary.append(avatar, nameBlock);

  const balance = document.createElement('div');
  balance.className = 'ledger-balance';
  const amount = document.createElement('strong');
  amount.textContent = `₹${Math.abs(customer.balance || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
  const label = document.createElement('span');
  label.textContent = customer.balance > 0 ? 'to collect' : 'balance';
  balance.append(amount, label);

  const track = document.createElement('div');
  track.className = 'bar-track';
  const fill = document.createElement('span');
  fill.className = 'bar-fill';
  const width = Math.min(100, Math.abs(customer.balance || 0) / 12 * 100);
  fill.style.width = `${width}%`;
  track.appendChild(fill);

  button.append(summary, balance, track);
  button.addEventListener('click', () => onOpen(customer));
  return button;
}

export function createTimelineEntry(entry) {
  const item = document.createElement('div');
  item.className = 'timeline-item';

  const copy = document.createElement('div');
  copy.className = 'entry-copy';
  const heading = document.createElement('strong');
  heading.textContent = `${entry.type === 'credit_given' ? 'Credit' : 'Payment'} · ₹${Number(entry.amount || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
  const note = document.createElement('span');
  note.textContent = entry.note || 'No note';
  copy.append(heading, note);
  item.append(copy);
  return item;
}
