const loginForm = document.querySelector('#login-form');
const registerForm = document.querySelector('#register-form');
const errorBox = document.querySelector('#auth-error');
const path = window.location.pathname;

if (path === '/register') {
  loginForm.hidden = true;
  registerForm.hidden = false;
}

document.querySelector('#form-language')?.addEventListener('change', (event) => {
  const language = event.currentTarget.value;
  const copyLanguage = language === 'hi-IN' ? 'hi' : language === 'mr-IN' ? 'mr' : 'en';
  document.querySelectorAll('[data-copy]').forEach((element) => {
    element.textContent = element.dataset[copyLanguage];
  });
});

const showError = (message) => {
  errorBox.textContent = message;
  errorBox.hidden = false;
};

const submit = async (url, body, button) => {
  errorBox.hidden = true;
  button.disabled = true;
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const result = await response.json();
    if (!response.ok) {
      const detail = result.detail;
      throw new Error(Array.isArray(detail)
        ? detail.map((item) => item.msg).join(' ')
        : detail || 'Please check your details and try again.');
    }
    window.location.assign('/dashboard');
  } catch (reason) {
    showError(reason.message || 'Something went wrong. Please try again.');
    button.disabled = false;
  }
};

loginForm.addEventListener('submit', (event) => {
  event.preventDefault();
  const button = loginForm.querySelector('[type="submit"]');
  if (!loginForm.reportValidity()) {
    showError('Please enter your phone number and 4–6 digit PIN.');
    return;
  }
  submit('/api/login', {
    phone: loginForm.elements.phone.value.trim(),
    pin: loginForm.elements.pin.value,
  }, button);
});

registerForm.addEventListener('submit', (event) => {
  event.preventDefault();
  const button = registerForm.querySelector('[type="submit"]');
  if (!registerForm.reportValidity()) {
    showError('Please complete the required fields. Your PIN must be 4–6 digits.');
    return;
  }
  submit('/api/register', {
    shop_name: registerForm.elements.shop_name.value.trim(),
    owner_name: registerForm.elements.owner_name.value.trim(),
    phone: registerForm.elements.phone.value.trim(),
    pin: registerForm.elements.pin.value,
    language: registerForm.elements.language.value,
    upi_id: registerForm.elements.upi_id.value.trim(),
  }, button);
});

document.querySelector('#demo-login')?.addEventListener('click', async (event) => {
  const button = event.currentTarget;
  errorBox.hidden = true;
  button.disabled = true;
  try {
    const response = await fetch('/api/demo-login', { method: 'POST' });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || 'Demo shop could not be opened.');
    window.location.assign('/dashboard');
  } catch (reason) {
    showError(reason.message || 'Demo shop could not be opened.');
    button.disabled = false;
  }
});
