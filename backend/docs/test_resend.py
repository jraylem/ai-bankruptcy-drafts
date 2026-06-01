import os
import resend

# Set your API key
# resend.api_key = os.getenv("RESEND_API_KEY")
# OR directly:
resend.api_key = "re_4tFEm1sH_D1PBB7wdv2e1m546EipyfLfk"

try:
    response = resend.Emails.send({
        "from": "testing@test.bkdrafts.ai",
        "to": ["ralphl@vanhornlawgroup.com"],
        "subject": "Resend API Test",
        "html": """
        <h1>Test Email</h1>
        <p>Your Resend API is working correctly.</p>
        """,
    })

    print("Email sent successfully!")
    print(response)

except Exception as e:
    print("Error sending email:")
    print(e)