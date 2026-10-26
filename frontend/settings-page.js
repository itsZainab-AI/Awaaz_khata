const form = document.querySelector('#settings-form');
const errorBox = document.querySelector('#settings-error');
const setError = (message) => {
  errorBox.textContent = message;
  errorBox.hidden = !message;
  errorBox.classList.toggle('settings-success', message === 'Settings saved.');
};
const request = async (url, options = {}) => {
  const response = await fetch(url, options);
  const result = response.status === 204 ? {} : await response.json();
  if (response.status === 401) {
    window.location.replace('/login');
    throw new Error('Your session expired. Please log in again.');
  }
  if (!response.ok) throw new Error(result.detail || 'Request could not be completed.');
  return result;
};

try {
  const result = await request('/api/me');
  form.elements.shop_name.value = result.shop.shop_name;
  form.elements.language.value = result.shop.language;
  form.elements.upi_id.value = result.shop.upi_id || '';
  if (result.shop.is_demo) {
    form.querySelector('button[type="submit"]').disabled = true;
    document.querySelector('#settings-upi').disabled = true;
    document.querySelector('#settings-shop-name').disabled = true;
    document.querySelector('#settings-language').disabled = true;
    setError('Demo shop settings are read-only. Create an account to personalize your khata.');
  }
} catch (error) {
  setError(error.message || 'Your settings could not be loaded.');
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  setError('');
  const button = form.querySelector('button[type="submit"]');
  button.disabled = true;
  try {
    await request('/api/settings', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        shop_name: form.elements.shop_name.value.trim(),
        language: form.elements.language.value,
        upi_id: form.elements.upi_id.value.trim(),
      }),
    });
    setError('Settings saved.');
  } catch (error) {
    setError(error.message || 'Settings could not be saved.');
  } finally {
    button.disabled = false;
  }
});

document.querySelector('#logout-button').addEventListener('click', async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    await request('/api/logout', { method: 'POST' });
    window.location.assign('/');
  } catch (error) {
    setError(error.message || 'Could not log out.');
    button.disabled = false;
  }
});

document.querySelector('#delete-account').addEventListener('click', async (event) => {
  if (!window.confirm('Delete your account and permanently erase all customer and ledger data?')) return;
  const button = event.currentTarget;
  button.disabled = true;
  try {
    await request('/api/account', { method: 'DELETE' });
    window.location.assign('/');
  } catch (error) {
    setError(error.message || 'Account data could not be deleted.');
    button.disabled = false;
  }
});
