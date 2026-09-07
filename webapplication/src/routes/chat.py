from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from src.services.article_service import *
from src.models.Chat import Chat
from src.database import db
from src.services.generation_service import generate_content

bp = Blueprint('chats', __name__)

@bp.route('/api/chats/generate', methods=['POST'])
@login_required
def generate_chat():
    data = request.get_json(silent=True) or {}
    article_id = data.get('article_id')
    field_name = data.get('field_name')
    prompt = data.get('prompt')
    context = data.get('context', '')
    
    if not all([article_id, field_name, prompt]):
        return jsonify({'error': 'article_id, field_name und prompt sind erforderlich'}), 400
    
    if field_name not in ['headline', 'subline', 'roofline', 'text', 'teaser', 'subheadings', 'tags', 'shorten_text']:
        return jsonify({'error': 'Ungültiger field_name'}), 400

    try:
        generated_content = generate_content(prompt, field_name=field_name, context=context, user=current_user)
    except Exception as e:
        return jsonify({'error': str(e)}), 502

    chat = Chat(
        article_id=article_id, # type: ignore
        field_name=field_name, # type: ignore
        chat_type='generate', # type: ignore
        content=generated_content # type: ignore
    )
    
    db.session.add(chat)
    db.session.commit()
    
    return jsonify({
        'id': chat.id,
        'article_id': chat.article_id,
        'field_name': chat.field_name,
        'chat_type': chat.chat_type,
        'content': chat.content,
        'created_at': chat.created_at.isoformat()
    }), 201

@bp.route('/api/chats/edit', methods=['POST'])
@login_required
def edit_chat():
    data = request.get_json(silent=True) or {}
    article_id = data.get('article_id')
    field_name = data.get('field_name')
    current_content = data.get('current_content')
    user_prompt = data.get('user_prompt')
    preview_only = data.get('preview_only', False)
    
    if current_content and user_prompt:
        combined_prompt = f"Aktueller Text:\n{current_content}\n\nÄnderungswunsch:\n{user_prompt}"
        try:
            content = generate_content(combined_prompt, field_name=field_name, user=current_user)
        except Exception as e:
            return jsonify({'error': str(e)}), 502
    else:
        content = data.get('content')
    
    if not all([article_id, field_name, content]):
        return jsonify({'error': 'article_id, field_name und content sind erforderlich'}), 400
    
    if field_name not in ['headline', 'subline', 'roofline', 'text', 'teaser', 'subheadings', 'tags', 'shorten_text']:
        return jsonify({'error': 'Ungültiger field_name'}), 400
    
    if preview_only:
        return jsonify({
            'content': content,
            'preview': True
        }), 200
    
    chat = Chat(
        article_id=article_id, # type: ignore
        field_name=field_name, # type: ignore
        chat_type='edit', # type: ignore
        content=content # type: ignore
    )
    
    db.session.add(chat)
    db.session.commit()
    
    return jsonify({
        'id': chat.id,
        'article_id': chat.article_id,
        'field_name': chat.field_name,
        'chat_type': chat.chat_type,
        'content': chat.content,
        'created_at': chat.created_at.isoformat()
    }), 201

@bp.route('/api/chats', methods=['GET'])
@login_required
def list_chats():
    article_id = request.args.get('article_id', type=int)
    field_name = request.args.get('field_name')
    chat_type = request.args.get('chat_type')
    
    if not article_id or not field_name:
        return jsonify({'error': 'article_id und field_name sind erforderlich'}), 400
    
    if field_name not in ['headline', 'subline', 'roofline', 'text', 'teaser', 'subheadings', 'tags', 'shorten_text']:
        return jsonify({'error': 'Ungültiger field_name'}), 400
    
    if chat_type and chat_type not in ['generate', 'edit', 'shorten']:
        return jsonify({'error': 'Ungültiger chat_type'}), 400
    
    query = Chat.query.filter_by(
        article_id=article_id,
        field_name=field_name
    )
    
    if chat_type:
        query = query.filter_by(chat_type=chat_type)
    
    chats = query.order_by(Chat.created_at.desc()).all()
    
    return jsonify([{
        'id': chat.id,
        'article_id': chat.article_id,
        'field_name': chat.field_name,
        'chat_type': chat.chat_type,
        'content': chat.content,
        'created_at': chat.created_at.isoformat()
    } for chat in chats]), 200

@bp.route('/api/chats/shorten', methods=['POST'])
@login_required
def shorten_text():
    data = request.get_json(silent=True) or {}
    article_id = data.get('article_id')
    current_text = data.get('current_text')
    target_word_count = data.get('target_word_count')
    preview_only = data.get('preview_only', False)
    
    if not all([article_id, current_text, target_word_count]):
        return jsonify({'error': 'article_id, current_text und target_word_count sind erforderlich'}), 400
    
    try:
        target_word_count = int(target_word_count)
        if target_word_count <= 0:
            return jsonify({'error': 'target_word_count muss eine positive Zahl sein'}), 400
    except ValueError:
        return jsonify({'error': 'target_word_count muss eine Zahl sein'}), 400
    
    prompt = f"""Kürze den folgenden Text auf maximal {target_word_count} Wörter. 
Behalte die wichtigsten Informationen und den Kerninhalt bei.
Achte darauf, dass der gekürzte Text flüssig lesbar bleibt und alle wesentlichen Fakten enthält.

Aktueller Text:
{current_text}

Gekürzte Version (maximal {target_word_count} Wörter):"""
    
    try:
        shortened_content = generate_content(prompt, field_name='shorten_text', user=current_user)
    except Exception as e:
        return jsonify({'error': str(e)}), 502
    
    if preview_only:
        return jsonify({
            'content': shortened_content,
            'preview': True
        }), 200
    
    chat = Chat(
        article_id=article_id, # type: ignore
        field_name='shorten_text', # type: ignore
        chat_type='shorten', # type: ignore
        content=shortened_content # type: ignore
    )
    
    db.session.add(chat)
    db.session.commit()
    
    return jsonify({
        'id': chat.id,
        'article_id': chat.article_id,
        'field_name': chat.field_name,
        'chat_type': chat.chat_type,
        'content': chat.content,
        'created_at': chat.created_at.isoformat()
    }), 201
