from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

from .user import User
from .person import Person, FaceEmbedding
from .camera import Camera
from .event import Event
from .notification import Notification
from .system_setting import SystemSetting
from .restricted_zone import RestrictedZone

__all__ = [
    "db",
    "User",
    "Person",
    "FaceEmbedding",
    "Camera",
    "Event",
    "Notification",
    "SystemSetting",
    "RestrictedZone",
]
