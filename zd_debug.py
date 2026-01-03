
import asyncio
import zendriver as zd
import sys
import os

async def test():
    print("Testing Zendriver Startup...")
    print(f"EUID: {os.geteuid()}")
    
    # Check what parameters zendriver Config accepts
    config = zd.Config()
    print(f"Default Config no_sandbox: {getattr(config, 'no_sandbox', 'N/A')}")
    
    try:
        # Try starting with explicit args
        print("Attempting to start browser with no_sandbox=True and explicit --no-sandbox arg...")
        browser = await zd.start(
            headless=True,
            no_sandbox=True,
            browser_args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
        )
        print("Success! Browser started.")
        await browser.stop()
    except Exception as e:
        print(f"Failed to start: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
