from mistralai import Mistral

client = Mistral(api_key="HtxRNKpTEWLLeItdYokmbvBMP6cmx8Kd")

response = client.chat.complete(
    model="mistral-small-latest",
    messages=[{"role": "user", "content": "Hello!"}]
)
print(response.choices[0].message.content)