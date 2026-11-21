const historyEl = document.getElementById('history');
const outputEl = document.getElementById('output');
const submitForm = document.getElementById('submit-form');
const urlInput = document.getElementById('url-input');
const answerForm = document.getElementById('answer-form');
const answerInput = document.getElementById('answer-input');
const cookiesBtn = document.getElementById('cookies-btn');
const cookiesMark = cookiesBtn.querySelector('.cookies-mark');
const cookiesDialog = document.getElementById('cookies-dialog');
const cookiesForm = document.getElementById('cookies-form');
const cookiesFile = document.getElementById('cookies-file');
const cookiesMessage = document.getElementById('cookies-message');
const cookiesCancel = document.getElementById('cookies-cancel');
const runBar = document.getElementById('run-bar');
const runBarUrl = document.getElementById('run-bar-url');
const runBarStatus = document.getElementById('run-bar-status');
const retryBtn = document.getElementById('retry-btn');
const retryIcon = document.getElementById('retry-icon');

let currentId = null;
let currentEntry = null; // {id, url, status} of the submission shown in the content page
let currentSocket = null;
let cookiesOk = null;
let cookiesStatusMessage = '';

function statusLabel(status) {
  return status.replace('_', ' ');
}

// Failed and throttled runs are the non-successful ones that can be retried.
function isRetryable(status) {
  return status === 'failed' || status === 'throttled';
}

function makeRetryButton() {
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'icon-btn retry-btn-small';
  btn.title = 'Retry';
  btn.setAttribute('aria-label', 'Retry');
  btn.appendChild(retryIcon.content.cloneNode(true));
  return btn;
}

function syncRetryButton(el, url, status) {
  let btn = el.querySelector('.retry-btn-small');
  if (isRetryable(status)) {
    if (!btn) {
      btn = makeRetryButton();
      btn.addEventListener('click', (event) => {
        event.stopPropagation();
        startSubmission(url);
      });
      el.appendChild(btn);
    }
  } else if (btn) {
    btn.remove();
  }
}

function syncRunBar() {
  const show = !!currentEntry && isRetryable(currentEntry.status);
  runBar.classList.toggle('hidden', !currentEntry);
  if (!currentEntry) return;
  runBarUrl.textContent = currentEntry.url;
  runBarStatus.className = 'status status-' + currentEntry.status;
  runBarStatus.textContent = statusLabel(currentEntry.status);
  retryBtn.classList.toggle('hidden', !show);
}

function renderHistory(items) {
  historyEl.innerHTML = '';
  for (const item of items) {
    const el = document.createElement('div');
    el.className = 'history-item' + (item.id === currentId ? ' active' : '');
    el.dataset.id = item.id;

    const text = document.createElement('div');
    text.className = 'history-text';

    const urlLine = document.createElement('span');
    urlLine.textContent = item.url;

    const statusLine = document.createElement('span');
    statusLine.className = 'status status-' + item.status;
    statusLine.textContent = statusLabel(item.status);

    text.appendChild(urlLine);
    text.appendChild(statusLine);
    el.appendChild(text);
    syncRetryButton(el, item.url, item.status);
    el.addEventListener('click', () => openSubmission(item.id));
    historyEl.appendChild(el);
  }
}

async function refreshHistory() {
  const res = await fetch('/api/sessions');
  if (!res.ok) return;
  renderHistory(await res.json());
}

function markActiveInSidebar(id) {
  for (const el of historyEl.querySelectorAll('.history-item')) {
    el.classList.toggle('active', el.dataset.id === id);
  }
}

function updateSidebarStatus(id, status) {
  const item = historyEl.querySelector('.history-item[data-id="' + id + '"]');
  if (item) {
    const el = item.querySelector('.status');
    el.className = 'status status-' + status;
    el.textContent = statusLabel(status);
    syncRetryButton(item, item.querySelector('.history-text span').textContent, status);
  }
  if (currentEntry && currentEntry.id === id) {
    currentEntry.status = status;
    syncRunBar();
  }
}

function showAnswerRow(show) {
  answerForm.classList.toggle('hidden', !show);
  if (show) answerInput.focus();
}

