// Draw the microphone and reply waveforms only while audio is active.
export function initMicVisualizer(canvas) {
  const context = canvas.getContext('2d');
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const state = {
    mode: 'idle',
    frameId: 0,
    lastFrame: 0,
    audioContext: null,
    micAnalyser: null,
    micSource: null,
    micData: null,
    outputAnalyser: null,
    outputSource: null,
    outputAudio: null,
  };
  const bars = reducedMotion.matches ? 32 : 48;

  function resize() {
    const rect = canvas.getBoundingClientRect();
    const pixelRatio = Math.min(1.5, window.devicePixelRatio || 1);
    const size = Math.max(1, Math.min(rect.width || 240, 360));
    canvas.width = Math.round(size * pixelRatio);
    canvas.height = Math.round(size * pixelRatio);
    context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
    drawIdle();
  }

  function center() {
    return {
      x: canvas.width / (2 * (window.devicePixelRatio > 1.5 ? 1.5 : window.devicePixelRatio || 1)),
      y: canvas.height / (2 * (window.devicePixelRatio > 1.5 ? 1.5 : window.devicePixelRatio || 1)),
    };
  }

  function drawIdle() {
    const { x, y } = center();
    const radius = Math.min(x, y);
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.beginPath();
    context.arc(x, y, radius * 0.71, 0, Math.PI * 2);
    context.strokeStyle = 'rgba(255, 204, 102, 0.2)';
    context.lineWidth = 1;
    context.stroke();
    for (let index = 0; index < bars; index += 1) {
      const angle = (index / bars) * Math.PI * 2 - Math.PI / 2;
      const inner = radius * 0.76;
      const outer = inner + (index % 4 === 0 ? 13 : 7);
      context.beginPath();
      context.strokeStyle = index % 4 === 0
        ? 'rgba(255, 204, 102, 0.34)'
        : 'rgba(255, 255, 255, 0.12)';
      context.lineWidth = 1.5;
      context.moveTo(x + Math.cos(angle) * inner, y + Math.sin(angle) * inner);
      context.lineTo(x + Math.cos(angle) * outer, y + Math.sin(angle) * outer);
      context.stroke();
    }
  }

  function drawActive(analyser, data, output = false) {
    if (!analyser || !data) {
      drawIdle();
      return;
    }

    analyser.getByteFrequencyData(data);
    const { x, y } = center();
    const radius = Math.min(x, y);
    context.clearRect(0, 0, canvas.width, canvas.height);

    for (let index = 0; index < bars; index += 1) {
      const angle = (index / bars) * Math.PI * 2 - Math.PI / 2;
      const sampleIndex = Math.floor((index / bars) * data.length);
      const amplitude = data[sampleIndex] / 255;
      const inner = radius * 0.69;
      const outer = inner + 8 + amplitude * radius * 0.22;
      context.beginPath();
      context.strokeStyle = output
        ? 'rgba(107, 214, 168, 0.88)'
        : 'rgba(255, 197, 93, 0.92)';
      context.lineWidth = 2;
      context.lineCap = 'round';
      context.moveTo(x + Math.cos(angle) * inner, y + Math.sin(angle) * inner);
      context.lineTo(x + Math.cos(angle) * outer, y + Math.sin(angle) * outer);
      context.stroke();
    }
  }

  function stopLoop() {
    if (state.frameId) {
      cancelAnimationFrame(state.frameId);
      state.frameId = 0;
    }
  }

  function animate(timestamp) {
    state.frameId = 0;
    if (document.hidden || state.mode === 'idle') return;

    const frameInterval = reducedMotion.matches ? 100 : 1000 / 30;
    if (timestamp - state.lastFrame >= frameInterval) {
      state.lastFrame = timestamp;
      if (state.mode === 'recording') {
        drawActive(state.micAnalyser, state.micData);
      } else if (state.mode === 'playback' && state.outputAnalyser) {
        drawActive(state.outputAnalyser, state.outputData, true);
      } else {
        drawIdle();
      }
    }
    state.frameId = requestAnimationFrame(animate);
  }

  function startLoop() {
    stopLoop();
    if (!document.hidden && !reducedMotion.matches) {
      state.frameId = requestAnimationFrame(animate);
    } else if (state.mode !== 'idle') {
      drawIdle();
    }
  }

  function getAudioContext() {
    if (!state.audioContext) {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (!AudioContextClass) return null;
      state.audioContext = new AudioContextClass();
    }
    if (state.audioContext.state === 'suspended') {
      state.audioContext.resume().catch(() => {});
    }
    return state.audioContext;
  }

  function attachStream(stream) {
    const audioContext = getAudioContext();
    if (!stream || !audioContext) return;
    if (state.micSource) state.micSource.disconnect();

    state.micAnalyser = audioContext.createAnalyser();
    state.micAnalyser.fftSize = 256;
    state.micAnalyser.smoothingTimeConstant = 0.82;
    state.micData = new Uint8Array(state.micAnalyser.frequencyBinCount);
    state.micSource = audioContext.createMediaStreamSource(stream);
    state.micSource.connect(state.micAnalyser);
    state.mode = 'recording';
    startLoop();
  }

  function detachStream() {
    if (state.micSource) state.micSource.disconnect();
    state.micSource = null;
    state.micAnalyser = null;
    state.micData = null;
    if (state.mode === 'recording') state.mode = 'idle';
    stopLoop();
    drawIdle();
  }

  function bindAudio(audio) {
    if (!audio || state.outputAudio === audio) return;
    const audioContext = getAudioContext();
    if (!audioContext) return;

    if (state.outputSource) state.outputSource.disconnect();
    state.outputAnalyser = audioContext.createAnalyser();
    state.outputAnalyser.fftSize = 256;
    state.outputAnalyser.smoothingTimeConstant = 0.82;
    state.outputData = new Uint8Array(state.outputAnalyser.frequencyBinCount);
    state.outputSource = audioContext.createMediaElementSource(audio);
    state.outputSource.connect(state.outputAnalyser);
    state.outputAnalyser.connect(audioContext.destination);
    state.outputAudio = audio;
    state.mode = 'playback';
    startLoop();
  }

  function setIdle() {
    state.mode = 'idle';
    stopLoop();
    drawIdle();
  }

  function setPlayback() {
    state.mode = 'playback';
    startLoop();
  }

  function onVisibilityChange() {
    if (document.hidden) {
      stopLoop();
    } else if (state.mode !== 'idle') {
      startLoop();
    } else {
      drawIdle();
    }
  }

  resize();
  window.addEventListener('resize', resize, { passive: true });
  document.addEventListener('visibilitychange', onVisibilityChange);
  reducedMotion.addEventListener?.('change', startLoop);

  return { attachStream, detachStream, bindAudio, setIdle, setPlayback };
}
