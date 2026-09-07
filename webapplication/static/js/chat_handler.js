import { getFieldLabel } from './utils.js';

export function showLoadingOverlay(message = 'KI generiert…') {
  const overlay = document.getElementById('loadingOverlay');
  const text = document.getElementById('loadingOverlayText');
  if (!overlay) return;
  if (text) text.textContent = message;
  overlay.classList.remove('hidden');
}

export function hideLoadingOverlay() {
  const overlay = document.getElementById('loadingOverlay');
  if (overlay) overlay.classList.add('hidden');
}

async function parseApiResponse(res, fallbackMessage) {
  const raw = await res.text();
  let payload = {};

  if (raw) {
    try {
      payload = JSON.parse(raw);
    } catch (_) {
      const snippet = raw.trim().replace(/\s+/g, ' ').slice(0, 180);
      const statusPart = `HTTP ${res.status}`;
      throw new Error(`${fallbackMessage} (${statusPart}). Unerwartete Server-Antwort: ${snippet || 'leer'}`);
    }
  }

  if (!res.ok) {
    const message = payload.error || payload.message || `${fallbackMessage} (HTTP ${res.status})`;
    throw new Error(message);
  }

  return payload;
}

function triggerAutoSave() {
  document.dispatchEvent(new CustomEvent('autoSaveArticle'));
}

let currentArticleId = null;
let currentField = null;

export function setCurrentArticleId(articleId) {
  currentArticleId = articleId;
  updateEditorVisibility();
}

export function getCurrentArticleId() {
  return currentArticleId;
}

export function updateEditorVisibility() {
  const noArticleOverlay = document.getElementById('noArticleOverlay');
  const articleEditor = document.getElementById('articleEditor');
  
  if (noArticleOverlay && articleEditor) {
    if (currentArticleId) {
      noArticleOverlay.classList.add('hidden');
      articleEditor.classList.remove('hidden');
    } else {
      noArticleOverlay.classList.remove('hidden');
      articleEditor.classList.add('hidden');
    }
  }
}

export function initChatHandler() {
  const chatSidebar = document.getElementById('chatSidebar');
  const chatToggle = document.getElementById('chatToggle');
  const mainContent = document.getElementById('mainContent');

  if (chatToggle && chatSidebar) {
    chatToggle.addEventListener('click', () => {
      chatSidebar.classList.toggle('translate-x-full');
      if (mainContent) {
        mainContent.classList.toggle('mr-[650px]');
      }
    });
  }

  document.addEventListener('click', (e) => {
    if (e.target.classList.contains('generieren-btn')) {
      const field = e.target.getAttribute('data-field');
      handleGenerate(field);
    } else if (e.target.classList.contains('umschreiben-btn')) {
      const field = e.target.getAttribute('data-field');
      openChatAndRewrite(field);
    }
  });

  setupCloseChatOnInteraction();
}

export async function generateField(field, openChat = false) {
  return await handleGenerate(field, openChat);
}

