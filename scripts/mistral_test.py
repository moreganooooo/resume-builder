import os
from dotenv import load_dotenv
from mistralai import Mistral

# 1. Load the variables from your .env file into the system environment
load_dotenv()

def test_api():
    # 2. Grab the API key that load_dotenv just loaded
    api_key = os.environ.get("MISTRAL_API_KEY")
    
    if not api_key:
        print("❌ Error: Could not find 'MISTRAL_API_KEY' inside your .env file.")
        print("Please double-check that your file is named exactly '.env' and contains: MISTRAL_API_KEY=your_key")
        return

    print("🔄 Connecting to Mistral AI via .env...")
    
    # 3. Initialize the Mistral client
    client = Mistral(api_key=api_key)

    try:
        # 4. Send a tiny request to verify the key works
        response = client.chat.complete(
            model="mistral-large-latest",
            messages=[
                {
                    "role": "user",
                    "content": "Say 'API Key Works!' if you can read this.",
                },
            ]
        )
        
        # 5. Print the successful response
        print("\n✅ Success!")
        print(f"Mistral Response: {response.choices.message.content}")
        
    except Exception as e:
        print("\n❌ API Call Failed!")
        print(f"Error Details: {e}")

if __name__ == "__main__":
    test_api()
