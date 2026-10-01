from auth_utils import create_access_token, decode_access_token

token = create_access_token(1, "test@test.com")
print("Token:", token)
payload = decode_access_token(token)
print("Payload:", payload)
