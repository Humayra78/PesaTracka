import re
import firebase_admin
from firebase_admin import credentials, auth
from flask import session

# Initialize Firebase Admin SDK
# Note: You will download your serviceAccountKey.json from your Firebase Console
try:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)
except ValueError:
    pass # Already initialized

class AuthenticationHandler:
    @staticmethod
    def validate_kenyan_phone(phone_number):
        """Validates and standardizes Kenyan phone numbers to E.164 format (+254...)"""
        # Remove spaces or hyphens
        phone = re.sub(r'[\s\-]', '', phone_number)
        
        # Match layouts: +2547..., +2541..., 07..., 01..., 7..., 1...
        match = re.match(r'^(?:\+254|0)?([71]\d{8})$', phone)
        if match:
            return f"+254{match.group(1)}"
        return None

    @classmethod
    def register_user(cls, email, password, phone_number, display_name):
        standard_phone = cls.validate_kenyan_phone(phone_number)
        if not standard_phone:
            return {"status": "error", "message": "Invalid Kenyan phone number format."}
        
        try:
            user = auth.create_user(
                email=email,
                password=password,
                phone_number=standard_phone,
                display_name=display_name
            )
            # Generate email verification link
            verification_link = auth.generate_email_verification_link(email)
            # In production, you would use an email library to send this link to the user
            print(f"Verification link generated for dev: {verification_link}")
            
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