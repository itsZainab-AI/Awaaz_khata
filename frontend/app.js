import { initMicVisualizer } from './mic-visualizer.js';
import { createEntryCard } from './entries.js';
import { createLedgerRow, createTimelineEntry } from './ledger.js';
import { emitParticles, vibrate, showNotice } from './effects.js';

const ui = {
  splash: document.querySelector('#splash-screen'),
  heroPanel: document.querySelector('#hero-panel'),
  summaryCard: document.querySelector('.summary-card'),
  micButton: document.querySelector('#mic-button'),
  micStatus: document.querySelector('#mic-status'),
  transcriptText: document.querySelector('#transcript-text'),
  transcriptOriginal: document.querySelector('#transcript-original'),
  transcriptFeedback: document.querySelector('#transcript-feedback'),
  notice: document.querySelector('#notice'),
  audio: document.querySelector('#reply-audio'),
  confirmButton: document.querySelector('#confirm-button'),
  discardButton: document.querySelector('#discard-button'),
  ledgerList: document.querySelector('#ledger-list'),
  confirmationStack: document.querySelector('#confirmation-stack'),
  entryCardList: document.querySelector('#entry-card-list'),
  confirmationActions: document.querySelector('#confirmation-actions'),
  summaryStats: document.querySelector('#summary-stats'),
  summaryChart: document.querySelector('#summary-chart'),
  refreshLedger: document.querySelector('#refresh-ledger'),
  languageButtons: [...document.querySelectorAll('#language-toggle button')],
  customerDrawer: document.querySelector('#customer-drawer'),
  drawerAvatar: document.querySelector('#drawer-avatar'),
  drawerName: document.querySelector('#drawer-name'),
  drawerBalance: document.querySelector('#drawer-balance'),
  drawerCount: document.querySelector('#drawer-count'),
  drawerTimeline: document.querySelector('#drawer-timeline'),
  closeDrawer: document.querySelector('#close-drawer'),
  sendReminder: document.querySelector('#send-reminder'),
  reminderChat: document.querySelector('#reminder-chat'),
  reminderMessage: document.querySelector('#reminder-message'),
  pointerGlow: document.querySelector('#pointer-glow'),
};

const state = {
  confirmationId: null,
  entries: [],
  currentUserName: null,
  stream: null,
  mediaRecorder: null,
  chunks: [],
  isRecording: false,
  isBusy: false,
  pointerId: null,
  isProcessing: false,
  selectedLanguage: 'hi-en',
  originalTranscript: '',
  transcriptFeedback: '',
  voiceLanguage: 'hi-en',
  speechLanguage: 'hi-en',
  loadedLedger: [],
  statusTimer: 0,
};

const micVisualizer = initMicVisualizer(document.querySelector('#mic-canvas'));

const setLanguage = (value) => {
  const map = {
    'hi-en': { language: 'hi-IN', speechLanguage: 'hi-en' },
    'hi-IN': { language: 'hi-IN', speechLanguage: 'hi-IN' },
    'mr-IN': { language: 'mr-IN', speechLanguage: 'mr-IN' },
  };
  const resolved = map[value] || map['hi-en'];
  state.selectedLanguage = value;
  state.voiceLanguage = resolved.language;
  state.speechLanguage = resolved.speechLanguage;
  ui.languageButtons.forEach((button) => {
    const active = button.dataset.lang === value;
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
  });
  if (state.originalTranscript) {
    setTranscript(state.originalTranscript, state.transcriptFeedback);
  }
};

