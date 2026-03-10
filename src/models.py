from database.database import Base
from sqlalchemy import Column, Integer, String, Boolean, Date, ForeignKey, DateTime, Text
from sqlalchemy.sql import func

class Users(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    public_key = Column(String)
    email = Column(String, unique=True, index=True)
    phone = Column(String, unique=True, index=True)
    first_name = Column(String)
    last_name = Column(String)
    language = Column(String)
    role = Column(String)
    manager_id = Column(Integer, ForeignKey("users.id"))
    is_active = Column(Boolean)
    hire_date = Column(Date)
    relive_date = Column(Date)
    created_dt = Column(Date)
    emp_type = Column(String)


class Sites(Base):
    __tablename__ = "sites"
    id = Column(Integer, primary_key=True, index=True)
    site_name = Column(String, index=True)
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
    timestamp = Column(DateTime, server_default=func.now())

class UserLogs(Base):
    """Stores user login/logout activity"""
    __tablename__ = "user_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    timestamp = Column(DateTime, server_default=func.now())