function setupCloseChatOnInteraction() {
  const chatSidebar = document.getElementById('chatSidebar');
  const chatToggle = document.getElementById('chatToggle');
  const mainContent = document.getElementById('mainContent');
  
  if (!chatSidebar) return;

  document.addEventListener('click', (e) => {
    const isChatOpen = !chatSidebar.classList.contains('translate-x-full');
    
    if (!isChatOpen) return;

    const isClickInsideChat = chatSidebar.contains(e.target);
    const isClickOnToggle = chatToggle && chatToggle.contains(e.target);
    const isClickOnChatButtons = e.target.classList.contains('generieren-btn') || 
                                   e.target.classList.contains('umschreiben-btn');
    const isShortenButton = e.target.id === 'shortenTextBtn';

    if (!isClickInsideChat && !isClickOnToggle && !isClickOnChatButtons && !isShortenButton) {
      chatSidebar.classList.add('translate-x-full');
      if (mainContent) {
        mainContent.classList.remove('mr-[650px]');
      }
    }
  });

  const inputFields = document.querySelectorAll('input, textarea');
  inputFields.forEach(field => {
    field.addEventListener('focus', () => {
      const isChatOpen = !chatSidebar.classList.contains('translate-x-full');
      if (isChatOpen) {
        chatSidebar.classList.add('translate-x-full');
        if (mainContent) {
          mainContent.classList.remove('mr-[650px]');
        }
      }
    });
  });

  const saveBtn = document.getElementById('saveBtn');
  if (saveBtn) {
    saveBtn.addEventListener('click', () => {
      const isChatOpen = !chatSidebar.classList.contains('translate-x-full');
      if (isChatOpen) {
        chatSidebar.classList.add('translate-x-full');
        if (mainContent) {
          mainContent.classList.remove('mr-[650px]');
        }
      }
    });
  }

  const newChatBtn = document.getElementById('newChatBtn');
  if (newChatBtn) {
    newChatBtn.addEventListener('click', () => {
      const isChatOpen = !chatSidebar.classList.contains('translate-x-full');
      if (isChatOpen) {
        chatSidebar.classList.add('translate-x-full');
        if (mainContent) {
          mainContent.classList.remove('mr-[650px]');
        }
      }
    });
  }

  const historyList = document.getElementById('historyList');
  if (historyList) {
    historyList.addEventListener('click', () => {
      const isChatOpen = !chatSidebar.classList.contains('translate-x-full');
      if (isChatOpen) {
        chatSidebar.classList.add('translate-x-full');
        if (mainContent) {
          mainContent.classList.remove('mr-[650px]');
        }
      }
    });
  }
}

async function handleGenerate(field, openChat = true) {
  const chatSidebar = document.getElementById('chatSidebar');
  const chatContent = chatSidebar.querySelector('.space-y-3');
  const mainContent = document.getElementById('mainContent');
  
  if (!currentArticleId) {
    if (openChat && chatSidebar.classList.contains('translate-x-full')) {
      chatSidebar.classList.remove('translate-x-full');
      if (mainContent) {
        mainContent.classList.add('mr-[650px]');
      }
    }
    if (openChat) {
      chatContent.innerHTML = `
        <div class="bg-yellow-50 p-3 rounded">
          <strong>Hinweis</strong>
          <p class="text-sm mt-1">Bitte speichern Sie zuerst den Artikel, um die KI-Funktionen zu nutzen.</p>
        </div>
      `;
    }
    return;
  }
  
  currentField = field;
  const prompt = `Generiere ${getFieldLabel(field)}`;
  
  try {
    let contextContent = '';
    
    if (field === 'text') {
      contextContent = document.getElementById('bulletpoints').value;
      if (!contextContent.trim()) {
        if (openChat && chatSidebar.classList.contains('translate-x-full')) {
          chatSidebar.classList.remove('translate-x-full');
          if (mainContent) {
            mainContent.classList.add('mr-[650px]');
          }
        }
        if (openChat) {
          chatContent.innerHTML = `
            <div class="bg-yellow-50 p-3 rounded">
              <strong>Hinweis</strong>
              <p class="text-sm mt-1">Bitte geben Sie zuerst Stichpunkte ein.</p>
            </div>
          `;
        }
        return;
      }
    } else if (field === 'roofline' || field === 'headline' || field === 'subline' || field === 'teaser' || field === 'subheadings' || field === 'tags') {
      contextContent = document.getElementById('text').value;
      if (!contextContent.trim()) {
        if (openChat && chatSidebar.classList.contains('translate-x-full')) {
          chatSidebar.classList.remove('translate-x-full');
          if (mainContent) {
            mainContent.classList.add('mr-[650px]');
          }
        }
        if (openChat) {
          chatContent.innerHTML = `
            <div class="bg-yellow-50 p-3 rounded">
              <strong>Hinweis</strong>
              <p class="text-sm mt-1">Bitte generieren Sie zuerst den Text.</p>
            </div>
          `;
        }
        return;
      }
    }
    
    showLoadingOverlay(`Generiere ${getFieldLabel(field)}…`);
    const res = await fetch('/api/chats/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        article_id: currentArticleId,
        field_name: field,
        prompt: prompt,
        context: contextContent
      })
    });
    hideLoadingOverlay();

    const data = await parseApiResponse(res, 'Fehler beim Generieren');
    
    document.getElementById(field).value = data.content;
    
    if (openChat && chatSidebar.classList.contains('translate-x-full')) {
      chatSidebar.classList.remove('translate-x-full');
      if (mainContent) {
        mainContent.classList.add('mr-[650px]');
      }
    }
    
    if (openChat) {
      await loadChatHistory(field, chatContent, 'generate');
    }
    
  } catch (err) {
    hideLoadingOverlay();
    console.error('Fehler beim Generieren:', err);
    if (openChat && chatSidebar.classList.contains('translate-x-full')) {
      chatSidebar.classList.remove('translate-x-full');
      if (mainContent) {
        mainContent.classList.add('mr-[650px]');
      }
    }
    if (openChat) {
      chatContent.innerHTML = `
        <div class="bg-red-50 p-3 rounded text-sm text-red-700">
          Fehler beim Generieren: ${err.message}
        </div>
      `;
    }
    throw err;
  }
}