const devanagariLetters = {
  क: 'k', ख: 'kh', ग: 'g', घ: 'gh', ङ: 'ng',
  च: 'ch', छ: 'chh', ज: 'j', झ: 'jh', ञ: 'ny',
  ट: 't', ठ: 'th', ड: 'd', ढ: 'dh', ण: 'n',
  त: 't', थ: 'th', द: 'd', ध: 'dh', न: 'n',
  प: 'p', फ: 'ph', ब: 'b', भ: 'bh', म: 'm',
  य: 'y', र: 'r', ल: 'l', व: 'v', श: 'sh',
  ष: 'sh', स: 's', ह: 'h', ळ: 'l',
};
const devanagariVowels = {
  'अ': 'a', 'आ': 'aa', 'इ': 'i', 'ई': 'ee', 'उ': 'u', 'ऊ': 'oo',
  'ऋ': 'ri', 'ए': 'e', 'ऐ': 'ai', 'ओ': 'o', 'औ': 'au',
  'ा': 'aa', 'ि': 'i', 'ी': 'ee', 'ु': 'u', 'ू': 'oo',
  'ृ': 'ri', 'े': 'e', 'ै': 'ai', 'ो': 'o', 'ौ': 'au',
};
const dependentVowelMarks = new Set(['ा', 'ि', 'ी', 'ु', 'ू', 'ृ', 'े', 'ै', 'ो', 'ौ']);

const transliterateDevanagari = (text) => {
  let result = '';
  let pendingConsonant = false;
  for (const character of text) {
    if (devanagariLetters[character]) {
      if (pendingConsonant) result += 'a';
      result += devanagariLetters[character];
      pendingConsonant = true;
    } else if (devanagariVowels[character]) {
      if (pendingConsonant || !dependentVowelMarks.has(character)) {
        result += devanagariVowels[character];
      }
      pendingConsonant = false;
    } else if (character === '्') {
      pendingConsonant = false;
    } else if (character === 'ं' || character === 'ँ') {
      result += 'n';
      pendingConsonant = false;
    } else if (character === 'ः') {
      result += 'h';
      pendingConsonant = false;
    } else if (/[०-९]/.test(character)) {
      result += String('०१२३४५६७८९'.indexOf(character));
    } else if (character === '़') {
      continue;
    } else {
      pendingConsonant = false;
      result += character;
    }
  }
  return result;
};

const setTranscript = (transcript, feedback = '') => {
  const original = String(transcript || '').trim();
  state.originalTranscript = original;
  state.transcriptFeedback = feedback;
  const display = state.selectedLanguage === 'hi-en'
    ? transliterateDevanagari(original)
    : original;
  ui.transcriptText.textContent = display || 'The recording is ready to be translated.';
  ui.transcriptOriginal.textContent = original ? `Original: ${original}` : '';
  ui.transcriptOriginal.hidden = !original;
  ui.transcriptFeedback.textContent = feedback;
  ui.transcriptFeedback.hidden = !feedback;
};

const setMicStatus = (message) => {
  ui.micStatus.textContent = message;
};

const preferredMimeType = () => {
  if (!window.MediaRecorder) return '';
  const candidates = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/ogg;codecs=opus'];
  return candidates.find((candidate) => MediaRecorder.isTypeSupported(candidate)) || '';
};

const stopMicrophone = () => {
  if (state.stream) {
    state.stream.getTracks().forEach((track) => track.stop());
    state.stream = null;
  }
  micVisualizer.detachStream();
};

const resetDraft = () => {
  state.confirmationId = null;
  state.entries = [];
  ui.confirmationStack.hidden = true;
  ui.confirmationActions.hidden = false;
  ui.entryCardList.replaceChildren();
  ui.audio.pause();
  ui.audio.hidden = true;
  ui.audio.removeAttribute('src');
  ui.audio.load();
  ui.reminderChat.hidden = true;
  ui.customerDrawer.classList.remove('is-open');
};

const setBusy = (busy) => {
  state.isBusy = busy;
  ui.micButton.disabled = busy;
  ui.confirmButton.disabled = busy;
  ui.discardButton.disabled = busy;
};

function showTransientNotice(message, type = '') {
  showNotice(ui.notice, message, type);
}

