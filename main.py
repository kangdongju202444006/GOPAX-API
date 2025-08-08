import asyncio
asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from datetime import datetime
import base64, hmac, hashlib, requests, json
from telethon import TelegramClient


# ======== 계정 정보 ========
ACCOUNTS = [
    {
        "API_KEY": "키 값",
        "SECRET": "키 값"
    },
    {
        "API_KEY": "키 값",
        "SECRET": "키 값"
    }
]

# ======== 코인 설정 ========
with open(r'파일경로\config.json', encoding='utf-8') as f:
    COIN_CONFIG = json.load(f)
    
    #테스트용
    #COIN_CONFIG = {"JUM-KRW": 210,"MSQ-KRW": 0.07,"SUT-KRW": 0.1}   

    print(COIN_CONFIG)

def is_coin_active(end_date_str):
    if not end_date_str:  # None이나 빈값 등
        return True
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
    today = datetime.today().date()
    return today <= end_date

# ======== Telegram 설정 ========
api_id = '키 값'
api_hash = '해시 값'
client = TelegramClient('session_file', api_id, api_hash)


def get_balance(api_key: str, secret: str, pair: str) -> float:
    """특정 코인의 사용 가능 잔고 조회"""
    coin = pair.split('-')[0]
    nonce = str(datetime.now().timestamp() * 1000)
    method = 'GET'
    path = '/balances'
    
    # 1. 서명 생성
    message = nonce + method + path
    raw_secret = base64.b64decode(secret)
    signature = hmac.new(raw_secret, message.encode(), hashlib.sha512)
    signature_b64 = base64.b64encode(signature.digest()).decode()
    
    # 2. API 요청
    headers = {
        'API-Key': api_key,
        'Signature': signature_b64,
        'Nonce': nonce
    }
    response = requests.get(
        'https://api.gopax.co.kr' + path,
        headers=headers
    )
    
    # 3. 잔고 추출
    if response.status_code == 200:
        for asset in response.json():
            if asset['asset'] == coin:
                return float(asset['avail'])
    return 0.0

def create_order(api_key: str, secret: str, pair: str, side: str, amount: float) -> requests.Response:
    """시장가 주문 실행"""
    nonce = str(datetime.now().timestamp() * 1000)
    method = 'POST'
    path = '/orders'
    
    # 1. 주문 정보 구성
    body = {
        "amount": amount,
        "side": side.lower(),
        "tradingPairName": pair,
        "type": "market"
    }
    
    # 2. 서명 생성
    message = nonce + method + path + json.dumps(body, sort_keys=True)
    raw_secret = base64.b64decode(secret)
    signature = hmac.new(raw_secret, message.encode(), hashlib.sha512)
    signature_b64 = base64.b64encode(signature.digest()).decode()
    
    # 3. API 요청
    headers = {
        'API-Key': api_key,
        'Signature': signature_b64,
        'Nonce': nonce
    }
    return requests.post(
        'https://api.gopax.co.kr' + path,
        headers=headers,
        json=body
    )



async def telegram_auth():
    """텔레그램 인증 처리"""
    await client.connect()
    if not await client.is_user_authorized():
        print("Telegram 인증 필요")
        phone_number = '+8210XXXXXXXXX'  # 본인의 전화번호 입력
        await client.send_code_request(phone_number)
        code = input('인증 코드 입력: ')
        await client.sign_in(phone_number, code)

async def process_account(account: dict, account_idx: int, result_lines: list):
    """계정별 거래 처리"""
    api_key = account["API_KEY"]
    secret = account["SECRET"]
    
    result_lines.append(f"\n🔑 {account_idx+1}번 계정")
    
    for pair, conf in COIN_CONFIG.items():
        qty = conf["amount"]
        end_date = conf.get("end_date")

        if not is_coin_active(end_date):
            result_lines.append(f"⏸️ {pair} 자동매매 종료일 지남(중단)")
            continue  # 종료일 지났으면 건너뜀
        
        try:
            # 1. 현재가 조회
            ticker = requests.get(f'https://api.gopax.co.kr/trading-pairs/{pair}/ticker').json()
            price = float(ticker['ask'])
            
            # 2. 매수 주문
            buy_amount = int(qty * price) if pair.endswith('-KRW') else qty
            buy_res = create_order(api_key, secret, pair, 'buy', buy_amount)
            result_lines.append(f"✅ {pair} 매수: {buy_res.status_code}")
            
            # 3. 잔고 확인
            await asyncio.sleep(2)
            balance = get_balance(api_key, secret, pair)
            
            # 4. 매도 주문
            if balance > 0:
                sell_amount = round(balance * 0.9999,8)
                sell_res = create_order(api_key, secret, pair, 'sell', sell_amount)
                result_lines.append(f"💰 {pair} 매도: {sell_res.status_code} {sell_amount}")
                
        except Exception as e:
            result_lines.append(f"❌ {pair} 오류: {str(e)}")

async def main():
    """메인 비동기 함수"""
    await telegram_auth()
    result_lines = ["🎉 GOPAX 자동 거래 시작 🎉"]
    
    # 모든 계정 순회
    for idx, account in enumerate(ACCOUNTS):
        await process_account(account, idx, result_lines)
        await asyncio.sleep(3)  # 계정 간 간격
    
    # 최종 결과 전송
    try:
        await client.send_message('eventbithumb_bot', '\n'.join(result_lines))
        print("✅ 텔레그램 메시지 전송 완료")
    except Exception as e:
        print(f"❌ 메시지 전송 실패: {e}")

if __name__ == '__main__':
    with client:
        client.loop.run_until_complete(main())  # 이벤트 루프 실행
