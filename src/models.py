from database.database import Base
from sqlalchemy import Column, Integer, String, Boolean, Date

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
    manager_id = Column(Integer)
    is_active = Column(Boolean)
    hire_date = Column(Date)
    relive_date = Column(Date)
    created_dt = Column(Date)
    emp_type = Column(String)