const handleAudioReply = async (audioBase64, contentType = 'audio/mpeg') => {
  if (!audioBase64) return;
  const binary = atob(audioBase64);
  const bytes = new Uint8Array(binary.length);
  for (let idx = 0; idx < binary.length; idx += 1) {
    bytes[idx] = binary.charCodeAt(idx);
  }
  const blob = new Blob([bytes], { type: contentType });
  const url = URL.createObjectURL(blob);
  ui.audio.src = url;
  ui.audio.hidden = false;
  ui.audio.controls = true;
  micVisualizer.bindAudio(ui.audio);
  micVisualizer.setPlayback();
  try {
    await ui.audio.play();
  } catch {
    showTransientNotice('Reply ready — tap play to hear it.', '');
  }
};

const setMicButtonMode = (mode) => {
  ui.micButton.classList.toggle('is-recording', mode === 'recording');
  ui.micButton.classList.toggle('is-processing', mode === 'processing');
  ui.micButton.setAttribute('aria-label', mode === 'recording'
    ? 'Recording, release to finish'
    : 'Hold to record');
  ui.micButton.setAttribute('aria-pressed', String(mode === 'recording'));
};

const startRecording = async () => {
  if (state.isBusy || state.isRecording || state.isProcessing) return;
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    showTransientNotice('This browser cannot access the mic. Please try another device or browser.', 'error');
    return;
  }

  resetDraft();
  setMicButtonMode('recording');
  setMicStatus('Listening… release to finish');
  state.isRecording = true;
  vibrate(18);
  emitParticles(ui.micButton, 'rgba(255, 153, 51, 0.85)', 22);

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    if (!state.isRecording) {
      stream.getTracks().forEach((track) => track.stop());
      setMicButtonMode('idle');
      setMicStatus('Press & hold to record');
      return;
    }
    state.stream = stream;
    micVisualizer.attachStream(stream);

    const mimeType = preferredMimeType();
    state.mediaRecorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    state.chunks = [];

    state.mediaRecorder.addEventListener('dataavailable', (event) => {
      if (event.data && event.data.size > 0) state.chunks.push(event.data);
    });

    state.mediaRecorder.addEventListener('stop', async () => {
      try {
        if (!state.chunks.length) {
          showTransientNotice('No sound was captured. Please try again.', 'error');
          setMicButtonMode('idle');
          setMicStatus('Press & hold to record');
          return;
        }

        const blob = new Blob(state.chunks, { type: state.mediaRecorder?.mimeType || 'audio/webm' });
        setMicStatus('Preparing your voice note…');
        const wav = await toWav(blob);
        await submitVoice(wav);
      } catch (error) {
        state.isProcessing = false;
        setBusy(false);
        setMicButtonMode('idle');
        setMicStatus('Press & hold to record');
        showTransientNotice(error.message || 'The recording could not be prepared.', 'error');
      }
    }, { once: true });

    state.mediaRecorder.start();
  } catch (error) {
    state.isRecording = false;
    setMicButtonMode('idle');
    setMicStatus('Press & hold to record');
    stopMicrophone();
    showTransientNotice(error.name === 'NotAllowedError'
      ? 'Microphone access was denied. Please allow it and try again.'
      : `Could not start the mic: ${error.message}`, 'error');
  }
};

const stopRecording = () => {
  if (!state.isRecording) return;
  state.isRecording = false;
  setMicButtonMode('processing');
  setMicStatus('Processing your words…');
  if (state.mediaRecorder && state.mediaRecorder.state !== 'inactive') {
    state.mediaRecorder.stop();
  }
  stopMicrophone();
};

