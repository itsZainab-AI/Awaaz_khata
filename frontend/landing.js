const button = document.querySelector('#try-demo');
const error = document.querySelector('#landing-error');

button?.addEventListener('click', async () => {
  button.disabled = true;
  error.hidden = true;
  try {
    const response = await fetch('/api/demo-login', { method: 'POST' });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || 'Demo shop could not be opened.');
    window.location.assign('/dashboard');
  } catch (reason) {
    error.textContent = reason.message || 'Demo shop could not be opened. Please try again.';
    error.hidden = false;
    button.disabled = false;
  }
});
