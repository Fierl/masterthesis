from src.database import db
from flask_login import login_user, logout_user


class AuthService:
    @staticmethod
    def register_user(username, password):
        from src.models.User import User
        
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            return False, "Username bereits vergeben", None
        
        if not username or len(username.strip()) < 3:
            return False, "Username muss mindestens 3 Zeichen lang sein", None
        
        if not password or len(password) < 6:
            return False, "Passwort muss mindestens 6 Zeichen lang sein", None
        
        try:
            user = User(username=username.strip()) # type: ignore
            user.set_password(password)
            
            db.session.add(user)
            db.session.commit()
            
            return True, "Benutzer erfolgreich registriert", user
        
        except Exception as e:
            db.session.rollback()
            return False, f"Fehler bei der Registrierung: {str(e)}", None
    
    @staticmethod
    def login_user_service(username, password):
        from src.models.User import User
        
        if not username or not password:
            return False, "Username und Passwort sind erforderlich", None
        
        user = User.query.filter_by(username=username.strip()).first()
        
        if not user or not user.check_password(password):
            return False, "Ungültige Anmeldedaten", None
        
        login_user(user)  # type: ignore
        return True, "Erfolgreich angemeldet", user
    
    @staticmethod
    def logout_user_service():
        """Logout current user"""
        logout_user()
        return True, "Erfolgreich abgemeldet"
    
    @staticmethod
    def get_user_by_id(user_id):
        """Get user by ID for Flask-Login user_loader"""
        from src.models.User import User
        return User.query.get(int(user_id))