const toWav = async (blob) => {
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextClass) {
    throw new Error('This browser cannot convert recordings to the required WAV format.');
  }

  const audioContext = new AudioContextClass();
  try {
    const arrayBuffer = await blob.arrayBuffer();
    const decoded = await audioContext.decodeAudioData(arrayBuffer.slice(0));
    const sampleRate = 16000;
    const ratio = decoded.sampleRate / sampleRate;
    const outputLength = Math.ceil(decoded.length / ratio);
    const mono = new Float32Array(outputLength);
    const channels = Array.from({ length: decoded.numberOfChannels }, (_, index) => decoded.getChannelData(index));

    for (let outputIndex = 0; outputIndex < outputLength; outputIndex += 1) {
      const start = Math.floor(outputIndex * ratio);
      const end = Math.min(Math.floor((outputIndex + 1) * ratio), decoded.length);
      let total = 0;
      let count = 0;
      for (let sourceIndex = start; sourceIndex < end; sourceIndex += 1) {
        for (const channel of channels) {
          total += channel[sourceIndex];
          count += 1;
        }
      }
      mono[outputIndex] = count ? total / count : 0;
    }

    const wavLength = 44 + mono.length * 2;
    const wav = new ArrayBuffer(wavLength);
    const view = new DataView(wav);
    const bytes = new Uint8Array(wav);

    const writeString = (offset, text) => {
      for (let idx = 0; idx < text.length; idx += 1) {
        bytes[offset + idx] = text.charCodeAt(idx);
      }
    };

    writeString(0, 'RIFF');
    view.setUint32(4, 36 + mono.length * 2, true);
    writeString(8, 'WAVE');
    writeString(12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeString(36, 'data');
    view.setUint32(40, mono.length * 2, true);

    for (let index = 0; index < mono.length; index += 1) {
      const sample = Math.max(-1, Math.min(1, mono[index]));
      view.setInt16(44 + index * 2, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
    }
    return new Blob([wav], { type: 'audio/wav' });
  } finally {
    await audioContext.close();
  }
};

const submitVoice = async (waveBlob) => {
  state.isProcessing = true;
  setBusy(true);
  setMicButtonMode('processing');
  const processingStatuses = ['Sun raha hoon…', 'Samajh raha hoon…', 'Hisaab likh raha hoon…'];
  let statusIndex = 0;
  setMicStatus(processingStatuses[statusIndex]);
  window.clearInterval(state.statusTimer);
  state.statusTimer = window.setInterval(() => {
    statusIndex = (statusIndex + 1) % processingStatuses.length;
    setMicStatus(processingStatuses[statusIndex]);
  }, 1100);
  try {
    const form = new FormData();
    form.append('audio', waveBlob, 'recording.wav');
    form.append('language', state.voiceLanguage);
    form.append('speech_language', state.speechLanguage);

    const response = await fetch('/voice', { method: 'POST', body: form });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.detail || 'Voice processing failed.');
    }

    if (result.status === 'unrecognized' || result.status === 'clarification_required') {
      const message = result.message || result.clarification_question || 'Samajh nahi aaya, phir se bolo.';
      setTranscript(result.transcript, message);
      showTransientNotice(message, '');
      if (result.audio_base64) {
        await handleAudioReply(result.audio_base64, result.audio_content_type || 'audio/mpeg');
      }
      return;
    }

    setTranscript(result.transcript);
    if (result.status === 'customer_created') {
      ui.entryCardList.replaceChildren();
      const card = document.createElement('div');
      card.className = 'customer-created-card';
      const icon = document.createElement('span');
      icon.className = 'customer-created-icon';
      icon.setAttribute('aria-hidden', 'true');
      icon.textContent = '✓';
      const copy = document.createElement('div');
      const title = document.createElement('strong');
      title.textContent = result.confirmation_text || `${result.customer.name} ka khata ban gaya`;
      const detail = document.createElement('p');
      detail.textContent = 'Customer added with a ₹0 balance.';
      copy.append(title, detail);
      card.append(icon, copy);
      ui.entryCardList.appendChild(card);
      ui.confirmationActions.hidden = true;
      ui.confirmationStack.hidden = false;
      showTransientNotice(title.textContent, 'success');
      await loadLedger();
      if (result.audio_base64) {
        await handleAudioReply(result.audio_base64, result.audio_content_type || 'audio/mpeg');
      }
      return;
    }

    if (result.status !== 'confirmation_required') {
      throw new Error('Unexpected voice response from the server.');
    }

    state.confirmationId = result.confirmation_id;
    state.entries = Array.isArray(result.entries) ? result.entries.map((entry) => ({
      ...entry,
      person: entry.person || '',
      amount: Number(entry.amount || 0),
      note: entry.note || '',
      type: entry.type === 'payment_received' ? 'payment_received' : 'credit_given',
    })) : [];

    renderEntries();
    ui.confirmationStack.hidden = false;
    showTransientNotice('Review the entries and save when it looks right.', 'success');

    if (result.audio_base64) {
      await handleAudioReply(result.audio_base64, result.audio_content_type || 'audio/mpeg');
    }
  } catch (error) {
    showTransientNotice(error.message || 'The recording could not be processed.', 'error');
  } finally {
    window.clearInterval(state.statusTimer);
    state.statusTimer = 0;
    state.isProcessing = false;
    setBusy(false);
    setMicButtonMode('idle');
    setMicStatus('Press & hold to record');
  }
};

