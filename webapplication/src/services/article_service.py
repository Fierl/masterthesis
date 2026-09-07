from src.database import db
from src.models.Article import Article

def create_article(payload, user_id):
    article = Article(
        user_id = user_id, # type: ignore
        bulletpoints = payload.get('bulletpoints'), # type: ignore
        roofline = payload.get('roofline'), # type: ignore
        headline = payload.get('headline'), # type: ignore
        subline = payload.get('subline'), # type: ignore
        text = payload.get('text'), # type: ignore
        subheadings = payload.get('subheadings'), # type: ignore
        tags = payload.get('tags') # type: ignore
    )
    db.session.add(article)
    db.session.commit()
    return article

def get_articles(user_id=None):
    q = Article.query
    if user_id is not None:
        q = q.filter_by(user_id=user_id)
    q = q.filter_by(is_hidden=False)
    articles = q.order_by(Article.created_at.desc()).all()
    return articles

def update_article(article_id, payload, user_id):
    article = Article.query.filter_by(id=article_id, user_id=user_id).first()
    if not article:
        return None
    
    if 'bulletpoints' in payload:
        article.bulletpoints = payload['bulletpoints']
    if 'roofline' in payload:
        article.roofline = payload['roofline']
    if 'headline' in payload:
        article.headline = payload['headline']
    if 'subline' in payload:
        article.subline = payload['subline']
    if 'text' in payload:
        article.text = payload['text']
    if 'teaser' in payload:
        article.teaser = payload['teaser']
    if 'subheadings' in payload:
        article.subheadings = payload['subheadings']
    if 'tags' in payload:
        article.tags = payload['tags']
    
    db.session.commit()
    return article

def hide_article(article_id, user_id):
    article = Article.query.filter_by(id=article_id, user_id=user_id).first()
    if not article:
        return None
    article.is_hidden = True
    db.session.commit()
    return article