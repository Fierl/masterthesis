from flask import Blueprint, request, jsonify, render_template
from flask_login import login_required, current_user
from src.database import db
from src.prompts import SystemPrompts

bp = Blueprint('settings', __name__, url_prefix='/settings')


@bp.route('/')
@login_required
def settings_page():
    return render_template('settings.html', username=current_user.username)


@bp.route('/instructions')
@login_required
def instructions_page():
    return render_template('instructions.html', username=current_user.username)


@bp.route('/api/system-prompts', methods=['GET'])
@login_required
def get_system_prompts():
    custom_prompts = current_user.get_custom_prompts()
    
    fields = ['roofline', 'headline', 'subline', 'teaser', 'text', 'subheadings', 'tags']
    prompts = {}
    
    for field in fields:
        prompts[field] = {
            'default': SystemPrompts.get_prompt(field),
            'custom': custom_prompts.get(field, ''),
            'using_custom': bool(custom_prompts.get(field))
        }
    
    return jsonify(prompts)


@bp.route('/api/system-prompts', methods=['POST'])
@login_required
def save_system_prompts():
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'Keine Daten übermittelt'}), 400
        
        valid_fields = {'roofline', 'headline', 'subline', 'teaser', 'text', 'subheadings', 'tags'}
        prompts_to_save = {}
        
        for field, prompt_text in data.items():
            if field not in valid_fields:
                return jsonify({'error': f'Ungültiges Feld: {field}'}), 400
            
            if prompt_text and prompt_text.strip():
                prompts_to_save[field] = prompt_text.strip()
        
        current_user.set_custom_prompts(prompts_to_save)
        db.session.add(current_user)
        db.session.commit()
        
        return jsonify({
            'message': 'System-Prompts erfolgreich gespeichert',
            'saved_prompts': prompts_to_save
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Fehler beim Speichern: {str(e)}'}), 500


@bp.route('/api/system-prompts/<field>', methods=['DELETE'])
@login_required
def delete_system_prompt(field):
    try:
        valid_fields = {'roofline', 'headline', 'subline', 'teaser', 'text', 'subheadings', 'tags'}
        
        if field not in valid_fields:
            return jsonify({'error': f'Ungültiges Feld: {field}'}), 400
        
        prompts = current_user.get_custom_prompts()
        
        if field in prompts:
            del prompts[field]
            current_user.set_custom_prompts(prompts)
            db.session.commit()
            
            return jsonify({
                'message': f'Custom System-Prompt für {field} wurde gelöscht',
                'field': field
            })
        else:
            return jsonify({'message': f'Kein Custom System-Prompt für {field} vorhanden'}), 404
            
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Fehler beim Löschen: {str(e)}'}), 500