const renderEntries = () => {
  ui.entryCardList.replaceChildren();
  if (!state.entries.length) {
    const empty = document.createElement('div');
    empty.className = 'entry-card';
    empty.textContent = 'No entries ready to save yet.';
    ui.entryCardList.appendChild(empty);
    return;
  }

  state.entries.forEach((entry) => {
    const card = createEntryCard(entry, () => {
      showTransientNotice('This entry is ready to save with the final confirmation.', 'success');
      vibrate(10);
    }, () => {
      const next = entry.person || 'Customer';
      const edited = window.prompt(`Edit customer name for this entry:`, next);
      if (edited && edited.trim()) {
        entry.person = edited.trim();
        renderEntries();
      }
    });
    ui.entryCardList.appendChild(card);
  });
};

const readEntries = () => {
  return state.entries.map((entry) => {
    const person = String(entry.person || '').trim();
    const note = String(entry.note || '').trim();
    const amount = Number(entry.amount || 0);
    if (!person || !note || !Number.isFinite(amount) || amount <= 0) {
      throw new Error('Each entry needs a valid customer, positive amount, and short note.');
    }
    return {
      person,
      amount,
      note,
      type: entry.type === 'payment_received' ? 'payment_received' : 'credit_given',
    };
  });
};

const confirmEntries = async () => {
  if (!state.confirmationId || state.isBusy) return;
  try {
    setBusy(true);
    const payload = {
      confirmation_id: state.confirmationId,
      confirmed: true,
      entries: readEntries(),
    };

    const response = await fetch('/confirm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.detail || 'The draft could not be saved.');
    }

    resetDraft();
    showTransientNotice('Your ledger has been updated.', 'success');
    vibrate([24, 18, 24]);
    emitParticles(document.body, 'rgba(107, 214, 168, 0.9)', 24);
    await loadLedger();
  } catch (error) {
    showTransientNotice(error.message || 'The entry could not be confirmed.', 'error');
  } finally {
    setBusy(false);
  }
};

const discardEntries = async () => {
  if (!state.confirmationId) {
    resetDraft();
    return;
  }

  try {
    setBusy(true);
    const response = await fetch('/confirm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ confirmation_id: state.confirmationId, confirmed: false }),
    });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.detail || 'The draft could not be discarded.');
    }
    resetDraft();
    showTransientNotice('No worries. Nothing was saved.', '');
  } catch (error) {
    showTransientNotice(error.message || 'The draft could not be discarded.', 'error');
  } finally {
    setBusy(false);
  }
};

