
import asyncio
import zendriver as zd
import sys
import os
import subprocess

async def test():
    print("=== Zendriver Final Stand Debug ===")
    
    browser_bin = "/bin/chromium-browser"
    if not os.path.exists(browser_bin):
        browser_bin = "/usr/bin/chromium-browser"
    
    print(f"Testing browser binary: {browser_bin}")
    
    # 1. Try to run browser version check
    try:
        print("\n--- Checking Browser Version ---")
        out = subprocess.check_output([browser_bin, "--version"], stderr=subprocess.STDOUT).decode()
        print(f"Version output: {out}")
    except Exception as e:
        print(f"Version check failed: {e}")
        if hasattr(e, 'output'):
            print(f"Error output: {e.output.decode()}")

    # 2. Try to run browser with minimum flags to see if it crashes
    print("\n--- Direct Subprocess Start Test (Headless + No Sandbox) ---")
    try:
        # Just try to get help or something that starts the engine
        cmd = [browser_bin, "--headless", "--no-sandbox", "--disable-gpu", "--remote-debugging-port=9222", "--about:blank"]
        print(f"Running: {' '.join(cmd)}")
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        await asyncio.sleep(3)
        if proc.poll() is None:
            print(">>> SUCCESS: Browser process is ALIVE after 3 seconds!")
            proc.terminate()
        else:
            stdout, stderr = proc.communicate()
            print(f"FAIL: Browser process DIED instantly (code {proc.returncode})")
            print(f"STDOUT: {stdout.decode()}")
            print(f"STDERR: {stderr.decode()}")
    except Exception as e:
        print(f"Process start test failed: {e}")

    # 3. Last try with Zendriver and absolute bare settings
    print("\n--- Zendriver Barebones Test ---")
    try:
        browser = await zd.start(
            browser_executable_path=browser_bin,
            headless=True,
            sandbox=False,
            browser_args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        print(">>> SUCCESS: Zendriver connected!")
        await browser.stop()
    except Exception as e:
        print(f"Zendriver test failed: {e}")

if __name__ == "__main__":
    asyncio.run(test())
