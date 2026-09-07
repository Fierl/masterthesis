from src.database import db
from datetime import datetime, timezone

class Article(db.Model):
    __tablename__ = "articles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    bulletpoints = db.Column(db.Text)
    roofline = db.Column(db.Text)
    headline = db.Column(db.Text)
    subline = db.Column(db.Text)
    text = db.Column(db.Text)
    teaser = db.Column(db.Text)
    subheadings = db.Column(db.Text)
    tags = db.Column(db.Text)
    is_hidden = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))