const openCustomerDrawer = async (customer) => {
  state.currentUserName = customer.name;
  try {
    const response = await fetch(`/customer/${encodeURIComponent(customer.name)}`);
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || 'Customer details could not be loaded.');

    const initials = customer.name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0].toUpperCase()).join('') || 'K';
    ui.drawerAvatar.textContent = initials;
    ui.drawerName.textContent = result.name;
    ui.drawerBalance.textContent = `₹${Math.abs(Number(result.balance || 0)).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
    ui.drawerCount.textContent = String(Array.isArray(result.transactions) ? result.transactions.length : 0);
    ui.drawerTimeline.replaceChildren();

    if (!result.transactions || !result.transactions.length) {
      const empty = document.createElement('div');
      empty.className = 'entry-copy';
      empty.innerHTML = '<strong>No ledger history yet</strong><span>Start by adding a new entry.</span>';
      ui.drawerTimeline.appendChild(empty);
    } else {
      result.transactions.forEach((entry) => {
        const item = createTimelineEntry({
          ...entry,
          type: entry.type === 'payment_received' ? 'payment_received' : 'credit_given',
        });
        ui.drawerTimeline.appendChild(item);
      });
    }

    ui.customerDrawer.classList.add('is-open');
    ui.customerDrawer.setAttribute('aria-hidden', 'false');
  } catch (error) {
    showTransientNotice(error.message || 'Customer details could not be opened.', 'error');
  }
};

const closeCustomerDrawer = () => {
  ui.customerDrawer.classList.remove('is-open');
  ui.customerDrawer.setAttribute('aria-hidden', 'true');
};

const loadLedger = async () => {
  try {
    const response = await fetch('/ledger');
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || 'The ledger could not be loaded.');

    const customers = Array.isArray(result.customers) ? result.customers : [];
    const summary = result.summary || {};
    const transactionCount = Number(summary.transaction_count || 0);
    const hasTransactions = transactionCount > 0;
    state.loadedLedger = customers;
    ui.ledgerList.replaceChildren();

    ui.summaryCard.hidden = !hasTransactions;
    ui.heroPanel.classList.toggle('has-no-transactions', !hasTransactions);
    ui.summaryStats.hidden = !hasTransactions;
    ui.summaryChart.hidden = !hasTransactions;
    if (hasTransactions) {
      const creditValue = Number(summary.credit || 0);
      const paidValue = Number(summary.paid || 0);
      ui.summaryStats.querySelector('[data-summary="credit"]').textContent =
        `₹${creditValue.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
      ui.summaryStats.querySelector('[data-summary="paid"]').textContent =
        `₹${paidValue.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
      ui.summaryStats.querySelector('[data-summary="customers"]').textContent =
        String(customers.length);
    }

    if (!hasTransactions) {
      const empty = document.createElement('div');
      empty.className = 'ledger-empty-state';
      const illustration = document.createElement('span');
      illustration.className = 'ledger-empty-icon';
      illustration.setAttribute('aria-hidden', 'true');
      illustration.textContent = '✳';
      const title = document.createElement('strong');
      title.textContent = 'Your khata is ready';
      const message = document.createElement('p');
      message.textContent = 'Your first voice note will create a customer record.';
      const example = document.createElement('p');
      example.className = 'ledger-example';
      example.textContent = 'Try saying: Ramesh ko 500 udhaar diya';
      const playButton = document.createElement('button');
      playButton.type = 'button';
      playButton.className = 'ledger-example-button';
      playButton.dataset.playExample = 'true';
      playButton.textContent = '▶ Hear example';
      empty.append(illustration, title, message, example, playButton);
      ui.ledgerList.appendChild(empty);
    }

    customers.forEach((customer) => {
      const row = createLedgerRow(customer, openCustomerDrawer);
      ui.ledgerList.appendChild(row);
    });
  } catch (error) {
    showTransientNotice(error.message || 'The ledger could not be loaded.', 'error');
  }
};

const playExampleSentence = async () => {
  try {
    const response = await fetch(
      `/voice-example?speech_language=${encodeURIComponent(state.speechLanguage)}`,
    );
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || 'The example could not be spoken.');
    await handleAudioReply(result.audio_base64, result.audio_content_type || 'audio/mpeg');
  } catch (error) {
    showTransientNotice(error.message || 'The example could not be played.', 'error');
  }
};

const sendReminder = async () => {
  if (!state.currentUserName) return;
  try {
    const response = await fetch(`/remind/${encodeURIComponent(state.currentUserName)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.detail || 'Reminder could not be sent.');
    }

    ui.reminderMessage.textContent = result.reminder_text || 'Your reminder is on the way.';
    ui.reminderChat.hidden = false;
    if (result.audio_base64) {
      await handleAudioReply(result.audio_base64, result.audio_content_type || 'audio/mpeg');
    }
  } catch (error) {
    showTransientNotice(error.message || 'Reminder could not be sent.', 'error');
  }
};

