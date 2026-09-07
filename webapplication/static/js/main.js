import { initChatHandler } from './chat_handler.js';
import { initArticleHandler } from './article_handler.js';
import { initHistoryHandler } from './history_handler.js';

document.addEventListener('DOMContentLoaded', () => {
  initChatHandler();
  initArticleHandler();
  initHistoryHandler();
});
