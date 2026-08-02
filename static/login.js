const form = document.querySelector('#loginForm');
const errorBox = document.querySelector('#loginError');
form.addEventListener('submit', async (event) => {
  event.preventDefault();
  errorBox.textContent = '';
  const button = form.querySelector('button');
  button.disabled = true;
  try {
    const response = await fetch('/api/auth/login', {
      method: 'POST',
      credentials: 'same-origin',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({password: document.querySelector('#password').value})
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || `Erreur HTTP ${response.status}`);
    window.location.assign('/');
  } catch (error) {
    errorBox.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});
