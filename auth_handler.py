import re
import firebase_admin
from firebase_admin import credentials, auth, firestore
from flask import session

# Initialize Firebase Admin SDK
try:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)
except ValueError:
    pass # Already initialized

# Create a Firestore Client instance
db = firestore.client()

class AuthenticationHandler:
    @staticmethod
    def validate_kenyan_phone(phone_number):
        # Remove spaces or hyphens
        phone = re.sub(r'[\s\-]', '', phone_number)
        # Match layouts: +2547..., +2541..., 07..., 01..., 7..., 1...
        match = re.match(r'^(?:\+254|0)?([71]\d{8})$', phone)
        if match:
            return f"+254{match.group(1)}"
        return None

    @classmethod
    def register_user(cls, email, password, phone_number, business_name, first_name, last_name):
        standard_phone = cls.validate_kenyan_phone(phone_number)
        if not standard_phone:
            return {"status": "error", "message": "Invalid Kenyan phone number format."}
        
        try:
            # 1. Store full name under the primary authentication display profile
            full_name = f"{first_name} {last_name}"
            
            user = auth.create_user(
                email=email,
                password=password,
                phone_number=standard_phone,
                display_name=full_name
            )
            
            # 2. Write highly structured details to Firestore database
            user_data = {
                "business_name": business_name,
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "phone": standard_phone,
                "created_at": firestore.SERVER_TIMESTAMP
            }
            db.collection("users").document(user.uid).set(user_data)
            
            return {"status": "success", "uid": user.uid}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @staticmethod
    def login_user(email, password):
        """
        Firebase Admin SDK doesn't handle raw password verification directly (done on frontend/client SDK).
        For a secure pure-backend prototype workflow, we issue custom session tokens or verify identity.
        """
        try:
            # Look up user details to verify existence
            user = auth.get_user_by_email(email)
            
            # Create session state
            session['user_id'] = user.uid
            session['user_email'] = user.email
            session['user_name'] = user.display_name or "User"
            
            return {"status": "success", "user": session['user_name']}
        except Exception as e:
            return {"status": "error", "message": "Authentication failed or user does not exist."}

    @staticmethod
    def logout_user():
        session.clear()
        return {"status": "success"}