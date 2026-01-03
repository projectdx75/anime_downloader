
import asyncio
import zendriver as zd
import sys
import os
import inspect

async def test():
    print("=== Zendriver API Inspection ===")
    
    # Inspect zd.start
    print("\n--- zd.start Signature ---")
    try:
        sig = inspect.signature(zd.start)
        print(sig)
        for param in sig.parameters.values():
            print(f"  {param.name}: {param.default}")
    except Exception as e:
        print(f"Failed to inspect zd.start: {e}")

    # Inspect zd.Config
    print("\n--- zd.Config Attributes ---")
    try:
        config = zd.Config()
        # Filter out dunder methods
        attrs = [a for a in dir(config) if not a.startswith("__")]
        print(attrs)
        
        # Check current values
        for a in attrs:
            try:
                val = getattr(config, a)
                if not callable(val):
                    print(f"  {a} = {val}")
            except:
                pass
    except Exception as e:
        print(f"Failed to inspect zd.Config: {e}")

    print("\n--- Testing Config 3: 'arguments' instead of 'browser_args' ---")
    try:
        # Based on typical Zendriver usage, it might be 'arguments'
        browser = await zd.start(headless=True, no_sandbox=True, arguments=["--no-sandbox", "--disable-dev-shm-usage"])
        print("Success with Config 3 (arguments)!")
        await browser.stop()
    except Exception as e:
        print(f"Config 3 (arguments) Failed: {e}")

if __name__ == "__main__":
    asyncio.run(test())
