from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


from app import app
from src.database import db
from src.models import User

def create_user():
    with app.app_context():
        username = ""
        raw_password = ""

        if User.query.filter_by(username=username).first():
            print("User already exists:", username)
            return

        user = User(username=username) # type: ignore
        user.set_password(raw_password)
        
        db.session.add(user)
        db.session.commit()
        print(f"User created: {username} with password: {raw_password}")

if __name__ == "__main__":
    create_user()