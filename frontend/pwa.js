const offlineBanner = document.querySelector('#offline-banner');

const updateOfflineState = () => {
  if (offlineBanner) offlineBanner.hidden = navigator.onLine;
};

window.addEventListener('online', updateOfflineState);
window.addEventListener('offline', updateOfflineState);
updateOfflineState();

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/service-worker.js', { scope: '/' }).catch(() => {
    if (offlineBanner) {
      offlineBanner.textContent = 'Offline support could not be enabled on this device.';
      offlineBanner.hidden = false;
    }
  });
}
