const historyEl = document.getElementById('history');
const outputEl = document.getElementById('output');
const submitForm = document.getElementById('submit-form');
const urlInput = document.getElementById('url-input');
const answerForm = document.getElementById('answer-form');
const answerInput = document.getElementById('answer-input');

let currentId = null;
let currentSocket = null;

function statusLabel(status) {
  return status.replace('_', ' ');
}

function renderHistory(items) {
  historyEl.innerHTML = '';
  for (const item of items) {
    const el = document.createElement('div');
    el.className = 'history-item' + (item.id === currentId ? ' active' : '');
    el.dataset.id = item.id;

    const urlLine = document.createElement('span');
    urlLine.textContent = item.url;

    const statusLine = document.createElement('span');
    statusLine.className = 'status status-' + item.status;
    statusLine.textContent = statusLabel(item.status);

    el.appendChild(urlLine);
    el.appendChild(statusLine);
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
  const el = historyEl.querySelector('.history-item[data-id="' + id + '"] .status');
  if (el) {
    el.className = 'status status-' + status;
    el.textContent = statusLabel(status);
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
      if (message.status === 'done' || message.status === 'failed') {
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
  outputEl.textContent = data.transcript;
  outputEl.scrollTop = outputEl.scrollHeight;

  if (data.entry.status === 'running' || data.entry.status === 'needs_input') {
    connectSocket(id);
    showAnswerRow(data.entry.status === 'needs_input');
  }
}

submitForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const url = urlInput.value.trim();
  if (!url) return;
  urlInput.value = '';

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
  outputEl.textContent = '';
  showAnswerRow(false);
  await refreshHistory();
  markActiveInSidebar(id);
  connectSocket(id);
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

refreshHistory();