async function openChatAndGenerate(field) {
  const chatSidebar = document.getElementById('chatSidebar');
  const chatContent = chatSidebar.querySelector('.space-y-3');
  const mainContent = document.getElementById('mainContent');
  
  if (chatSidebar.classList.contains('translate-x-full')) {
    chatSidebar.classList.remove('translate-x-full');
    if (mainContent) {
      mainContent.classList.add('mr-[650px]');
    }
  }
  
  currentField = field;
  
  if (currentArticleId) {
    await loadChatHistory(field, chatContent, 'generate');
  } else {
    chatContent.innerHTML = `
      <div class="bg-yellow-50 p-3 rounded">
        <strong>Hinweis</strong>
        <p class="text-sm mt-1">Bitte speichern Sie zuerst den Artikel, um die KI-Funktionen zu nutzen.</p>
      </div>
    `;
    return;
  }
  
  document.getElementById('generateBtn').addEventListener('click', async () => {
    const prompt = document.getElementById('chatPrompt').value;
    if (!prompt.trim()) {
      return;
    }
    
    await generateContent(field, prompt, chatContent);
  });
}

async function openChatAndRewrite(field) {
  const chatSidebar = document.getElementById('chatSidebar');
  const chatContent = chatSidebar.querySelector('.space-y-3');
  const mainContent = document.getElementById('mainContent');
  
  if (chatSidebar.classList.contains('translate-x-full')) {
    chatSidebar.classList.remove('translate-x-full');
    if (mainContent) {
      mainContent.classList.add('mr-[650px]');
    }
  }
  
  currentField = field;
  const currentValue = document.getElementById(field).value;
  
  if (!currentArticleId) {
    chatContent.innerHTML = `
      <div class="bg-yellow-50 p-3 rounded">
        <strong>Hinweis</strong>
        <p class="text-sm mt-1">Bitte speichern Sie zuerst den Artikel, um die KI-Funktionen zu nutzen.</p>
      </div>
    `;
    return;
  }
  
  // Zuerst das Input-Feld oben anzeigen
  if (!currentValue.trim()) {
    chatContent.innerHTML = `
      <div class="bg-yellow-50 p-3 rounded mb-3">
        <strong>Umschreiben ${getFieldLabel(field)}</strong>
        <p class="text-sm mt-1">Bitte geben Sie zuerst Text ein, der umgeschrieben werden soll.</p>
      </div>
    `;
  } else {
    chatContent.innerHTML = `
      <div class="bg-green-50 p-3 rounded mb-3">
        <strong>Schreibe ${getFieldLabel(field)} um</strong>
        <textarea id="chatRewritePrompt" class="w-full mt-2 p-2 border rounded text-sm" rows="3" placeholder="Wie möchten Sie den Text ändern? (z.B. 'schreib das noch dramatischer')"></textarea>
        <button id="rewriteBtn" class="mt-2 bg-blue-600 text-white px-3 py-1 text-sm rounded hover:bg-blue-700">
          Umschreiben
        </button>
      </div>
    `;
    
    document.getElementById('rewriteBtn').addEventListener('click', async () => {
      const userPrompt = document.getElementById('chatRewritePrompt').value;
      if (!userPrompt.trim()) {
        return;
      }
      
      await editContent(field, currentValue, userPrompt, chatContent);
    });
  }
  
  await loadChatHistoryAppend(field, chatContent, 'edit');
}

