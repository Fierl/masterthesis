from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from src.services.article_service import *

bp = Blueprint('articles', __name__)

@bp.route('/api/articles', methods=['POST'])
@login_required
def create():
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form.to_dict()
    
    article = create_article(data, user_id=current_user.id)
    return jsonify({
        'id': article.id,
        'created_at': article.created_at.isoformat() if article.created_at else None
    }), 201

@bp.route('/api/articles', methods=['GET'])
@login_required
def list_articles():
    articles = get_articles(user_id=current_user.id)
    result = []
    for a in articles:
        result.append({
            'id': a.id,
            'bulletpoints': a.bulletpoints,
            'roofline': a.roofline,
            'headline': a.headline,
            'subline': a.subline,
            'text': a.text,
            'teaser': a.teaser,
            'subheadings': a.subheadings,
            'tags': a.tags,
            'created_at': a.created_at.isoformat() if a.created_at else None
        })
    return jsonify(result), 200

@bp.route('/api/articles/<int:article_id>', methods=['PUT'])
@login_required
def update(article_id):
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form.to_dict()
    
    article = update_article(article_id, data, user_id=current_user.id)
    if not article:
        return jsonify({'error': 'Article not found'}), 404
    
    return jsonify({
        'id': article.id,
        'created_at': article.created_at.isoformat() if article.created_at else None,
        'updated_at': article.updated_at.isoformat() if article.updated_at else None
    }), 200

@bp.route('/api/articles/<int:article_id>', methods=['DELETE'])
@login_required
def delete_article(article_id):
    article = hide_article(article_id, user_id=current_user.id)
    if not article:
        return jsonify({'error': 'Article not found'}), 404
    return jsonify({'message': 'Article hidden successfully'}), 200