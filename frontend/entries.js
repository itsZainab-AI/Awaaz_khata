// Entry rendering and confirmation actions: keep the parsed ledger entries viewable,
// editable, and easy to confirm without blocking the rest of the interaction flow.

export function createEntryCard(entry, onConfirm, onEdit) {
  const card = document.createElement('div');
  card.className = `entry-card ${entry.type === 'credit_given' ? 'credit' : 'payment'}`;
  card.setAttribute('data-entry-type', entry.type);

  const top = document.createElement('div');
  top.className = 'entry-topline';

  const badge = document.createElement('span');
  badge.className = 'entry-badge';
  badge.textContent = entry.type === 'credit_given' ? 'Credit' : 'Payment';

  const amount = document.createElement('strong');
  amount.className = 'entry-amount';
  amount.textContent = `₹${Number(entry.amount || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;

  top.append(badge, amount);

  const meta = document.createElement('div');
  meta.className = 'entry-meta';
  const person = document.createElement('span');
  person.textContent = entry.person || 'Customer';
  const note = document.createElement('span');
  note.textContent = entry.note || 'No note';
  meta.append(person, note);

  const actions = document.createElement('div');
  actions.className = 'entry-actions';

  const editBtn = document.createElement('button');
  editBtn.type = 'button';
  editBtn.className = 'edit-btn';
  editBtn.textContent = 'Edit';
  editBtn.addEventListener('click', () => onEdit(entry));

  const confirmBtn = document.createElement('button');
  confirmBtn.type = 'button';
  confirmBtn.className = 'confirm-btn';
  confirmBtn.textContent = 'Confirm';
  confirmBtn.addEventListener('click', () => onConfirm(entry));

  actions.append(editBtn, confirmBtn);
  card.append(top, meta, actions);
  return card;
}

export function readingEntryFromDraft(entry) {
  return {
    person: String(entry.person || '').trim(),
    amount: Number(entry.amount || 0),
    note: String(entry.note || '').trim(),
    type: entry.type === 'payment_received' ? 'payment_received' : 'credit_given',
  };
}
