import asyncio
import time
import json
import traceback
import sys
from playwright.async_api import async_playwright

async def run_diagnostic():
    report = {
        "vps_environment_test": {},
        "network_test": {},
        "dom_analysis": {},
        "click_strategy_tests": {},
        "console_logs": [],
        "page_errors": [],
        "api_caught": False
    }

    url = 'https://btech.com/en/p/5cdab7d8-9613-4ac8-b869-451d8960521b'

    print("[*] Starting VPS Diagnostic Tool...")
    
    try:
        async with async_playwright() as p:
            print("[*] Launching Chromium...")
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-gpu',
                    '--disable-dev-shm-usage',
                    '--disable-blink-features=AutomationControlled'
                ]
            )
            report["vps_environment_test"]["browser_launch"] = "SUCCESS"
            
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 5000},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            # Listeners
            page.on("console", lambda msg: report["console_logs"].append({"type": msg.type, "text": msg.text}))
            page.on("pageerror", lambda err: report["page_errors"].append(err.message))
            
            api_caught = asyncio.Event()
            async def handle_response(response):
                if "discovery/api/v1/products/" in response.url and "/offers" in response.url:
                    report["network_test"]["api_status_code"] = response.status
                    report["api_caught"] = True
                    try:
                        data = await response.json()
                        report["network_test"]["api_payload_preview"] = str(data)[:300]
                    except:
                        pass
                    api_caught.set()
            page.on("response", handle_response)
            
            print("[*] Navigating to B.TECH...")
            start_time = time.time()
            response = await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            report["network_test"]["page_status"] = response.status if response else "Unknown"
            report["network_test"]["goto_time_sec"] = round(time.time() - start_time, 2)
            
            if response and response.status == 403:
                report["network_test"]["ip_blocked_by_cloudflare"] = True
                print("[!] B.TECH returned 403! Your VPS IP might be blocked.")
            else:
                report["network_test"]["ip_blocked_by_cloudflare"] = False
                
            print("[*] Waiting 5 seconds for React Hydration...")
            await asyncio.sleep(5)
            
            print("[*] Analyzing DOM for button...")
            button = page.locator("text=Compare the best offers").first
            try:
                await button.wait_for(state="attached", timeout=5000)
                report["dom_analysis"]["button_attached"] = True
                report["dom_analysis"]["button_visible"] = await button.is_visible()
                report["dom_analysis"]["button_enabled"] = await button.is_enabled()
                
                # Get the exact HTML of the button to see what it is
                outer_html = await button.evaluate("el => el.outerHTML")
                report["dom_analysis"]["button_html"] = outer_html
                
                # Get its bounding box to see where it rendered on the VPS screen
                box = await button.bounding_box()
                report["dom_analysis"]["bounding_box"] = box
                
            except Exception as e:
                report["dom_analysis"]["button_attached"] = False
                report["dom_analysis"]["error"] = str(e)
                print("[!] Failed to find button in DOM.")

            if report["dom_analysis"].get("button_attached"):
                print("[*] Testing Strategy 1: dispatch_event('click')")
                try:
                    await button.dispatch_event('click')
                    try:
                        await asyncio.wait_for(api_caught.wait(), timeout=3.0)
                        report["click_strategy_tests"]["strategy_1_dispatch_event"] = "SUCCESS"
                        print("[+] Strategy 1 SUCCESS!")
                    except asyncio.TimeoutError:
                        report["click_strategy_tests"]["strategy_1_dispatch_event"] = "FAILED (API Timeout)"
                        print("[-] Strategy 1 FAILED.")
                except Exception as e:
                    report["click_strategy_tests"]["strategy_1_dispatch_event"] = f"ERROR: {str(e)}"
                    print("[-] Strategy 1 ERROR.")

            if not api_caught.is_set() and report["dom_analysis"].get("button_attached"):
                print("[*] Testing Strategy 2: locator.click(force=True)")
                try:
                    await button.click(force=True, timeout=3000)
                    try:
                        await asyncio.wait_for(api_caught.wait(), timeout=3.0)
                        report["click_strategy_tests"]["strategy_2_force_click"] = "SUCCESS"
                        print("[+] Strategy 2 SUCCESS!")
                    except asyncio.TimeoutError:
                        report["click_strategy_tests"]["strategy_2_force_click"] = "FAILED (API Timeout)"
                        print("[-] Strategy 2 FAILED.")
                except Exception as e:
                    report["click_strategy_tests"]["strategy_2_force_click"] = f"ERROR: {str(e)}"
                    print("[-] Strategy 2 ERROR.")

            if not api_caught.is_set():
                print("[*] Testing Strategy 3: JS Bubbler")
                js_bubbler = """
                () => {
                    const el = document.evaluate("//*[contains(text(), 'Compare the best offers')]", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                    if (el) {
                        let curr = el;
                        while (curr && curr !== document.body) {
                            curr.click();
                            curr = curr.parentElement;
                        }
                        return true;
                    }
                    return false;
                }
                """
                try:
                    found = await page.evaluate(js_bubbler)
                    report["click_strategy_tests"]["strategy_3_js_bubbler_found"] = found
                    if found:
                        try:
                            await asyncio.wait_for(api_caught.wait(), timeout=3.0)
                            report["click_strategy_tests"]["strategy_3_js_bubbler"] = "SUCCESS"
                            print("[+] Strategy 3 SUCCESS!")
                        except asyncio.TimeoutError:
                            report["click_strategy_tests"]["strategy_3_js_bubbler"] = "FAILED (API Timeout)"
                            print("[-] Strategy 3 FAILED.")
                except Exception as e:
                    report["click_strategy_tests"]["strategy_3_js_bubbler"] = f"ERROR: {str(e)}"
                    print("[-] Strategy 3 ERROR.")

            await browser.close()
            
    except Exception as e:
        report["vps_environment_test"]["fatal_error"] = traceback.format_exc()
        print("[!!!] FATAL ERROR:", e)

    print("\n" + "="*50)
    print("DIAGNOSTIC REPORT JSON:")
    print("="*50)
    print(json.dumps(report, indent=4))
    print("="*50)
    print("[+] DONE! Please copy the JSON above and paste it here.")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(run_diagnostic())
