const elements = {
  addEntry: document.querySelector("#add-entry"),
  clarification: document.querySelector("#clarification-block"),
  clarificationQuestion: document.querySelector("#clarification-question"),
  confirm: document.querySelector("#confirm-button"),
  discard: document.querySelector("#discard-button"),
  entries: document.querySelector("#entries-block"),
  entryList: document.querySelector("#entry-list"),
  language: document.querySelector("#language"),
  ledger: document.querySelector("#ledger-list"),
  mic: document.querySelector("#mic-button"),
  micHint: document.querySelector("#mic-hint"),
  notice: document.querySelector("#notice"),
  recordingStatus: document.querySelector("#recording-status"),
  refresh: document.querySelector("#refresh-ledger"),
  replyAudio: document.querySelector("#reply-audio"),
  transcript: document.querySelector("#transcript"),
  transcriptBlock: document.querySelector("#transcript-block"),
  splash: document.querySelector("#splash-screen"),
};

const state = {
  confirmationId: null,
  entries: [],
  mediaRecorder: null,
  chunks: [],
  stream: null,
  recording: false,
  starting: false,
  busy: false,
  pointerId: null,
  recordingTimer: null,
  replyAudioUrl: null,
};

const money = new Intl.NumberFormat(undefined, {
  maximumFractionDigits: 2,
});

window.setTimeout(() => {
  elements.splash.classList.add("is-dismissed");
  window.setTimeout(() => {
    elements.splash.hidden = true;
  }, 420);
}, window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 250 : 1100);

function showNotice(message, kind = "") {
  elements.notice.textContent = message;
  elements.notice.className = `notice ${kind}`.trim();
  elements.notice.hidden = false;
}

function clearNotice() {
  elements.notice.hidden = true;
  elements.notice.textContent = "";
  elements.notice.className = "notice";
}

function setBusy(busy) {
  state.busy = busy;
  elements.mic.disabled = busy;
  elements.confirm.disabled = busy;
  elements.discard.disabled = busy;
}

function selectedLanguage() {
  const option = elements.language.selectedOptions[0];
  return { language: option.value, speechLanguage: option.dataset.speech };
}

function resetProposal() {
  state.confirmationId = null;
  state.entries = [];
  elements.transcriptBlock.hidden = true;
  elements.clarification.hidden = true;
  elements.entries.hidden = true;
  elements.entryList.replaceChildren();
  elements.replyAudio.hidden = true;
  elements.replyAudio.pause();
  elements.replyAudio.removeAttribute("src");
  if (state.replyAudioUrl) URL.revokeObjectURL(state.replyAudioUrl);
  state.replyAudioUrl = null;
}

async function playReply(encodedAudio, contentType) {
  if (!encodedAudio) return;
  const binary = atob(encodedAudio);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  state.replyAudioUrl = URL.createObjectURL(new Blob([bytes], { type: contentType }));
  elements.replyAudio.src = state.replyAudioUrl;
  elements.replyAudio.hidden = false;
  try {
    await elements.replyAudio.play();
  } catch {
    showNotice("Your reply is ready below. Tap play to listen.", "");
  }
}

function writeUint32(view, offset, value) {
  view.setUint32(offset, value, true);
}