async function loadChatHistory(field, chatContent, chatType = null) {
  try {
    let url = `/api/chats?article_id=${currentArticleId}&field_name=${field}`;
    if (chatType) {
      url += `&chat_type=${chatType}`;
    }
    
    const res = await fetch(url);
    
    if (!res.ok) {
      throw new Error('Fehler beim Laden der Chat-Historie');
    }
    
    const chats = await res.json();
    
    const typeLabels = {
      'generate': 'Generiert',
      'edit': 'Bearbeitet'
    };
    const typeLabel = chatType ? typeLabels[chatType] || 'Alle' : 'Alle';
    
    chatContent.innerHTML = `
      <div class="mb-3">
        <strong class="text-sm">Historie für ${getFieldLabel(field)}</strong>
        ${chatType ? `<span class="text-xs text-gray-500 ml-2">(${typeLabel})</span>` : ''}
      </div>
    `;
    
    if (chats.length === 0) {
      const emptyMsg = document.createElement('div');
      emptyMsg.className = 'text-sm text-gray-500 italic';
      emptyMsg.textContent = 'Noch keine Einträge vorhanden.';
      chatContent.appendChild(emptyMsg);
    } else {
      chats.forEach(chat => {
        const chatItem = document.createElement('div');
        const bgColors = {
          'generate': 'bg-blue-50',
          'edit': 'bg-green-50'
        };
        const bgColor = bgColors[chat.chat_type] || 'bg-gray-50';
        
        chatItem.className = `${bgColor} p-2 rounded mb-2 cursor-pointer hover:opacity-80`;
        chatItem.innerHTML = `
          <div class="text-xs text-gray-500">
           ${new Date(chat.created_at).toLocaleString()}
          </div>
          <div class="text-sm mt-1 whitespace-pre-wrap">${chat.content}</div>
        `;
        chatItem.addEventListener('click', () => {
          document.getElementById(field).value = chat.content;
        });
        chatContent.appendChild(chatItem);
      });
    }
  } catch (err) {
    console.error('Fehler beim Laden der Chats:', err);
    chatContent.innerHTML = `
      <div class="bg-red-50 p-3 rounded text-sm text-red-700">
        Fehler beim Laden der Historie.
      </div>
    `;
  }
}

