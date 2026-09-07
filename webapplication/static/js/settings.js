let currentPrompts = {};

document.addEventListener('DOMContentLoaded', async () => {
  await loadSettings();
  
  const saveBtn = document.getElementById('saveBtn');
  if (saveBtn) {
    saveBtn.addEventListener('click', saveSettings);
  }
});

async function loadSettings() {
  const loadingIndicator = document.getElementById('loadingIndicator');
  const settingsForm = document.getElementById('settingsForm');
  
  try {
    const response = await fetch('/settings/api/system-prompts');
    
    if (!response.ok) {
      throw new Error('Fehler beim Laden der Einstellungen');
    }
    
    const data = await response.json();
    currentPrompts = data;
    
    const fields = ['roofline', 'headline', 'subline', 'teaser', 'text', 'subheadings', 'tags'];
    
    fields.forEach(field => {
      const fieldData = data[field];
      
      const defaultElement = document.getElementById(`default-${field}`);
      if (defaultElement) {
        defaultElement.textContent = fieldData.default;
      }
      
      const customElement = document.getElementById(`custom-${field}`);
      if (customElement) {
        customElement.value = fieldData.custom || '';
      }
    });
    
    loadingIndicator.classList.add('hidden');
    settingsForm.classList.remove('hidden');
    
  } catch (error) {
    console.error('Fehler beim Laden:', error);
    showStatus('Fehler beim Laden der Einstellungen: ' + error.message, 'error');
    loadingIndicator.classList.add('hidden');
  }
}

async function saveSettings() {
  const saveBtn = document.getElementById('saveBtn');
  const originalText = saveBtn.textContent;
  
  saveBtn.disabled = true;
  saveBtn.textContent = 'Speichere...';
  
  try {
    const fields = ['roofline', 'headline', 'subline', 'teaser', 'text', 'subheadings', 'tags'];
    const customPrompts = {};
    
    fields.forEach(field => {
      const customElement = document.getElementById(`custom-${field}`);
      if (customElement && customElement.value.trim()) {
        customPrompts[field] = customElement.value.trim();
      }
    });
    
    const response = await fetch('/settings/api/system-prompts', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(customPrompts)
    });
    
    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.error || 'Fehler beim Speichern');
    }
    
    const result = await response.json();
    showStatus('Einstellungen erfolgreich gespeichert!', 'success');
    
    await loadSettings();
    
  } catch (error) {
    console.error('Fehler beim Speichern:', error);
    showStatus('Fehler beim Speichern: ' + error.message, 'error');
  } finally {
    saveBtn.disabled = false;
    saveBtn.textContent = originalText;
  }
}

async function resetField(field) {
  const confirmed = confirm(`Möchten Sie die zusätzlichen Anweisungen für "${getFieldLabel(field)}" wirklich löschen?`);
  
  if (!confirmed) {
    return;
  }
  
  try {
    const customElement = document.getElementById(`custom-${field}`);
    if (customElement) {
      customElement.value = '';
    }
    
    const response = await fetch(`/settings/api/system-prompts/${field}`, {
      method: 'DELETE'
    });
    
    if (!response.ok && response.status !== 404) {
      const errorData = await response.json();
      throw new Error(errorData.error || 'Fehler beim Zurücksetzen');
    }
    
    showStatus(`Zusätzliche Anweisungen für "${getFieldLabel(field)}" wurden gelöscht.`, 'success');
    
  } catch (error) {
    console.error('Fehler beim Zurücksetzen:', error);
    showStatus('Fehler beim Zurücksetzen: ' + error.message, 'error');
  }
}

function showStatus(message, type = 'info') {
  const statusElement = document.getElementById('statusMessage');
  if (!statusElement) return;
  
  const bgColor = type === 'success' ? 'bg-green-50 text-green-800 border-green-200' : 
                  type === 'error' ? 'bg-red-50 text-red-800 border-red-200' : 
                  'bg-blue-50 text-blue-800 border-blue-200';
  
  statusElement.className = `p-4 rounded-lg border ${bgColor}`;
  statusElement.textContent = message;
  statusElement.classList.remove('hidden');
  
  setTimeout(() => {
    statusElement.classList.add('hidden');
  }, 5000);
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