function audioBufferToWav(audioBuffer) {
  const sampleRate = 16000;
  const ratio = audioBuffer.sampleRate / sampleRate;
  const outputLength = Math.ceil(audioBuffer.length / ratio);
  const mono = new Float32Array(outputLength);
  const channels = Array.from(
    { length: audioBuffer.numberOfChannels },
    (_, index) => audioBuffer.getChannelData(index),
  );

  for (let outputIndex = 0; outputIndex < outputLength; outputIndex += 1) {
    const start = Math.floor(outputIndex * ratio);
    const end = Math.min(Math.floor((outputIndex + 1) * ratio), audioBuffer.length);
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

  const wav = new ArrayBuffer(44 + mono.length * 2);
  const view = new DataView(wav);
  const bytes = new Uint8Array(wav);
  bytes.set(new TextEncoder().encode("RIFF"), 0);
  writeUint32(view, 4, 36 + mono.length * 2);
  bytes.set(new TextEncoder().encode("WAVEfmt "), 8);
  writeUint32(view, 16, 16);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  writeUint32(view, 24, sampleRate);
  writeUint32(view, 28, sampleRate * 2);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  bytes.set(new TextEncoder().encode("data"), 36);
  writeUint32(view, 40, mono.length * 2);

  for (let index = 0; index < mono.length; index += 1) {
    const sample = Math.max(-1, Math.min(1, mono[index]));
    view.setInt16(44 + index * 2, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
  }
  return new Blob([wav], { type: "audio/wav" });
}

async function toWav(recording) {
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextClass) {
    throw new Error("This browser can record audio but cannot prepare it for transcription.");
  }
  const context = new AudioContextClass();
  try {
    const decoded = await context.decodeAudioData(await recording.arrayBuffer());
    return audioBufferToWav(decoded);
  } finally {
    await context.close();
  }
}

function preferredRecorderType() {
  if (!window.MediaRecorder) return "";
  return [
    "audio/webm;codecs=opus",
    "audio/mp4",
    "audio/ogg;codecs=opus",
  ].find((type) => MediaRecorder.isTypeSupported(type)) || "";
}

async function startRecording(pointerId = null) {
  if (state.recording || state.starting || state.busy) return;
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    showNotice("Audio recording is not supported in this browser. Try a recent version of Safari or Chrome.", "error");
    return;
  }

  clearNotice();
  resetProposal();
  state.pointerId = pointerId;
  state.starting = true;
  try {
    state.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    if (!state.starting) {
      stopMicrophone();
      return;
    }
    const mimeType = preferredRecorderType();
    state.mediaRecorder = new MediaRecorder(
      state.stream,
      mimeType ? { mimeType } : undefined,
    );
    state.chunks = [];
    state.mediaRecorder.addEventListener("dataavailable", (event) => {
      if (event.data.size) state.chunks.push(event.data);
    });
    state.mediaRecorder.addEventListener("stop", submitRecording, { once: true });
    state.mediaRecorder.start();
    state.starting = false;
    state.recording = true;
    elements.mic.classList.add("is-recording");
    elements.mic.setAttribute("aria-label", "Recording, release to finish");
    elements.recordingStatus.textContent = "Listening… let go to finish";
    elements.micHint.innerHTML = "I’m listening…<br><span>Let go when you’re done</span>";
    elements.voiceCard?.classList.add("is-recording");
    state.recordingTimer = window.setTimeout(() => {
      if (state.recording && state.mediaRecorder?.state === "recording") stopRecording();
    }, 60_000);
  } catch (error) {
    state.starting = false;
    stopMicrophone();
    showNotice(error.name === "NotAllowedError"
      ? "Please allow microphone access, then press and hold to try again."
      : `Couldn’t start recording: ${error.message}`, "error");
  }
}

function stopMicrophone() {
  state.stream?.getTracks().forEach((track) => track.stop());
  state.stream = null;
}

function stopRecording() {
  if (!state.recording) {
    state.starting = false;
    state.pointerId = null;
    return;
  }
  state.recording = false;
  state.pointerId = null;
  window.clearTimeout(state.recordingTimer);
  elements.mic.classList.remove("is-recording");
  elements.mic.setAttribute("aria-label", "Hold to record");
  elements.recordingStatus.textContent = "Getting your words ready…";
  elements.micHint.innerHTML = "One moment…<br><span>Getting your words ready</span>";
  elements.voiceCard?.classList.remove("is-recording");
  if (state.mediaRecorder?.state === "recording") state.mediaRecorder.stop();
  stopMicrophone();
}

async function submitRecording() {
  if (!state.chunks.length) {
    elements.recordingStatus.textContent = "Ready when you are";
    elements.micHint.innerHTML = "Press and hold to talk<br><span>Let go when you’re finished</span>";
    showNotice("I didn’t catch any audio. Please try again.", "error");
    return;
  }

  setBusy(true);
  try {
    const recordedBlob = new Blob(state.chunks, {
      type: state.mediaRecorder?.mimeType || "audio/webm",
    });
    const wav = await toWav(recordedBlob);
    const form = new FormData();
    const { language, speechLanguage } = selectedLanguage();
    form.append("audio", wav, "voice-note.wav");
    form.append("language", language);
    form.append("speech_language", speechLanguage);

    const response = await fetch("/voice", { method: "POST", body: form });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "The voice request could not be completed.");

    elements.transcript.textContent = result.transcript || "";
    elements.transcriptBlock.hidden = !result.transcript;
    if (result.status === "clarification_required") {
      elements.clarificationQuestion.textContent = result.clarification_question;
      elements.clarification.hidden = false;
      showNotice("Let’s make sure we get it right before adding anything.", "");
    } else if (result.status === "confirmation_required") {
      state.confirmationId = result.confirmation_id;
      state.entries = result.entries;
      renderEntries();
      elements.entries.hidden = false;
      showNotice("Nothing is saved until you confirm.", "");
    } else {
      throw new Error("The server returned an unexpected voice response.");
    }
    await playReply(result.audio_base64, result.audio_content_type);
  } catch (error) {
    showNotice(error.message || "Something went wrong while processing the recording.", "error");
  } finally {
    setBusy(false);
    elements.recordingStatus.textContent = "Ready when you are";
    elements.micHint.innerHTML = "Press and hold to talk<br><span>Let go when you’re finished</span>";
  }
}