async function loadChatHistoryAppend(field, chatContent, chatType = null) {
  try {
    let url = `/api/chats?article_id=${currentArticleId}&field_name=${field}`;
    if (chatType) {
      url += `&chat_type=${chatType}`;
    }
    
    const res = await fetch(url);
    
    if (!res.ok) {
      throw new Error('Fehler beim Laden der Chat-Historie');
    }
    
    const chats = await res.json();
    
    const typeLabels = {
      'generate': 'Generiert',
      'edit': 'Bearbeitet'
    };
    const typeLabel = chatType ? typeLabels[chatType] || 'Alle' : 'Alle';
    
    const historyHeader = document.createElement('div');
    historyHeader.className = 'mb-3 mt-4 pt-3 border-t border-gray-200';
    historyHeader.innerHTML = `
      <strong class="text-sm">Historie für ${getFieldLabel(field)}</strong>
      ${chatType ? `<span class="text-xs text-gray-500 ml-2">(${typeLabel})</span>` : ''}
    `;
    chatContent.appendChild(historyHeader);
    
    if (chats.length === 0) {
      const emptyMsg = document.createElement('div');
      emptyMsg.className = 'text-sm text-gray-500 italic';
      emptyMsg.textContent = 'Noch keine Einträge vorhanden.';
      chatContent.appendChild(emptyMsg);
    } else {
      chats.forEach(chat => {
        const chatItem = document.createElement('div');
        const bgColors = {
          'generate': 'bg-blue-50',
          'edit': 'bg-green-50'
        };
        const bgColor = bgColors[chat.chat_type] || 'bg-gray-50';
        
        chatItem.className = `${bgColor} p-2 rounded mb-2 cursor-pointer hover:opacity-80`;
        chatItem.innerHTML = `
          <div class="text-xs text-gray-500">
           ${new Date(chat.created_at).toLocaleString()}
          </div>
          <div class="text-sm mt-1 whitespace-pre-wrap">${chat.content}</div>
        `;
        chatItem.addEventListener('click', () => {
          document.getElementById(field).value = chat.content;
        });
        chatContent.appendChild(chatItem);
      });
    }
  } catch (err) {
    console.error('Fehler beim Laden der Chats:', err);
    const errorMsg = document.createElement('div');
    errorMsg.className = 'bg-red-50 p-3 rounded text-sm text-red-700 mt-3';
    errorMsg.textContent = 'Fehler beim Laden der Historie.';
    chatContent.appendChild(errorMsg);
  }
}

async function generateContent(field, prompt, chatContent) {
  try {
    let contextContent = '';
    
    if (field === 'text') {
      contextContent = document.getElementById('bulletpoints').value;
    } else if (field === 'roofline' || field === 'headline' || field === 'subline' || field === 'teaser' || field === 'subheadings') {
      contextContent = document.getElementById('text').value;
    }
    
    showLoadingOverlay(`Generiere ${getFieldLabel(field)}…`);
    const res = await fetch('/api/chats/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        article_id: currentArticleId,
        field_name: field,
        prompt: prompt,
        context: contextContent
      })
    });
    hideLoadingOverlay();

    const data = await parseApiResponse(res, 'Fehler beim Generieren');
    
    document.getElementById(field).value = data.content;
    
    await loadChatHistory(field, chatContent, 'generate');
    
    triggerAutoSave();
  } catch (err) {
    hideLoadingOverlay();
    console.error('Fehler beim Generieren:', err);
  }
}

async function editContent(field, currentContent, userPrompt, chatContent) {
  try {
    showLoadingOverlay(`Schreibe ${getFieldLabel(field)} um…`);
    const res = await fetch('/api/chats/edit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        article_id: currentArticleId,
        field_name: field,
        current_content: currentContent,
        user_prompt: userPrompt,
        preview_only: true
      })
    });
    hideLoadingOverlay();

    const data = await parseApiResponse(res, 'Fehler beim Umschreiben');
    
    showDiffPreview(field, currentContent, data.content, chatContent);
    
  } catch (err) {
    hideLoadingOverlay();
    console.error('Fehler beim Umschreiben:', err);
  }
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function calculateDiff(oldText, newText) {
  const oldWords = oldText.split(/(\s+)/);
  const newWords = newText.split(/(\s+)/);
  const diffs = [];
  
  let i = 0, j = 0;
  while (i < oldWords.length || j < newWords.length) {
    if (i < oldWords.length && j < newWords.length && oldWords[i] === newWords[j]) {
      diffs.push({ type: 'equal', value: oldWords[i] });
      i++; j++;
    } else {
      let foundMatch = false;
      for (let k = j + 1; k < Math.min(j + 10, newWords.length); k++) {
        if (oldWords[i] === newWords[k]) {
          while (j < k) {
            diffs.push({ type: 'insert', value: newWords[j] });
            j++;
          }
          foundMatch = true;
          break;
        }
      }
      
      if (!foundMatch) {
        for (let k = i + 1; k < Math.min(i + 10, oldWords.length); k++) {
          if (oldWords[k] === newWords[j]) {
            while (i < k) {
              diffs.push({ type: 'delete', value: oldWords[i] });
              i++;
            }
            foundMatch = true;
            break;
          }
        }
      }
      
      if (!foundMatch) {
        if (i < oldWords.length) {
          diffs.push({ type: 'delete', value: oldWords[i] });
          i++;
        }
        if (j < newWords.length) {
          diffs.push({ type: 'insert', value: newWords[j] });
          j++;
        }
      }
    }
  }
  
  return diffs;
}

