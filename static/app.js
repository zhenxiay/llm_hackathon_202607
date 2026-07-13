// VIN Parts Finder - frontend. Talks only to our Python backend (/api/decode).

const vinInput = document.getElementById('vinInput');
const decodeBtn = document.getElementById('decodeBtn');
const loadingSpinner = document.getElementById('loadingSpinner');
const errorMessage = document.getElementById('errorMessage');
const vehicleSection = document.getElementById('vehicleSection');
const partsSection = document.getElementById('partsSection');
const partsList = document.getElementById('partsList');
const noPartsMessage = document.getElementById('noPartsMessage');
const vinBoxes = document.getElementById('vinBoxes');
const vinLegend = document.getElementById('vinLegend');
const vinWarning = document.getElementById('vinWarning');
const vehicleImage = document.getElementById('vehicleImage');
const chatSection = document.getElementById('chatSection');
const chatLog = document.getElementById('chatLog');
const chatInput = document.getElementById('chatInput');
const chatSend = document.getElementById('chatSend');

// Conversation state for the AI chat, plus the currently decoded vehicle context.
let currentVehicle = null;
let chatMessages = [];

const SECTION_COLORS = {
    wmi: '#5b8def',
    vds: '#7c6ce0',
    check: '#e0873b',
    year: '#2fa27a',
    plant: '#c05fa8',
    serial: '#8a94a6',
};

decodeBtn.addEventListener('click', decodeVIN);
vinInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') decodeVIN();
});

document.querySelectorAll('.sample').forEach((btn) => {
    btn.addEventListener('click', () => {
        vinInput.value = btn.dataset.vin;
        decodeVIN();
    });
});

async function decodeVIN() {
    const vin = vinInput.value.trim().toUpperCase();

    hideError();
    if (!vin) {
        showError('Please enter a VIN.');
        return;
    }
    if (vin.length !== 17) {
        showError('A VIN must be exactly 17 characters.');
        return;
    }

    showLoading(true);
    vehicleSection.classList.add('hidden');
    partsSection.classList.add('hidden');
    chatSection.classList.add('hidden');

    try {
        const resp = await fetch('/api/decode?vin=' + encodeURIComponent(vin));
        const data = await resp.json();

        if (data.error) {
            showError(data.error);
            return;
        }

        displayVehicleInfo(data.vehicle);
        renderVinBreakdown(data.breakdown);
        displayParts(data.parts);
        setupChat(data.vehicle);
    } catch (err) {
        console.error('decode failed', err);
        showError('Something went wrong contacting the server. Please try again.');
    } finally {
        showLoading(false);
    }
}

function displayVehicleInfo(vehicle) {
    document.getElementById('vehicleMake').textContent = vehicle.make || 'Unknown';
    document.getElementById('vehicleModel').textContent = vehicle.model || 'Unknown';
    document.getElementById('vehicleYear').textContent = vehicle.modelYear || 'Unknown';
    document.getElementById('vehicleBody').textContent = vehicle.bodyClass || 'Unknown';

    if (vehicle.image) {
        vehicleImage.src = vehicle.image;
        vehicleImage.alt = [vehicle.modelYear, vehicle.make, vehicle.model]
            .filter(Boolean).join(' ');
        vehicleImage.classList.remove('hidden');
    } else {
        vehicleImage.classList.add('hidden');
        vehicleImage.removeAttribute('src');
    }

    vehicleSection.classList.remove('hidden');
}

function renderVinBreakdown(breakdown) {
    vinBoxes.innerHTML = '';
    vinLegend.innerHTML = '';
    vinWarning.classList.add('hidden');
    vinWarning.textContent = '';

    if (!breakdown || !breakdown.segments || !breakdown.segments.length) {
        return;
    }

    breakdown.segments.forEach((seg) => {
        const segEl = document.createElement('div');
        segEl.className = 'vin-seg seg-' + seg.key;

        const charsEl = document.createElement('div');
        charsEl.className = 'vin-seg-chars';
        for (const ch of seg.chars) {
            const box = document.createElement('div');
            box.className = 'vin-char';
            box.textContent = ch;
            box.title = seg.label + ' (positions ' + seg.positions + '): ' + seg.note;
            charsEl.appendChild(box);
        }

        const labelEl = document.createElement('div');
        labelEl.className = 'vin-seg-label';
        labelEl.textContent = seg.label;

        segEl.appendChild(charsEl);
        segEl.appendChild(labelEl);
        vinBoxes.appendChild(segEl);
    });

    // Legend: one entry per section, showing the human-readable note.
    breakdown.segments.forEach((seg) => {
        const item = document.createElement('div');
        item.className = 'legend-item';

        const dot = document.createElement('span');
        dot.className = 'legend-dot';
        dot.style.background = SECTION_COLORS[seg.key] || '#999';

        const text = document.createElement('span');
        text.textContent = seg.label + ' — ' + seg.note;

        item.appendChild(dot);
        item.appendChild(text);
        vinLegend.appendChild(item);
    });

    if (breakdown.warning) {
        vinWarning.textContent = breakdown.warning;
        vinWarning.classList.remove('hidden');
    }
}

