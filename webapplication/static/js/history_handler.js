import { setCurrentArticleId } from './chat_handler.js';
import { switchToTab } from './article_handler.js';

const SOURCE_URL = '/api/articles';

function getArticleTitle(article) {
  const truncate = (str) => {
    const first = str.trim().split('\n')[0].trim();
    return first.length > 40 ? first.slice(0, 40) + '…' : first;
  };
  if (article.headline && article.headline.trim()) return article.headline.trim();
  if (article.text && article.text.trim()) return truncate(article.text);
  if (article.bulletpoints && article.bulletpoints.trim()) return truncate(article.bulletpoints);
  return 'Untitled';
}

export function initHistoryHandler() {
  const historyList = document.getElementById('historyList');
  
  if (!historyList) {
    console.warn('History list element not found');
    return;
  }

  loadArticleHistory();
  
  document.addEventListener('reloadHistory', () => {
    loadArticleHistory();
  });
}

async function loadArticleHistory() {
  const historyList = document.getElementById('historyList');
  
  try {
    const res = await fetch(SOURCE_URL);
    if (!res.ok) throw new Error('Failed to load articles');
    
    const articles = await res.json();
    renderHistory(articles || []);
  } catch (err) {
    console.error('Error loading articles:', err);
    historyList.innerHTML = '<li class="text-red-500 text-sm">Keine Artikel geladen.</li>';
  }
}

function renderHistory(articles) {
  const historyList = document.getElementById('historyList');
  
  if (!articles.length) {
    historyList.innerHTML = '<li class="text-gray-500 text-sm">Keine Artikel vorhanden.</li>';
    return;
  }
  
  historyList.innerHTML = '';
  articles.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
  
  articles.forEach(article => {
    const li = document.createElement('li');
    li.className = 'p-2 rounded hover:bg-gray-50 cursor-pointer relative group';
    li.dataset.id = article.id;
    li.innerHTML = `
      <div class="pr-8">
        <div class="font-medium text-sm">${getArticleTitle(article)}</div>
        <div class="text-xs text-gray-500">${new Date(article.created_at).toLocaleString()}</div>
      </div>
      <button class="delete-article-btn absolute top-2 right-2 opacity-0 group-hover:opacity-100 text-red-500 hover:text-red-700 transition-opacity" data-id="${article.id}" title="Artikel löschen">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
        </svg>
      </button>
    `;
    
    li.addEventListener('click', (e) => {
      if (!e.target.closest('.delete-article-btn')) {
        loadArticleIntoForm(article);
      }
    });
    
    const deleteBtn = li.querySelector('.delete-article-btn');
    deleteBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      deleteArticle(article.id);
    });
    
    historyList.appendChild(li);
  });
}

function loadArticleIntoForm(article) {
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

  fields.bulletpoints.value = article.bulletpoints || '';
  fields.roofline.value = article.roofline || '';
  fields.headline.value = article.headline || '';
  fields.subline.value = article.subline || '';
  fields.teaser.value = article.teaser || '';
  fields.text.value = article.text || '';
  fields.subheadings.value = article.subheadings || '';
  fields.tags.value = article.tags || '';
  
  setCurrentArticleId(article.id);
  
  updatePreviewFields();
  
  switchToTab('stichpunkte');
}

function updatePreviewFields() {
  const fields = ['roofline', 'headline', 'subline', 'teaser', 'text', 'subheadings', 'tags'];
  fields.forEach(fieldName => {
    const field = document.getElementById(fieldName);
    const preview = document.getElementById(`preview-${fieldName}`);
    
    if (field && preview) {
      const value = field.value.trim();
      preview.textContent = value || '—';
    }
  });
}

async function deleteArticle(articleId) {
  if (!confirm('Möchten Sie diesen Artikel wirklich löschen?')) {
    return;
  }
  
  try {
    const res = await fetch(`${SOURCE_URL}/${articleId}`, {
      method: 'DELETE'
    });
    
    if (!res.ok) {
      throw new Error('Failed to delete article');
    }
    
    await loadArticleHistory();
  } catch (err) {
    console.error('Error deleting article:', err);
  }
}
