// Helper effects for particles, vibration, and lightweight animation snippets used across the UI.

export function emitParticles(container, color = 'rgba(255,153,51,0.9)', count = 18) {
  if (!container || typeof document === 'undefined') return;
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reducedMotion) return;

  const fragment = document.createDocumentFragment();
  const bounds = container.getBoundingClientRect();
  const cx = bounds.left + bounds.width / 2;
  const cy = bounds.top + bounds.height / 2;

  for (let idx = 0; idx < Math.min(count, 60); idx += 1) {
    const particle = document.createElement('span');
    particle.style.position = 'fixed';
    particle.style.left = `${cx}px`;
    particle.style.top = `${cy}px`;
    particle.style.width = `${4 + Math.random() * 8}px`;
    particle.style.height = particle.style.width;
    particle.style.borderRadius = '50%';
    particle.style.background = color;
    particle.style.pointerEvents = 'none';
    particle.style.boxShadow = `0 0 16px ${color}`;
    particle.style.opacity = '1';
    particle.style.transform = 'translate3d(0,0,0)';
    particle.style.zIndex = '50';

    const dx = (Math.random() - 0.5) * 180;
    const dy = (Math.random() - 0.5) * 160;
    const duration = 500 + Math.random() * 420;

    particle.animate(
      [
        { transform: `translate3d(0, 0, 0) scale(1)`, opacity: 1 },
        { transform: `translate3d(${dx}px, ${dy}px, 0) scale(0.2)`, opacity: 0.2 },
      ],
      { duration, easing: 'cubic-bezier(0.22, 1, 0.36, 1)' }
    );

    fragment.appendChild(particle);
    setTimeout(() => particle.remove(), duration + 50);
  }

  document.body.appendChild(fragment);
}

export function vibrate(pattern = 18) {
  if ('vibrate' in navigator) {
    navigator.vibrate(pattern);
  }
}

export function showNotice(element, message, type = '') {
  if (!element) return;
  element.textContent = message;
  element.className = `notice ${type}`.trim();
  element.classList.remove('hidden');
  clearTimeout(element._hideTimer);
  element._hideTimer = setTimeout(() => {
    element.classList.add('hidden');
  }, 2200);
}