function renderDiff(diffs) {
  return diffs.map(diff => {
    if (diff.type === 'equal') {
      return `<span>${escapeHtml(diff.value)}</span>`;
    } else if (diff.type === 'delete') {
      return `<span class="bg-red-200 line-through">${escapeHtml(diff.value)}</span>`;
    } else if (diff.type === 'insert') {
      return `<span class="bg-green-200">${escapeHtml(diff.value)}</span>`;
    }
  }).join('');
}

function showDiffPreview(field, originalText, newText, chatContent) {
  const diffs = calculateDiff(originalText, newText);
  
  const existingDiff = document.getElementById('diffPreviewSection');
  if (existingDiff) {
    existingDiff.remove();
  }
  
  const diffSection = document.createElement('div');
  diffSection.id = 'diffPreviewSection';
  diffSection.className = 'bg-white p-3 rounded mb-3 border-2 border-green-500';
  diffSection.innerHTML = `
    <strong class="text-sm">Neuer Text</strong>
    <div class="mt-2 p-3 bg-blue-50 rounded text-sm max-h-60 overflow-y-auto whitespace-pre-wrap">
      ${escapeHtml(newText)}
    </div>
    <strong class="text-sm mt-4 block">Änderungen im Detail</strong>
    <div class="mt-2 p-3 bg-gray-50 rounded text-sm max-h-60 overflow-y-auto">
      ${renderDiff(diffs)}
    </div>
    <div class="mt-3 flex gap-2">
      <button id="acceptChangesBtn" class="bg-blue-600 text-white px-4 py-2 text-sm rounded hover:bg-blue-700">
        Übernehmen
      </button>
      <button id="rejectChangesBtn" class="bg-gray-500 text-white px-4 py-2 text-sm rounded hover:bg-gray-600">
        Verwerfen
      </button>
    </div>
  `;
  chatContent.prepend(diffSection);

  document.getElementById('acceptChangesBtn').addEventListener('click', async () => {
    document.getElementById(field).value = newText;
    await saveEditToHistory(field, newText, chatContent);
    diffSection.remove();
    triggerAutoSave();
  });

  document.getElementById('rejectChangesBtn').addEventListener('click', () => {
    diffSection.remove();
  });
}

async function saveEditToHistory(field, content, chatContent) {
  try {
    const res = await fetch('/api/chats/edit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        article_id: currentArticleId,
        field_name: field,
        content: content
      })
    });
    
    if (!res.ok) {
      throw new Error('Fehler beim Speichern in der Historie');
    }
    
    await loadChatHistory(field, chatContent, 'edit');
    
  } catch (err) {
    console.error('Fehler beim Speichern:', err);
  }
}

