from database.database import Base
from sqlalchemy import Column, Integer, String, Boolean, Date, ForeignKey, DateTime, Text, LargeBinary
from sqlalchemy.sql import func
from sqlalchemy.orm import deferred
from sqlalchemy.dialects.mysql import LONGTEXT as MySQL_LONGTEXT
LongText = Text().with_variant(MySQL_LONGTEXT(), "mysql")

class Users(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), unique=True, index=True)
    public_key = Column(String(2000))
    email = Column(String(255), unique=True, index=True)
    phone = Column(String(255), unique=True, index=True)
    first_name = Column(String(255))
    last_name = Column(String(255))
    language = Column(String(255))
    role = Column(String(255))
    manager_id = Column(Integer, ForeignKey("users.id"))
    is_active = Column(Boolean)
    hire_date = Column(Date)
    relive_date = Column(Date)
    created_dt = Column(Date)
    emp_type = Column(String(255))


class Sites(Base):
    __tablename__ = "sites"
    id = Column(Integer, primary_key=True, index=True)
    site_name = Column(String(255), index=True)
    site_description = Column(Text)
    created_date = Column(Date)
    close_date = Column(Date, nullable=True)


class SiteAssignments(Base):
    """User-Site Relationship Table"""
    __tablename__ = "site_assignments"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    site_id = Column(Integer, ForeignKey("sites.id"))
    assigned_date = Column(Date)


class SiteComments(Base):
    """Chat/Comments Table"""
    __tablename__ = "site_comments"
    id = Column(Integer, primary_key=True, index=True)
    site_user_relation_id = Column(Integer, ForeignKey("site_assignments.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    comment = Column(Text)
    image_id = Column(Integer, ForeignKey("images.id"))
    type = Column(String(255))
    timestamp = Column(DateTime, server_default=func.now())

class UserLogs(Base):
    """Stores user login/logout activity"""
    __tablename__ = "user_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    timestamp = Column(DateTime, server_default=func.now())

class PasswordResetTokens(Base):
    """Stores password reset tokens"""
    __tablename__ = "password_reset_tokens"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    token = Column(String(255), unique=True, index=True)
    expires_at = Column(DateTime)
    used = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())


class Images(Base):
    __tablename__ = "images"
    id = Column(Integer, primary_key=True, autoincrement=True)
    file_name = Column(String(255))
    data = deferred(Column(LargeBinary(length=4294967295)))
    format = Column(String(10))
    size = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())

class ImagesTemplate(Base):
    __tablename__ = "images_template"
    id = Column(Integer, primary_key=True, autoincrement=True)
    image_id = Column(Integer, ForeignKey("images.id"), index=True)
    file_name = Column(String(255))
    data = deferred(Column(LongText))
    format = Column(String(10))
    size = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())