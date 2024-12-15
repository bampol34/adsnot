import aiohttp
import asyncio
from concurrent.futures import ThreadPoolExecutor

CONFIG = {
    "api_url_base": "https://notpx.app/api/v1",
    "api_url_event": "https://plausible.joincommunity.xyz/api/event",
    "api_url_adv": "https://api.adsgram.ai",
    "api_url_status": "https://notpx.app/api/v1/mining/status",
    "block_id": "4853",
    "platform": "android",
}

USER_AGENT = ("Mozilla/5.0 (Linux; Android 11; K) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/130.0.6723.108 Mobile Safari/537.36 Telegram-Android/11.4.2 "
              "(Xiaomi M2004J19C; Android 11; SDK 30; AVERAGE)")

SEMAPHORE_LIMIT = 50

async def make_request(session, method, url, headers=None, json=None, semaphore=None, timeout=10):
    async with semaphore:
        try:
            async with session.request(method, url, headers=headers, json=json, timeout=timeout) as response:
                response.raise_for_status()
                if response.content_type == 'application/json':
                    return await response.json()
                else:
                    return await response.text()
        except asyncio.TimeoutError:
            print(f"[ERROR] Request to {url} timed out.")
        except aiohttp.ClientResponseError as e:
            print(f"[ERROR] HTTP Request failed: {e}")
        except Exception as e:
            print(f"[ERROR] An error occurred: {str(e)}")
    return None

async def send_initial_event(session, headers, semaphore):
    url = CONFIG['api_url_event']
    payload = {
        "n": "pageview",
        "u": "https://app.notpx.app/claiming",
        "d": "notpx.app",
        "r": None
    }
    return await make_request(session, 'POST', url, headers=headers, json=payload, semaphore=semaphore)

async def get_user_info(session, headers, semaphore):
    await send_initial_event(session, headers, semaphore)

    url = f"{CONFIG['api_url_base']}/users/me"
    response = await make_request(session, 'GET', url, headers=headers, semaphore=semaphore)
    
    if response and isinstance(response, dict):
        user_data = response
        print("\n=== Account Information ===")
        print(f"User ID     : {user_data.get('id')}")
        print(f"First Name  : {user_data.get('firstName')}")
        print(f"Last Name   : {user_data.get('lastName')}")   
        return user_data
    else:
        print("[ERROR] Failed to retrieve user information.")
        return None

async def fetch_ad_tracking_urls(session, user_id, headers, semaphore):
    adv_url = f"{CONFIG['api_url_adv']}/adv?blockId={CONFIG['block_id']}&tg_id={user_id}&tg_platform={CONFIG['platform']}&platform=Linux+aarch64&language=en&chat_type=sender&chat_instance=4925763693035646361&top_domain=app.notpx.app"
    response = await make_request(session, 'GET', adv_url, headers=headers, semaphore=semaphore)
    if response and isinstance(response, dict):
        trackings = {tracking['name']: tracking['value'] for tracking in response.get('banner', {}).get('trackings', [])}
        return trackings
    else:
        print("[ERROR] Failed to retrieve ad tracking URLs.")
        return None

async def watch_ad(session, user_id, headers, semaphore):
    trackings = await fetch_ad_tracking_urls(session, user_id, headers, semaphore)
    if not trackings:
        return

    pageview_data = {
        "n": "pageview",
        "u": "https://app.notpx.app/claiming",
        "d": "notpx.app",
        "r": None
    }
    if not await make_request(session, 'POST', CONFIG['api_url_event'], headers=headers, json=pageview_data, semaphore=semaphore):
        print("[ERROR] Pageview event failed.")
        return

    await asyncio.sleep(5)

    tasks = []
    for event_type in ['render', 'show', 'reward']:
        if event_type in trackings:
            tasks.append(make_request(session, 'GET', trackings[event_type], headers=headers, semaphore=semaphore))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for event_type, result in zip(['render', 'show', 'reward'], results):
        if result != {}:
            print(f"[ERROR] {event_type.capitalize()} event failed.")

    task_data = {
        "n": "task_adsgram1",
        "u": "https://app.notpx.app/claiming",
        "d": "notpx.app",
        "r": None,
        "p": {"country": "ID", "result": True}
    }
    if not await make_request(session, 'POST', CONFIG['api_url_event'], headers=headers, json=task_data, semaphore=semaphore):
        print("[ERROR] Task completion event failed.")
        return

    print("[SUCCESS] Ad watched successfully. Reward received!")

async def get_user_balance(session, headers, semaphore):
    response = await make_request(session, 'GET', CONFIG['api_url_status'], headers=headers, semaphore=semaphore)
    if response and isinstance(response, dict):
        return response.get('userBalance')
    else:
        print("[ERROR] Failed to retrieve user balance.")
        return None

async def read_initdata_from_file(file_path):
    try:
        with open(file_path, 'r') as file:
            return [line.strip() for line in file.readlines()]
    except FileNotFoundError:
        print(f"[ERROR] File {file_path} not found.")
        return None

async def process_account(session, initdata_value, semaphore):
    headers = {
        'Authorization': f"initData {initdata_value}",
        'User-Agent': USER_AGENT,
        "content-type": "text/plain",
        "sec-ch-ua-platform": '"Android"',
        "sec-ch-ua": '"Chromium";v="130", "Android WebView";v="130", "Not?A_Brand";v="99"',
        "sec-ch-ua-mobile": "?1",
        "accept": "*/*",
        "origin": "https://app.notpx.app",
        "x-requested-with": "org.telegram.messenger",
        "sec-fetch-site": "cross-site",
        "sec-fetch-mode": "cors",
        "sec-fetch-dest": "empty",
        "referer": "https://app.notpx.app/",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "en,en-AU;q=0.9,en-US;q=0.8",
        "priority": "u=1, i",
    }

    user_data = await get_user_info(session, headers, semaphore)
    if user_data:
        user_id = user_data.get('id')

        balance_before = await get_user_balance(session, headers, semaphore)
        await watch_ad(session, user_id, headers, semaphore)
        balance_after = await get_user_balance(session, headers, semaphore)

        if balance_after > balance_before:
            print(f"[SUCCESS] Reward received! New Balance: {balance_after}")
        else:
            print(f"[WARNING] Account ID {user_id} No reward received.")
        
    else:
        print("[ERROR] Skipping account due to errors in retrieving user info.")

async def main():
    initdata_values = await read_initdata_from_file('initdata.txt')
    if not initdata_values:
        print("[ERROR] No initData found in file.")
        return

    semaphore = asyncio.Semaphore(SEMAPHORE_LIMIT)

    connector = aiohttp.TCPConnector(limit_per_host=SEMAPHORE_LIMIT * 2)
    async with aiohttp.ClientSession(connector=connector) as session:
        while True:
            tasks = [
                process_account(session, initdata_value, semaphore)
                for initdata_value in initdata_values
            ]
            await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