function closeSocket() {
  if (currentSocket) {
    currentSocket.onclose = null;
    currentSocket.close();
    currentSocket = null;
  }
}

function connectSocket(id) {
  closeSocket();
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const socket = new WebSocket(proto + '://' + location.host + '/ws/' + id);

  socket.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.type === 'output') {
      outputEl.textContent += message.text;
      outputEl.scrollTop = outputEl.scrollHeight;
    } else if (message.type === 'status') {
      updateSidebarStatus(id, message.status);
      showAnswerRow(message.status === 'needs_input');
      if (message.status === 'done' || message.status === 'failed' || message.status === 'throttled') {
        closeSocket();
      }
    }
  };
  socket.onclose = () => {
    if (currentSocket === socket) currentSocket = null;
  };
  currentSocket = socket;
}

async function openSubmission(id) {
  currentId = id;
  markActiveInSidebar(id);
  showAnswerRow(false);
  closeSocket();

  const res = await fetch('/api/sessions/' + id + '/transcript');
  if (!res.ok) return;
  const data = await res.json();
  currentEntry = { id: data.entry.id, url: data.entry.url, status: data.entry.status };
  syncRunBar();
  outputEl.textContent = data.transcript;
  outputEl.scrollTop = outputEl.scrollHeight;

  if (data.entry.status === 'running' || data.entry.status === 'needs_input') {
    connectSocket(id);
    showAnswerRow(data.entry.status === 'needs_input');
  }
}

async function startSubmission(url) {
  const res = await fetch('/api/submit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  });
  if (!res.ok) {
    alert('Failed to submit');
    return;
  }
  const { id } = await res.json();

  currentId = id;
  currentEntry = { id, url, status: 'running' };
  syncRunBar();
  outputEl.textContent = '';
  showAnswerRow(false);
  await refreshHistory();
  markActiveInSidebar(id);
  connectSocket(id);
}

submitForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const url = urlInput.value.trim();
  if (!url) return;
  urlInput.value = '';
  await startSubmission(url);
});

retryBtn.appendChild(retryIcon.content.cloneNode(true));
// Retry is a fresh submission of the same URL; the failed run stays in the
// history as a record.
retryBtn.addEventListener('click', () => {
  if (currentEntry) startSubmission(currentEntry.url);
});

answerForm.addEventListener('submit', (event) => {
  event.preventDefault();
  const text = answerInput.value;
  answerInput.value = '';
  if (currentSocket && currentSocket.readyState === WebSocket.OPEN) {
    currentSocket.send(JSON.stringify({ input: text }));
  }
  showAnswerRow(false);
});

function setCookiesState(ok) {
  cookiesBtn.classList.remove('cookies-unknown', 'cookies-ok', 'cookies-bad');
  cookiesBtn.classList.add(ok ? 'cookies-ok' : 'cookies-bad');
  cookiesMark.textContent = ok ? '✓' : '✕';
}

async function refreshCookies() {
  const res = await fetch('/api/cookies');
  if (!res.ok) return;
  const data = await res.json();
  cookiesOk = !!data.ok;
  cookiesStatusMessage = data.message || '';
  setCookiesState(cookiesOk);
}

cookiesBtn.addEventListener('click', () => {
  cookiesMessage.textContent = cookiesOk ? '' : cookiesStatusMessage;
  cookiesFile.value = '';
  cookiesDialog.showModal();
});

cookiesCancel.addEventListener('click', () => {
  cookiesDialog.close();
});

cookiesForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const file = cookiesFile.files[0];
  if (!file) {
    cookiesMessage.textContent = 'Choose a cookies.txt file first.';
    return;
  }
  const body = new FormData();
  body.append('file', file);
  const res = await fetch('/api/cookies', { method: 'POST', body });
  let data = {};
  try {
    data = await res.json();
  } catch {
    data = {};
  }
  if (!res.ok || !data.ok) {
    cookiesMessage.textContent = data.message || 'Upload failed.';
    await refreshCookies();
    return;
  }
  cookiesDialog.close();
  setCookiesState(true);
});

refreshHistory();
refreshCookies();