function createField(label, value, className, type = "text") {
  const wrapper = document.createElement("label");
  wrapper.className = `field-label ${className}`;
  const caption = document.createElement("span");
  caption.textContent = label;
  const input = type === "select"
    ? document.createElement("select")
    : document.createElement("input");

  if (type === "select") {
    for (const [value, text] of [
      ["credit_given", "Gave on credit"],
      ["payment_received", "Payment received"],
    ]) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = text;
      input.append(option);
    }
    input.value = value;
  } else {
    input.type = type;
    input.value = value ?? "";
    input.required = true;
    if (type === "number") {
      input.min = "0.01";
      input.step = "0.01";
      input.inputMode = "decimal";
    }
    if (type === "text") input.maxLength = 120;
  }
  input.setAttribute("aria-label", label);
  wrapper.append(caption, input);
  return { wrapper, input };
}

function renderEntries() {
  for (const entry of state.entries) {
    if (!entry._inputs) continue;
    entry.person = entry._inputs.person.value;
    entry.amount = entry._inputs.amount.value;
    entry.note = entry._inputs.note.value;
    entry.type = entry._inputs.type.value;
  }
  elements.entryList.replaceChildren();
  state.entries.forEach((entry, index) => {
    const card = document.createElement("div");
    card.className = "entry-card";
    const person = createField("Person", entry.person, "field-person");
    const amount = createField("Amount (₹)", entry.amount, "field-amount", "number");
    const note = createField("Note", entry.note, "field-note");
    const type = createField("Entry", entry.type, "field-type", "select");
    const edit = document.createElement("button");
    edit.className = "entry-edit";
    edit.type = "button";
    edit.textContent = entry.editing ? "Done" : "Edit";
    edit.setAttribute("aria-label", `${entry.editing ? "Finish editing" : "Edit"} ${entry.person || "entry"}`);
    for (const field of [person.input, amount.input, note.input, type.input]) {
      field.disabled = !entry.editing;
    }
    edit.addEventListener("click", () => {
      entry.editing = !entry.editing;
      renderEntries();
      if (entry.editing) elements.entryList.children[index]?.querySelector(".field-person input")?.focus();
    });
    const remove = document.createElement("button");
    remove.className = "entry-remove";
    remove.type = "button";
    remove.textContent = "×";
    remove.setAttribute("aria-label", `Remove ${entry.person || "entry"}`);
    remove.addEventListener("click", () => {
      for (const current of state.entries) {
        if (!current._inputs) continue;
        current.person = current._inputs.person.value;
        current.amount = current._inputs.amount.value;
        current.note = current._inputs.note.value;
        current.type = current._inputs.type.value;
      }
      state.entries.splice(index, 1);
      if (!state.entries.length) {
        discardProposal();
        showNotice("No entries to save. You can record again whenever you’re ready.", "");
      } else {
        renderEntries();
      }
    });
    card.append(person.wrapper, amount.wrapper, note.wrapper, type.wrapper, edit, remove);
    elements.entryList.append(card);
    entry._inputs = { person: person.input, amount: amount.input, note: note.input, type: type.input };
  });
}

function readEntries() {
  return state.entries.map((entry) => {
    const fields = entry._inputs;
    const amount = Number(fields.amount.value);
    const person = fields.person.value.trim();
    const note = fields.note.value.trim();
    if (!person || !note || !Number.isFinite(amount) || amount <= 0) {
      throw new Error("Please enter a person, a positive amount, and a short note for each entry.");
    }
    return { person, amount, note, type: fields.type.value };
  });
}

async function confirmProposal() {
  if (!state.confirmationId || state.busy) return;
  clearNotice();
  try {
    const entries = readEntries();
    setBusy(true);
    const response = await fetch("/confirm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        confirmation_id: state.confirmationId,
        confirmed: true,
        entries,
      }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "The entries could not be saved.");
    resetProposal();
    showNotice("Your entries are safely in the khata.", "success");
    await loadLedger();
  } catch (error) {
    showNotice(error.message || "The entries could not be saved.", "error");
  } finally {
    setBusy(false);
  }
}

