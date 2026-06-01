from langgraph.prebuilt import create_react_agent
from langchain.chat_models import init_chat_model
from langgraph.checkpoint.memory import MemorySaver

from .vectorestore import context_tool
from .prompts import ASSISTANT_SYSTEM_PROMPT
from ..config import settings
from ..ai_models import CLAUDE_MODEL_STANDARD, CLAUDE_PROVIDER, CLAUDE_TEMPERATURE, CLAUDE_MAX_TOKENS_CHAT


llm = init_chat_model(
    CLAUDE_MODEL_STANDARD,
    model_provider=CLAUDE_PROVIDER,
    api_key=settings.ANTHROPIC_API_KEY,
    temperature=CLAUDE_TEMPERATURE,
    max_tokens=CLAUDE_MAX_TOKENS_CHAT,
)

agent_executor = create_react_agent(
    tools=context_tool(),
    model=llm,
    prompt=ASSISTANT_SYSTEM_PROMPT,
    checkpointer=MemorySaver()
)

def chat_loop():
    """Continuous conversation loop with the agent."""
    print("🤖 Bankruptcy Review Assistant")
    print("=" * 50)
    print("Type 'quit' or 'exit' to end the conversation")
    print("Type 'help' for available commands")
    print("=" * 50)
    
    while True:
        try:
            # Get user input
            user_input = input("\n💬 You: ").strip()
            
            # Check for exit commands
            if user_input.lower() in ['quit', 'exit', 'bye']:
                print("👋 Goodbye! Have a great day!")
                break
            
            # Check for help command
            if user_input.lower() == 'help':
                print("\n📚 Available Commands:")
                print("  - Type any question about bankruptcy or legal matters")
                print("  - The assistant will use the vectorstore to find relevant information")
                print("  - Type 'quit', 'exit', or 'bye' to end the conversation")
                print("  - Type 'help' to see this message again")
                continue
            
            # Skip empty input
            if not user_input:
                continue
            
            print("🤔 Thinking...")
            
            # Run the agent
            response = agent_executor.invoke({
                "messages": [
                    {"role": "user", "content": user_input}
                ]},
                config={"configurable": {"thread_id": "abc123"}}
                )
            
            # Display the response directly for debugging
            print(f"\n🤖 Assistant Response:")
            print(f"Response type: {type(response)}")
            print(f"Response content: {response}")
            
            # Also try to extract AI response if possible
            if hasattr(response, 'content'):
                print(f"\n📝 Extracted content: {response.content}")
            elif isinstance(response, dict) and "messages" in response:
                print(f"\n📝 Messages found: {len(response['messages'])}")
                for i, msg in enumerate(response["messages"]):
                    print(f"  Message {i}: {type(msg)} - {msg}")
            
        except KeyboardInterrupt:
            print("\n\n👋 Interrupted by user. Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {str(e)}")
            print("Please try again or type 'quit' to exit.")

if __name__ == "__main__":
    # Run the test when script is executed directly
    chat_loop()



