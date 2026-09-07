import { setCurrentArticleId, getCurrentArticleId, generateField, openShortenTextChat } from './chat_handler.js';

let autoSaveTimeout = null;

export function initArticleHandler() {
  const saveBtn = document.getElementById('saveBtn');
  const newChatBtn = document.getElementById('newChatBtn');
  const createNewFromOverlay = document.getElementById('createNewFromOverlay');
  const generateAllBtn = document.getElementById('generateAllBtn');
  const generateTextBtn = document.getElementById('generateTextBtn');
  const generateOtherFieldsBtn = document.getElementById('generateOtherFieldsBtn');
  const generateSubheadingsBtn = document.getElementById('generateSubheadingsBtn');
  const shortenTextBtn = document.getElementById('shortenTextBtn');

  if (saveBtn) {
    saveBtn.addEventListener('click', async (e) => {
      e.preventDefault();
      await saveArticle();
    });
  }
  
  if (newChatBtn) {
    newChatBtn.addEventListener('click', async (e) => {
      e.preventDefault();
      await createNewChat();
    });
  }

  if (createNewFromOverlay) {
    createNewFromOverlay.addEventListener('click', async (e) => {
      e.preventDefault();
      await createNewChat();
    });
  }

  if (generateAllBtn) {
    generateAllBtn.addEventListener('click', async (e) => {
      e.preventDefault();
      await generateAllFields(generateAllBtn);
    });
  }

  if (generateTextBtn) {
    generateTextBtn.addEventListener('click', async (e) => {
      e.preventDefault();
      await generateTextOnly(generateTextBtn);
    });
  }

  if (generateOtherFieldsBtn) {
    generateOtherFieldsBtn.addEventListener('click', async (e) => {
      e.preventDefault();
      await generateOtherFields(generateOtherFieldsBtn);
    });
  }

  if (generateSubheadingsBtn) {
    generateSubheadingsBtn.addEventListener('click', async (e) => {
      e.preventDefault();
      await generateSubheadingsOnly(generateSubheadingsBtn);
    });
  }

  if (shortenTextBtn) {
    shortenTextBtn.addEventListener('click', async (e) => {
      e.preventDefault();
      await openShortenTextChat();
    });
  }

  initTabs();
  
  initPreviewUpdates();
  
  initCopyButtons();
  
  initAutoSave();
  
  document.addEventListener('autoSaveArticle', async () => {
    await saveArticle({ showAlert: false });
  });
}