export async function openShortenTextChat() {
  const chatSidebar = document.getElementById('chatSidebar');
  const chatContent = chatSidebar.querySelector('.space-y-3');
  const mainContent = document.getElementById('mainContent');
  const currentText = document.getElementById('text').value;
  const field = 'text';
  
  if (chatSidebar.classList.contains('translate-x-full')) {
    chatSidebar.classList.remove('translate-x-full');
    if (mainContent) {
      mainContent.classList.add('mr-[650px]');
    }
  }
  
  if (!currentArticleId) {
    chatContent.innerHTML = `
      <div class="bg-yellow-50 p-3 rounded">
        <strong>Hinweis</strong>
        <p class="text-sm mt-1">Bitte speichern Sie zuerst den Artikel, um die KI-Funktionen zu nutzen.</p>
      </div>
    `;
    return;
  }
  
  if (!currentText.trim()) {
    chatContent.innerHTML = `
      <div class="bg-yellow-50 p-3 rounded">
        <strong>Hinweis</strong>
        <p class="text-sm mt-1">Bitte geben Sie zuerst einen Artikel-Text ein, der gekürzt werden soll.</p>
      </div>
    `;
    return;
  }
  
  chatContent.innerHTML = `
    <div class="bg-green-50 p-3 rounded mb-3">
      <strong>Artikeltext kürzen</strong>
      <p class="text-xs text-gray-600 mt-1">Geben Sie die gewünschte Anzahl an Wörtern ein.</p>
      <input 
        type="number" 
        id="targetWordCount" 
        class="w-full mt-2 p-2 border rounded text-sm" 
        placeholder="z.B. 200" 
        min="1"
      />
      <button id="shortenBtn" class="mt-2 bg-blue-600 text-white px-3 py-1 text-sm rounded hover:bg-blue-700">
        Text kürzen
      </button>
    </div>
  `;
  
  document.getElementById('shortenBtn').addEventListener('click', async () => {
    const targetWordCount = document.getElementById('targetWordCount').value;
    
    if (!targetWordCount || targetWordCount <= 0) {
      return;
    }
    
    await shortenText(currentText, targetWordCount, chatContent);
  });
  
  await loadChatHistoryAppend(field, chatContent, 'edit');
}

async function shortenText(currentText, targetWordCount, chatContent) {
  try {
    showLoadingOverlay('Kürze Artikeltext…');
    const res = await fetch('/api/chats/shorten', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        article_id: currentArticleId,
        current_text: currentText,
        target_word_count: targetWordCount,
        preview_only: true
      })
    });
    hideLoadingOverlay();

    const data = await parseApiResponse(res, 'Fehler beim Kürzen');
    
    showShortenPreview(currentText, data.content, chatContent);
    
  } catch (err) {
    hideLoadingOverlay();
    console.error('Fehler beim Kürzen:', err);
  }
}

function showShortenPreview(originalText, shortenedText, chatContent) {
  const diffs = calculateDiff(originalText, shortenedText);
  
  const existingDiff = document.getElementById('shortenPreviewSection');
  if (existingDiff) {
    existingDiff.remove();
  }
  
  const diffSection = document.createElement('div');
  diffSection.id = 'shortenPreviewSection';
  diffSection.className = 'bg-white p-3 rounded mb-3 border-2 border-green-500';
  diffSection.innerHTML = `
    <strong class="text-sm">Gekürzter Text</strong>
    <div class="mt-2 p-3 bg-blue-50 rounded text-sm max-h-60 overflow-y-auto whitespace-pre-wrap">
      ${escapeHtml(shortenedText)}
    </div>
    <strong class="text-sm mt-4 block">Änderungen im Detail</strong>
    <div class="mt-2 p-3 bg-gray-50 rounded text-sm max-h-60 overflow-y-auto">
      ${renderDiff(diffs)}
    </div>
    <div class="mt-3 flex gap-2">
      <button id="acceptShortenBtn" class="bg-blue-600 text-white px-4 py-2 text-sm rounded hover:bg-blue-700">
        Übernehmen
      </button>
      <button id="rejectShortenBtn" class="bg-gray-500 text-white px-4 py-2 text-sm rounded hover:bg-gray-600">
        Verwerfen
      </button>
    </div>
  `;
  chatContent.prepend(diffSection);

  document.getElementById('acceptShortenBtn').addEventListener('click', async () => {
    document.getElementById('text').value = shortenedText;
    await saveEditToHistory('text', shortenedText, chatContent);
    diffSection.remove();
    triggerAutoSave();
  });

  document.getElementById('rejectShortenBtn').addEventListener('click', () => {
    diffSection.remove();
  });
}
