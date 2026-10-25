from app import app, initialize_database


with app.app_context():
    initialize_database()
