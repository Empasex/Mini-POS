from sqlmodel import Session, select
from app.database import engine
from app.models import User
from app.security import get_password_hash

def create_admin(username="admin", password="admin123"):
    with Session(engine) as session:
        exists = session.exec(select(User).where(User.username == username)).first()
        if exists:
            print("User already exists")
            return
        u = User(username=username, password_hash=get_password_hash(password), role="admin")
        session.add(u)
        session.commit()
        print(f"Created {username} / {password}")

if __name__ == "__main__":
    create_admin()