const animateIntro = () => {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    ui.splash.style.display = 'none';
    return;
  }

  const finishIntro = () => {
    ui.splash.classList.add("is-dismissed");
    window.setTimeout(() => {
      ui.splash.hidden = true;
    }, 380);
  };

  if (window.gsap) {
    window.gsap.from('.splash-mark-wrap', {
      scale: 0.92,
      opacity: 0,
      duration: 0.35,
      ease: 'power2.out',
    });
    window.gsap.from('.splash-copy', {
      y: 8,
      opacity: 0,
      duration: 0.32,
      delay: 0.1,
      ease: 'power2.out',
    });
    window.setTimeout(finishIntro, 650);
    return;
  }

  window.setTimeout(finishIntro, 550);
};

ui.micButton.addEventListener('pointerdown', (event) => {
  if (event.button !== 0 || state.isBusy) return;
  state.pointerId = event.pointerId;
  ui.micButton.setPointerCapture(event.pointerId);
  startRecording();
});

ui.micButton.addEventListener('pointerup', () => {
  if (state.isRecording) stopRecording();
});

ui.micButton.addEventListener('pointercancel', stopRecording);
ui.micButton.addEventListener('pointerleave', () => {
  if (state.isRecording) stopRecording();
});

ui.micButton.addEventListener('keydown', (event) => {
  if ((event.key === ' ' || event.key === 'Enter') && !event.repeat) {
    event.preventDefault();
    startRecording();
  }
});

ui.micButton.addEventListener('keyup', (event) => {
  if (event.key === ' ' || event.key === 'Enter') {
    event.preventDefault();
    stopRecording();
  }
});

ui.confirmButton.addEventListener('click', confirmEntries);
ui.discardButton.addEventListener('click', discardEntries);
ui.refreshLedger.addEventListener('click', loadLedger);
ui.ledgerList.addEventListener('click', (event) => {
  if (event.target.closest('[data-play-example]')) playExampleSentence();
});
ui.closeDrawer.addEventListener('click', closeCustomerDrawer);
ui.sendReminder.addEventListener('click', sendReminder);
ui.customerDrawer.addEventListener('click', (event) => {
  if (event.target.dataset.close === 'drawer') closeCustomerDrawer();
});

ui.languageButtons.forEach((button) => {
  button.addEventListener('click', () => {
    setLanguage(button.dataset.lang);
    showTransientNotice(`Language set to ${button.textContent.trim()}.`, '');
  });
});

window.addEventListener('pointermove', (event) => {
  if (window.matchMedia('(pointer: coarse)').matches) return;
  ui.pointerGlow.style.transform = `translate3d(${event.clientX - 110}px, ${event.clientY - 110}px, 0)`;
  ui.pointerGlow.style.opacity = '1';
});

window.addEventListener('pointerleave', () => {
  ui.pointerGlow.style.opacity = '0';
});

ui.audio.addEventListener('play', () => {
  micVisualizer.bindAudio(ui.audio);
  micVisualizer.setPlayback();
});

ui.audio.addEventListener('pause', () => {
  micVisualizer.setIdle();
});

setLanguage('hi-en');
showTransientNotice('Ready to listen to your shop notes.', '');
loadLedger();
animateIntro();
