from datetime import datetime
from . import db

class SystemSetting(db.Model):
    __tablename__ = "system_settings"

    id = db.Column(db.Integer, primary_key=True)
    setting_name = db.Column(db.String(100), unique=True, nullable=False, index=True)
    setting_value = db.Column(db.Text, nullable=False)
    description = db.Column(db.String(255), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @classmethod
    def get(cls, name: str, default=None):
        setting = cls.query.filter_by(setting_name=name).first()
        return setting.setting_value if setting else default

    @classmethod
    def set(cls, name: str, value, description=None):
        setting = cls.query.filter_by(setting_name=name).first()
        if not setting:
            setting = cls(setting_name=name, setting_value=str(value), description=description)
            db.session.add(setting)
        else:
            setting.setting_value = str(value)
            if description:
                setting.description = description
        db.session.commit()
        return setting

    def to_dict(self):
        return {
            "id": self.id,
            "setting_name": self.setting_name,
            "setting_value": self.setting_value,
            "description": self.description or "",
            "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M:%S") if self.updated_at else None
        }

    def __repr__(self):
        return f"<SystemSetting {self.setting_name}={self.setting_value}>"