export async function saveArticle(options = {}) {
  const { showAlert = true } = options;
  const saveBtn = document.getElementById('saveBtn');
  if (saveBtn) saveBtn.disabled = true;
  
  const payload = {
    bulletpoints: document.getElementById('bulletpoints').value,
    roofline: document.getElementById('roofline').value,
    headline: document.getElementById('headline').value,
    subline: document.getElementById('subline').value,
    text: document.getElementById('text').value,
    teaser: document.getElementById('teaser').value,
    subheadings: document.getElementById('subheadings').value,
    tags: document.getElementById('tags').value
  };
  
  try {
    const currentId = getCurrentArticleId();
    let res;
    
    if (currentId) {
      res = await fetch(`/api/articles/${currentId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
    } else {
      res = await fetch('/api/articles', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
    }
    
    if (res.ok) {
      const body = await res.json();
      setCurrentArticleId(body.id);
      
      const historyEvent = new CustomEvent('reloadHistory');
      document.dispatchEvent(historyEvent);
      
      if (showAlert) {
        alert('Artikel wurde erfolgreich gespeichert.');
      }
    } else {
      const txt = await res.text();
      console.error('Save error', res.status, txt);
      if (showAlert) {
        alert('Fehler beim Speichern des Artikels.');
      }
    }
  } catch (err) {
    console.error(err);
  } finally {
    if (saveBtn) saveBtn.disabled = false;
  }
}

async function createNewChat() {
  const fields = {
    bulletpoints: document.getElementById('bulletpoints'),
    roofline: document.getElementById('roofline'),
    headline: document.getElementById('headline'),
    subline: document.getElementById('subline'),
    teaser: document.getElementById('teaser'),
    text: document.getElementById('text'),
    subheadings: document.getElementById('subheadings'),
    tags: document.getElementById('tags')
  };
  
  Object.values(fields).forEach(field => {
    if (field) field.value = '';
  });
  
  const payload = {
    bulletpoints: '',
    roofline: '',
    headline: '',
    subline: '',
    text: '',
    teaser: '',
    subheadings: '',
    tags: ''
  };
  
  try {
    const res = await fetch('/api/articles', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    
    if (res.ok) {
      const body = await res.json();
      setCurrentArticleId(body.id);
      
      if (fields.bulletpoints) {
        fields.bulletpoints.focus();
      }
      
      const historyEvent = new CustomEvent('reloadHistory');
      document.dispatchEvent(historyEvent);
      
    } else {
      const txt = await res.text();
      console.error('Create error', res.status, txt);
    }
  } catch (err) {
    console.error(err);
  }
}

async function generateAllFields(generateAllBtn) {
  const bulletpoints = document.getElementById('bulletpoints').value;
  
  if (!bulletpoints.trim()) {
    return;
  }
  
  if (!getCurrentArticleId()) {
    await saveArticle({ showAlert: false });
  }
  
  generateAllBtn.disabled = true;
  const originalText = generateAllBtn.textContent;
  
  try {
    generateAllBtn.textContent = 'Generiere Text...';
    await generateField('text', false);
    
    await new Promise(resolve => setTimeout(resolve, 500));
    
    const fields = ['roofline', 'headline', 'subline', 'teaser', 'subheadings', 'tags'];
    for (const field of fields) {
      generateAllBtn.textContent = `Generiere ${getFieldLabel(field)}...`;
      await generateField(field, false);
      await new Promise(resolve => setTimeout(resolve, 500));
    }
    
    generateAllBtn.textContent = 'Fertig!';
    setTimeout(() => {
      generateAllBtn.textContent = originalText;
    }, 2000);
    
    switchToTab('artikel');
    
    await saveArticle({ showAlert: false });
    
  } catch (err) {
    console.error('Fehler beim Generieren aller Felder:', err);
    generateAllBtn.textContent = originalText;
  } finally {
    generateAllBtn.disabled = false;
  }
}

async function generateTextOnly(generateTextBtn) {
  const bulletpoints = document.getElementById('bulletpoints').value;
  
  if (!bulletpoints.trim()) {
    return;
  }
  
  if (!getCurrentArticleId()) {
    await saveArticle({ showAlert: false });
  }
  
  generateTextBtn.disabled = true;
  const originalText = generateTextBtn.textContent;
  
  try {
    generateTextBtn.textContent = 'Generiere Text...';
    await generateField('text', false);
    
    await new Promise(resolve => setTimeout(resolve, 500));
    
    generateTextBtn.textContent = 'Generiere Zwischenüberschriften...';
    await generateField('subheadings', false);
    
    generateTextBtn.textContent = 'Fertig!';
    setTimeout(() => {
      generateTextBtn.textContent = originalText;
    }, 2000);
    
    switchToTab('artikel');
    
    await saveArticle({ showAlert: false });
    
  } catch (err) {
    console.error('Fehler beim Generieren des Textes:', err);
    generateTextBtn.textContent = originalText;
  } finally {
    generateTextBtn.disabled = false;
  }
}

async function generateOtherFields(generateOtherFieldsBtn) {
  const text = document.getElementById('text').value;
  
  if (!text.trim()) {
    return;
  }
  
  if (!getCurrentArticleId()) {
    await saveArticle({ showAlert: false });
  }
  
  generateOtherFieldsBtn.disabled = true;
  const originalText = generateOtherFieldsBtn.textContent;
  
  try {
    const fields = ['roofline', 'headline', 'subline', 'teaser', 'tags'];
    for (const field of fields) {
      generateOtherFieldsBtn.textContent = `Generiere ${getFieldLabel(field)}...`;
      await generateField(field);
      await new Promise(resolve => setTimeout(resolve, 500));
    }
    
    generateOtherFieldsBtn.textContent = 'Fertig!';
    setTimeout(() => {
      generateOtherFieldsBtn.textContent = originalText;
    }, 2000);
    
    switchToTab('weitere');
    
    await saveArticle({ showAlert: false });
    
  } catch (err) {
    console.error('Fehler beim Generieren der anderen Felder:', err);
    generateOtherFieldsBtn.textContent = originalText;
  } finally {
    generateOtherFieldsBtn.disabled = false;
  }
}

async function generateSubheadingsOnly(generateSubheadingsBtn) {
  const text = document.getElementById('text').value;
  
  if (!text.trim()) {
    return;
  }
  
  if (!getCurrentArticleId()) {
    await saveArticle({ showAlert: false });
  }
  
  generateSubheadingsBtn.disabled = true;
  const originalText = generateSubheadingsBtn.textContent;
  
  try {
    generateSubheadingsBtn.textContent = 'Generiere...';
    await generateField('subheadings');
    
    generateSubheadingsBtn.textContent = 'Fertig!';
    setTimeout(() => {
      generateSubheadingsBtn.textContent = originalText;
    }, 2000);
    
    await saveArticle({ showAlert: false });
    
  } catch (err) {
    console.error('Fehler beim Generieren der Zwischenüberschriften:', err);
    generateSubheadingsBtn.textContent = originalText;
  } finally {
    generateSubheadingsBtn.disabled = false;
  }
}

function getFieldLabel(field) {
  const labels = {
    'roofline': 'Dachzeile',
    'headline': 'Titel',
    'subline': 'Untertitel',
    'teaser': 'Paywall-Teaser',
    'text': 'Text',
    'subheadings': 'Zwischenüberschriften',
    'tags': 'Tags'
  };
  return labels[field] || field;
}

function initTabs() {
  const tabButtons = document.querySelectorAll('.tab-btn');
  const tabContents = document.querySelectorAll('.tab-content');
  
  tabButtons.forEach(button => {
    button.addEventListener('click', () => {
      const targetTab = button.getAttribute('data-tab');
      switchToTab(targetTab);
    });
  });
}

export function switchToTab(targetTab) {
  const tabButtons = document.querySelectorAll('.tab-btn');
  const tabContents = document.querySelectorAll('.tab-content');
  
  tabButtons.forEach(btn => {
    btn.classList.remove('active', 'border-blue-600', 'text-blue-600');
    btn.classList.add('border-transparent', 'text-gray-600');
  });
  
  const targetButton = document.querySelector(`.tab-btn[data-tab="${targetTab}"]`);
  if (targetButton) {
    targetButton.classList.add('active', 'border-blue-600', 'text-blue-600');
    targetButton.classList.remove('border-transparent', 'text-gray-600');
  }
  
  tabContents.forEach(content => {
    content.classList.add('hidden');
  });
  
  const targetContent = document.getElementById(`tab-${targetTab}`);
  if (targetContent) {
    targetContent.classList.remove('hidden');
  }
  
  if (targetTab === 'uebersicht') {
    updatePreview();
  }
}

function initPreviewUpdates() {
  const fields = ['roofline', 'headline', 'subline', 'teaser', 'text', 'subheadings', 'tags'];
  
  fields.forEach(fieldName => {
    const field = document.getElementById(fieldName);
    if (field) {
      field.addEventListener('input', () => {
        updatePreviewField(fieldName);
      });
    }
  });
}

function initAutoSave() {
  const fields = ['bulletpoints', 'roofline', 'headline', 'subline', 'teaser', 'text', 'subheadings', 'tags'];
  
  fields.forEach(fieldName => {
    const field = document.getElementById(fieldName);
    if (field) {
      field.addEventListener('input', () => {
        if (autoSaveTimeout) {
          clearTimeout(autoSaveTimeout);
        }
        autoSaveTimeout = setTimeout(async () => {
          if (getCurrentArticleId()) {
            await saveArticle({ showAlert: false });
          }
        }, 1000);
      });
    }
  });
}

function updatePreview() {
  const fields = ['roofline', 'headline', 'subline', 'teaser', 'text', 'subheadings', 'tags'];
  fields.forEach(fieldName => {
    updatePreviewField(fieldName);
  });
}

function updatePreviewField(fieldName) {
  const field = document.getElementById(fieldName);
  const preview = document.getElementById(`preview-${fieldName}`);
  
  if (field && preview) {
    const value = field.value.trim();
    preview.textContent = value || '—';
  }
}

async function copyTextToClipboard(text) {
  const hasClipboardApi = typeof navigator !== 'undefined' && navigator.clipboard && typeof navigator.clipboard.writeText === 'function';

  if (hasClipboardApi && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }

  const helperTextarea = document.createElement('textarea');
  helperTextarea.value = text;
  helperTextarea.setAttribute('readonly', '');
  helperTextarea.style.position = 'fixed';
  helperTextarea.style.top = '-1000px';
  helperTextarea.style.left = '-1000px';
  document.body.appendChild(helperTextarea);
  helperTextarea.focus();
  helperTextarea.select();

  const successful = document.execCommand('copy');
  document.body.removeChild(helperTextarea);

  if (!successful) {
    throw new Error('Clipboard copy fallback failed');
  }
}

function initCopyButtons() {
  const copyButtons = document.querySelectorAll('.copy-btn');
  
  copyButtons.forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.preventDefault();
      const fieldName = btn.dataset.field;
      const field = document.getElementById(fieldName);
      
      if (!field || !field.value.trim()) {
        showCopyFeedback(btn, 'Kein Inhalt zum Kopieren', false);
        return;
      }
      
      try {
        await copyTextToClipboard(field.value);
        showCopyFeedback(btn, '✓ Kopiert!', true);
      } catch (err) {
        console.error('Fehler beim Kopieren:', err);
        showCopyFeedback(btn, '✗ Fehler', false);
      }
    });
  });
}

function showCopyFeedback(button, message, success) {
  const originalText = button.textContent;
  const originalColor = button.className;
  
  button.textContent = message;
  
  if (success) {
    button.className = button.className.replace('bg-gray-500 hover:bg-gray-600', 'bg-green-500 hover:bg-green-600');
  } else {
    button.className = button.className.replace('bg-gray-500 hover:bg-gray-600', 'bg-red-500 hover:bg-red-600');
  }
  
  setTimeout(() => {
    button.textContent = originalText;
    button.className = originalColor;
  }, 2000);
}