async function discardProposal() {
  if (!state.confirmationId) {
    resetProposal();
    return;
  }
  const confirmationId = state.confirmationId;
  setBusy(true);
  try {
    const response = await fetch("/confirm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirmation_id: confirmationId, confirmed: false }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "The draft could not be discarded.");
    resetProposal();
    showNotice("No worries. Nothing was saved.", "");
  } catch (error) {
    showNotice(error.message || "The draft could not be discarded.", "error");
  } finally {
    setBusy(false);
  }
}

async function openCustomer(name) {
  try {
    const response = await fetch(`/customer/${encodeURIComponent(name)}`);
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Customer details could not be loaded.");
    const details = result.transactions.length
      ? result.transactions
        .map((entry) => `${entry.type === "credit_given" ? "Credit" : "Payment"} · ₹${money.format(entry.amount)} · ${entry.note}`)
        .join("\n")
      : "No entries yet.";
    window.alert(`${result.name} · Balance ₹${money.format(result.balance)}\n\n${details}`);
  } catch (error) {
    showNotice(error.message, "error");
  }
}

async function loadLedger() {
  elements.refresh.disabled = true;
  try {
    const response = await fetch("/ledger");
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "The ledger could not be loaded.");
    elements.ledger.replaceChildren();
    if (!result.customers.length) {
      const empty = document.createElement("div");
      empty.className = "empty-ledger";
      const flower = document.createElement("span");
      flower.textContent = "✳";
      flower.setAttribute("aria-hidden", "true");
      const message = document.createElement("p");
      message.append("Your khata is ready.");
      const small = document.createElement("span");
      small.textContent = "New entries will find a home here.";
      message.append(document.createElement("br"), small);
      empty.append(flower, message);
      elements.ledger.append(empty);
      return;
    }

    for (const customer of result.customers) {
      const row = document.createElement("button");
      row.type = "button";
      row.className = "ledger-row";
      row.setAttribute("aria-label", `${customer.name}, balance ₹${money.format(customer.balance)}. View details.`);
      const person = document.createElement("span");
      person.className = "ledger-person";
      const name = document.createElement("strong");
      name.textContent = customer.name;
      const description = document.createElement("span");
      description.textContent = customer.balance > 0
        ? "owes you"
        : customer.balance < 0
          ? "you owe"
          : "all settled";
      person.append(name, description);
      const balance = document.createElement("span");
      balance.className = `ledger-balance${customer.balance <= 0 ? " is-clear" : ""}`;
      const amount = document.createElement("strong");
      amount.textContent = `₹${money.format(Math.abs(customer.balance))}`;
      const caption = document.createElement("span");
      caption.textContent = customer.balance > 0 ? "to collect" : "balance";
      balance.append(amount, caption);
      row.append(person, balance);
      row.addEventListener("click", () => openCustomer(customer.name));
      elements.ledger.append(row);
    }
  } catch (error) {
    showNotice(error.message || "The ledger could not be loaded.", "error");
  } finally {
    elements.refresh.disabled = false;
  }
}

elements.mic.addEventListener("pointerdown", (event) => {
  if (event.button !== 0 || state.busy) return;
  event.preventDefault();
  elements.mic.setPointerCapture(event.pointerId);
  startRecording(event.pointerId);
});
elements.mic.addEventListener("pointerup", (event) => {
  if (state.pointerId === event.pointerId) stopRecording();
});
elements.mic.addEventListener("pointercancel", stopRecording);
elements.mic.addEventListener("lostpointercapture", stopRecording);
elements.mic.addEventListener("keydown", (event) => {
  if ((event.key === " " || event.key === "Enter") && !event.repeat) {
    event.preventDefault();
    startRecording();
  }
});
elements.mic.addEventListener("keyup", (event) => {
  if (event.key === " " || event.key === "Enter") stopRecording();
});
elements.mic.addEventListener("contextmenu", (event) => event.preventDefault());
elements.confirm.addEventListener("click", confirmProposal);
elements.discard.addEventListener("click", discardProposal);
elements.addEntry.addEventListener("click", () => {
  state.entries.push({ person: "", amount: "", type: "credit_given", note: "" });
  renderEntries();
  elements.entryList.lastElementChild?.querySelector("input")?.focus();
});
elements.refresh.addEventListener("click", loadLedger);
elements.voiceCard = document.querySelector(".voice-card");
loadLedger();
