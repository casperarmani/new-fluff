from database import engine, Base, SessionLocal, User

def test_database_connection():
    try:
        # Try to create a session
        session = SessionLocal()
        print("Successfully connected to the database.")
        
        # Try to create tables
        Base.metadata.create_all(bind=engine)
        print("Tables created successfully.")
        
        # Try to add a test user
        test_user = User(username="test_user", email="test@example.com", hashed_password="hashed_password")
        session.add(test_user)
        session.commit()
        print("Test user added successfully.")
        
        # Clean up
        session.delete(test_user)
        session.commit()
        print("Test user removed.")
        
        session.close()
        return True
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        return False

if __name__ == "__main__":
    test_database_connection()
