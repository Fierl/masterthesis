from src.database import db
from src.models.Chat import Chat

def create_chat(payload, user_id):
    chat = Chat(**payload, user_id=user_id) # type: ignore
    db.session.add(chat)
    db.session.commit()
    return chat