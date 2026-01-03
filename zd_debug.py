
import asyncio
import zendriver as zd
import sys
import os
import subprocess

async def test():
    print("=== Zendriver Google Chrome Debug (v0.5.14) ===")
    
    # Check possible paths
    bin_paths = ["/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium-browser"]
    
    for browser_bin in bin_paths:
        if not os.path.exists(browser_bin):
            continue
            
        print(f"\n>>> Testing binary: {browser_bin}")
        
        # 1. Version Check
        try:
            out = subprocess.check_output([browser_bin, "--version"], stderr=subprocess.STDOUT).decode()
            print(f"Version: {out.strip()}")
        except Exception as e:
            print(f"Version check failed: {e}")
            if hasattr(e, 'output'):
                print(f"Output: {e.output.decode()}")

        # 2. Minimum execution test (Headless + No Sandbox)
        print("--- Direct Execution Test ---")
        try:
            cmd = [browser_bin, "--headless", "--no-sandbox", "--disable-gpu", "--user-data-dir=/tmp/test_chrome", "--about:blank"]
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            await asyncio.sleep(3)
            if proc.poll() is None:
                print("SUCCESS: Browser process is alive!")
                proc.terminate()
            else:
                stdout, stderr = proc.communicate()
                print(f"FAIL: Browser process died (code {proc.returncode})")
                print(f"STDERR: {stderr.decode()}")
        except Exception as e:
            print(f"Execution test failed: {e}")

        # 3. Zendriver Test
        print("--- Zendriver Integration Test ---")
        try:
            browser = await zd.start(
                browser_executable_path=browser_bin,
                headless=True,
                sandbox=False
            )
            print("SUCCESS: Zendriver connected!")
            await browser.stop()
            # If we found one that works, we can stop
            print("\n!!! This path works. Set this in the plugin settings or leave empty if it is the first found.")
        except Exception as e:
            print(f"Zendriver failed: {e}")

if __name__ == "__main__":
    asyncio.run(test())
