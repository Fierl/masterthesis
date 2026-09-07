from src.database import db
from datetime import datetime, timezone

class Chat(db.Model):
    __tablename__ = "chats"

    id = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(db.Integer, db.ForeignKey("articles.id"), nullable=False)
    field_name = db.Column(db.Enum("headline", "subline", "roofline", "text", "teaser", "subheadings", "shorten_text", "tags", name="article_field"), nullable=False)
    chat_type = db.Column(db.Enum("generate", "edit", "shorten", name="chat_type"), nullable=False, default="generate")
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
