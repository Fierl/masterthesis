from flask import Blueprint, request, render_template, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from src.services.auth_service import AuthService

bp = Blueprint('auth', __name__, url_prefix='/auth')


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        success, message, user = AuthService.login_user_service(username, password)
        
        if request.is_json:
            return jsonify({
                'success': success,
                'message': message,
                'redirect': url_for('index') if success else None
            })
        
        if success:
            return redirect(url_for('index'))
        else:
            flash(message, 'error')
    
    return render_template('login.html')


@bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        username = data.get('username', '').strip()
        password = data.get('password', '')
        confirm_password = data.get('confirm_password', '')
        
        if password != confirm_password:
            message = "Passwörter stimmen nicht überein"
            if request.is_json:
                return jsonify({'success': False, 'message': message})
            flash(message, 'error')
            return render_template('register.html')
        
        success, message, user = AuthService.register_user(username, password)
        
        if request.is_json:
            return jsonify({
                'success': success,
                'message': message,
                'redirect': url_for('auth.login') if success else None
            })
        
        if success:
            flash(message, 'success')
            return redirect(url_for('auth.login'))
        else:
            flash(message, 'error')
    
    return render_template('register.html')


@bp.route('/logout')
@login_required
def logout():
    AuthService.logout_user_service()
    flash('Erfolgreich abgemeldet', 'success')
    return redirect(url_for('auth.login'))


@bp.route('/profile')
@login_required
def profile():
    return render_template('profile.html', user=current_user)