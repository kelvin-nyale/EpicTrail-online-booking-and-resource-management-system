# myApp/mpesa.py
import requests
import base64
from requests.auth import HTTPBasicAuth
from django.conf import settings
from datetime import datetime


# def get_mpesa_access_token():
#     token_url = f"{settings.MPESA_BASE_URL}/oauth/v1/generate?grant_type=client_credentials"
#     response = requests.get(
#         token_url,
#         auth=HTTPBasicAuth(settings.MPESA_CONSUMER_KEY, settings.MPESA_CONSUMER_SECRET)
#     )
#     response.raise_for_status()
#     access_token = response.json()["access_token"]
#     return access_token
def get_mpesa_access_token():
    url = f"{settings.MPESA_BASE_URL}/oauth/v1/generate?grant_type=client_credentials"
    response = requests.get(url, auth=HTTPBasicAuth(settings.MPESA_CONSUMER_KEY, settings.MPESA_CONSUMER_SECRET))
    data = response.json()
    return data['access_token']


def generate_stk_password():
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    password = base64.b64encode(
        f"{settings.MPESA_SHORTCODE}{settings.MPESA_PASSKEY}{timestamp}".encode()
    ).decode('utf-8')
    return password, timestamp


def initiate_stk_push(phone, amount, account_reference="EpicTrail Adventures", transaction_desc="Payment"):
    """
    Initiate Lipa na M-Pesa Online STK Push
    """
    password, timestamp = generate_stk_password()
    access_token = get_mpesa_access_token()

    stk_url = f"{settings.MPESA_BASE_URL}/mpesa/stkpush/v1/processrequest"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    payload = {
        "BusinessShortCode": settings.MPESA_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": float(amount),  # <-- Convert Decimal to float
        "PartyA": phone,
        "PartyB": settings.MPESA_SHORTCODE,
        "PhoneNumber": phone,
        "CallBackURL": settings.CALLBACK_URL,
        "AccountReference": account_reference,
        "TransactionDesc": transaction_desc,
    }

    response = requests.post(stk_url, json=payload, headers=headers)
    return response.json()

