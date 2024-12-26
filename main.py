from bs4 import BeautifulSoup
from google.oauth2 import service_account
from googleapiclient.discovery import build
import os
import requests
import time
from datetime import datetime, timedelta
import base64

THSR_URL = "https://www.thsrc.com.tw/ArticleContent/60dbfb79-ac20-4280-8ffb-b09e7c94f043"
SCOPES = ['https://www.googleapis.com/auth/calendar.events']

def get_google_calendar_service():
    """設定 Google Calendar API 認證和服務"""
    service_account_info = base64.b64decode(os.environ['GOOGLE_SERVICE_ACCOUNT'])
    credentials = service_account.Credentials.from_service_account_info(
        eval(service_account_info),
        scopes=SCOPES
    )
    return build('calendar', 'v3', credentials=credentials)

def get_thsr_html():
    """從高鐵網站獲取 HTML 內容"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
    }
    
    max_retries = 3
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            response = requests.get(THSR_URL, headers=headers, timeout=10)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            if attempt == max_retries - 1:
                raise Exception(f"無法從高鐵網站獲取資料: {str(e)}")
            print(f"第 {attempt + 1} 次嘗試失敗，{retry_delay} 秒後重試...")
            time.sleep(retry_delay)

def parse_date(date_str):
    """解析日期字串"""
    return datetime.strptime(date_str.split(' ')[0], '%Y/%m/%d')

def check_existing_event(service, holiday_name, sale_date, calendar_id):
    """檢查是否已存在相同的行事曆事件"""
    sale_date_obj = parse_date(sale_date)
    time_min = sale_date_obj.replace(hour=0, minute=0).isoformat() + 'Z'
    time_max = sale_date_obj.replace(hour=23, minute=59).isoformat() + 'Z'
    
    events_result = service.events().list(
        calendarId=calendar_id,
        timeMin=time_min,
        timeMax=time_max,
        q=f'高鐵{holiday_name}預售票'
    ).execute()
    
    return len(events_result.get('items', [])) > 0

def create_calendar_event(service, holiday_name, sale_date, travel_period, calendar_id):
    """建立 Google 日曆事件"""
    if check_existing_event(service, holiday_name, sale_date, calendar_id):
        print(f"跳過: {holiday_name} 預售票事件已存在")
        return
    
    sale_date_obj = parse_date(sale_date)
    start_time = sale_date_obj.replace(hour=0, minute=0)
    end_time = start_time + timedelta(minutes=30)
    
    event = {
        'summary': f'高鐵{holiday_name}預售票開賣',
        'description': f'疏運期間: {travel_period}\n請準時上網訂票',
        'start': {
            'dateTime': start_time.isoformat(),
            'timeZone': 'Asia/Taipei',
        },
        'end': {
            'dateTime': end_time.isoformat(),
            'timeZone': 'Asia/Taipei',
        },
        'reminders': {
            'useDefault': False,
            'overrides': [
                {'method': 'popup', 'minutes': 1440},
                {'method': 'popup', 'minutes': 60},
                {'method': 'popup', 'minutes': 15},
            ],
        },
    }
    
    try:
        service.events().insert(calendarId=calendar_id, body=event).execute()
        print(f"成功: 已新增 {holiday_name} 預售票事件到行事曆")
    except Exception as e:
        print(f"錯誤: 新增 {holiday_name} 事件失敗 - {str(e)}")

def process_thsr_table(html_content):
    """處理高鐵時刻表 HTML 並加入行事曆"""
    soup = BeautifulSoup(html_content, 'html.parser')
    service = get_google_calendar_service()
    
    # 從環境變數獲取行事曆 ID
    calendar_id = os.environ.get('CALENDAR_ID')
    if not calendar_id:
        raise Exception("未設定行事曆 ID")
    
    # 找到所有符合條件的表格
    tables = soup.find_all('table', {'summary': lambda x: x and '高鐵車票購買日期清單' in x})
    if not tables:
        raise Exception("找不到目標表格")
    
    print(f"找到 {len(tables)} 個時刻表")
    total_processed = 0
    
    # 處理每個表格
    for table_index, table in enumerate(tables, 1):
        print(f"\n處理第 {table_index} 個時刻表:")
        
        # 找到表格的標題（年份）
        caption = table.find('caption')
        year = "未知年份"
        if caption:
            year = caption.text.strip()
        print(f"時刻表年份: {year}")
        
        rows = table.find_all('tr')
        processed_count = 0
        
        # 跳過表頭
        for row in rows[1:]:
            columns = row.find_all(['td'])
            if len(columns) == 3:
                holiday_name = columns[0].text.strip()
                travel_period = columns[1].text.strip()
                sale_date = columns[2].text.strip()
                
                try:
                    create_calendar_event(service, holiday_name, sale_date, travel_period, calendar_id)
                    processed_count += 1
                except Exception as e:
                    print(f"處理 {holiday_name} 時發生錯誤: {str(e)}")
                    continue
        
        print(f"第 {table_index} 個時刻表處理了 {processed_count} 個假期事件")
        total_processed += processed_count
    
    print(f"\n總共處理了 {total_processed} 個假期事件")

def main():
    try:
        print("正在從高鐵網站獲取資料...")
        html_content = get_thsr_html()
        
        print("正在處理資料並新增至Google日曆...")
        process_thsr_table(html_content)
        
    except Exception as e:
        print(f"程式執行發生錯誤: {str(e)}")
        raise

if __name__ == "__main__":
    main()