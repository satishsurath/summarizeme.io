from app import db
from datetime import datetime

class Entry_Post(db.Model):
    __tablename__ = 'entry_post'
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    posttype = db.Column(db.Integer, index=True)
    url = db.Column(db.String(2048))
    text2summarize = db.Column(db.Text)
    text2summarize_hash = db.Column(db.String(64), unique=True)
    openAIsummary = db.Column(db.Text)
    openAIkeyInsights = db.Column(db.Text)
    openAItitle = db.Column(db.String(1024))

    def __repr__(self):
        return '<Entry_Posts {}>'.format(self.id)

class oAuthUser(db.Model):
    __tablename__ = 'o_auth_user'
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    linkedin_id = db.Column(db.String(64), index=True)
    email = db.Column(db.String(120), index=True, unique=True)
    name = db.Column(db.String(120), index=True)

    def __repr__(self):
        return '<oAuthUser {}>'.format(self.id)

class Entry_Posts_History(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    entry_post_id = db.Column(db.Integer, db.ForeignKey('entry_post.id'), index=True)
    oAuthUser_id = db.Column(db.Integer, db.ForeignKey('o_auth_user.id'), index=True)

    entry_post = db.relationship('Entry_Post', backref=db.backref('entry_post_histories', lazy=True))
    oAuthUser = db.relationship('oAuthUser', backref=db.backref('entry_post_histories', lazy=True))

    def __repr__(self):
        return '<Entry_Posts_oAuthUsers {}>'.format(self.id)