function displayParts(parts) {
    partsSection.classList.remove('hidden');
    partsList.innerHTML = '';
    noPartsMessage.classList.add('hidden');

    if (!parts || parts.length === 0) {
        noPartsMessage.classList.remove('hidden');
        return;
    }

    parts.forEach((part) => {
        const card = document.createElement('div');
        card.className = 'part-card';

        const h3 = document.createElement('h3');
        h3.textContent = part.name;

        const cat = document.createElement('span');
        cat.className = 'part-category';
        cat.textContent = part.category;

        const price = document.createElement('div');
        price.className = 'part-price';
        price.textContent = '$' + Number(part.price).toFixed(2);

        const desc = document.createElement('p');
        desc.className = 'part-description';
        desc.textContent = part.description;

        card.appendChild(h3);
        card.appendChild(cat);
        card.appendChild(price);
        card.appendChild(desc);

        if (part.lowest) {
            const lowest = document.createElement('div');
            lowest.className = 'part-lowest';
            const listPrice = '$' + Number(part.price).toFixed(2);
            lowest.innerHTML =
                'Lowest: $' + Number(part.lowest.price).toFixed(2) +
                ' · ' + escapeHtml(part.lowest.name) +
                '<span class="strike">' + listPrice + '</span>';
            card.appendChild(lowest);
        }

        if (part.vendors && part.vendors.length) {
            const details = document.createElement('details');
            details.className = 'part-vendors';
            const summary = document.createElement('summary');
            summary.textContent = 'Compare ' + part.vendors.length + ' vendors';
            details.appendChild(summary);
            const ul = document.createElement('ul');
            part.vendors.forEach((v) => {
                const li = document.createElement('li');
                const name = document.createElement('span');
                name.textContent = v.name;
                const vp = document.createElement('span');
                vp.className = 'v-price';
                vp.textContent = '$' + Number(v.price).toFixed(2);
                li.appendChild(name);
                li.appendChild(vp);
                ul.appendChild(li);
            });
            details.appendChild(ul);
            card.appendChild(details);
        }

        partsList.appendChild(card);
    });
}

function escapeHtml(s) {
    return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

// ---- AI chat ----
function setupChat(vehicle) {
    currentVehicle = vehicle;
    chatMessages = [];
    chatLog.innerHTML =
        '<div class="chat-hint">Ask anything about this ' +
        escapeHtml([vehicle.modelYear, vehicle.make, vehicle.model].filter(Boolean).join(' ')) +
        ' — maintenance intervals, common problems, which parts to check. ' +
        'Powered by Claude on the Bosch LLM Farm.</div>';
    chatInput.value = '';
    chatSection.classList.remove('hidden');
}

function appendChatMessage(role, text) {
    const el = document.createElement('div');
    el.className = 'chat-msg ' + role;
    el.textContent = text;
    chatLog.appendChild(el);
    chatLog.scrollTop = chatLog.scrollHeight;
    return el;
}

async function sendChat() {
    const text = chatInput.value.trim();
    if (!text) return;

    appendChatMessage('user', text);
    chatMessages.push({ role: 'user', content: text });
    chatInput.value = '';
    chatInput.disabled = true;
    chatSend.disabled = true;

    const typing = appendChatMessage('typing', 'Thinking…');

    try {
        const resp = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ vehicle: currentVehicle, messages: chatMessages }),
        });
        const data = await resp.json();
        typing.remove();

        if (data.error) {
            appendChatMessage('error', data.error);
            // Don't keep the unanswered user turn in history on failure.
            chatMessages.pop();
        } else {
            appendChatMessage('assistant', data.reply);
            chatMessages.push({ role: 'assistant', content: data.reply });
        }
    } catch (err) {
        console.error('chat failed', err);
        typing.remove();
        appendChatMessage('error', 'Could not reach the assistant. Please try again.');
        chatMessages.pop();
    } finally {
        chatInput.disabled = false;
        chatSend.disabled = false;
        chatInput.focus();
    }
}

chatSend.addEventListener('click', sendChat);
chatInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') sendChat();
});

function showLoading(show) {
    loadingSpinner.classList.toggle('hidden', !show);
}

function showError(message) {
    errorMessage.textContent = message;
    errorMessage.classList.remove('hidden');
}

function hideError() {
    errorMessage.classList.add('hidden');
}
