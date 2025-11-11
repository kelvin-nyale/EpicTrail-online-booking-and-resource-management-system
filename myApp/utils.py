# import requests
# from datetime import datetime
# import base64
# import os
# from dotenv import load_dotenv

# load_dotenv()  # Load .env variables

# MPESA_CONSUMER_KEY = os.getenv("MPESA_CONSUMER_KEY")
# MPESA_CONSUMER_SECRET = os.getenv("MPESA_CONSUMER_SECRET")
# MPESA_SHORTCODE = os.getenv("MPESA_SHORTCODE")
# MPESA_PASSKEY = os.getenv("MPESA_PASSKEY")
# MPESA_ENVIRONMENT = os.getenv("MPESA_ENVIRONMENT")
# CALLBACK_URL = os.getenv("CALLBACK_URL")

# def get_mpesa_access_token():
#     if MPESA_ENVIRONMENT == "sandbox":
#         url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
#     else:
#         url = "https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"

#     r = requests.get(url, auth=(MPESA_CONSUMER_KEY, MPESA_CONSUMER_SECRET))
#     r.raise_for_status()
#     return r.json()["access_token"]

# def generate_password():
#     timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
#     password = base64.b64encode(f"{MPESA_SHORTCODE}{MPESA_PASSKEY}{timestamp}".encode()).decode("utf-8")
#     return password, timestamp

# def initiate_stk_push(phone, amount, account_reference="Payment", transaction_desc="Payment"):
#     token = get_mpesa_access_token()
#     password, timestamp = generate_password()
#     if MPESA_ENVIRONMENT == "sandbox":
#         url = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
#     else:
#         url = "https://api.safaricom.co.ke/mpesa/stkpush/v1/processrequest"

#     headers = {"Authorization": f"Bearer {token}"}
#     payload = {
#         "BusinessShortCode": MPESA_SHORTCODE,
#         "Password": password,
#         "Timestamp": timestamp,
#         "TransactionType": "CustomerPayBillOnline",
#         "Amount": int(amount),
#         "PartyA": phone,
#         "PartyB": MPESA_SHORTCODE,
#         "PhoneNumber": phone,
#         "CallBackURL": CALLBACK_URL,
#         "AccountReference": account_reference,
#         "TransactionDesc": transaction_desc
#     }

#     r = requests.post(url, json=payload, headers=headers)
#     r.raise_for_status()
#     return r.json()
