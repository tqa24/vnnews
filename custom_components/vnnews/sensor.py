import feedparser
import aiohttp
from bs4 import BeautifulSoup
import time
import requests
from datetime import datetime, timedelta
import logging
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.event import async_track_time_interval
from .const import DOMAIN
from .utils import get_latest_news, add_or_update_news, delete_old_news, get_gemini_api_key, mark_all_old
import asyncio

CONF_GEMINI_API_KEY = "gemini_api_key"
CONF_NEWS_SOURCE = "news_source"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_NEWS_ITEM_COUNT = "news_item_count"

NEWS_RSS_URLS = {
    "vnexpress": "https://vnexpress.net/rss/tin-moi-nhat.rss",
    "24h": "https://cdn.24h.com.vn/upload/rss/tintuctrongngay.rss"
}

_LOGGER = logging.getLogger(__name__)

MAX_TITLES = 200
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"


def summarize_with_gemini(api_key, content, max_length=40):
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key
    }
    prompt = (
        f"Tóm tắt nội dung sau thành tối đa {max_length} từ bằng tiếng Việt."
        "nếu vượt quá 40 từ yêu cầu tóm tắt lại tiếp:\n\n"
        f"{content}"
    )
    data = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "response_mime_type": "text/plain"
        }
    }
    try:
        response = requests.post(GEMINI_API_URL, headers=headers, json=data, timeout=30)
        if response.status_code == 200:
            return response.json()['candidates'][0]['content']['parts'][0]['text'].strip()
        else:
            return f"Lỗi Gemini API: {response.status_code} - {response.text}"
    except Exception as e:
        return f"Lỗi khi gọi Gemini API: {str(e)}"


async def summarize_content_async(api_key, content, max_length=40):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, summarize_with_gemini, api_key, content, max_length)


def count_words(text):
    return len(text.split())


async def fetch_full_article(url, published_time=None, session=None, news_source="vnexpress"):
    _LOGGER.debug(f"Lấy bài báo: {url}")
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        async with session.get(url, headers=headers, timeout=10) as response:
            response.raise_for_status()
            text = await response.text()
            soup = BeautifulSoup(text, 'html.parser')
            if news_source == "24h":
                # Lấy title
                title_tag = soup.find('h1') or soup.find('title')
                title_text = title_tag.get_text(strip=True) if title_tag else 'Không tìm thấy tiêu đề'
                # Lấy nội dung bài báo
                article = soup.find("article", class_="cate-24h-foot-arti-deta-info")
                if article:
                    content_text = "\n".join(
                        p.get_text(strip=True)
                        for p in article.find_all("p")
                        if not p.get("class") or "img_chu_thich_0407" not in p.get("class")
                    )
                else:
                    content_text = "Không tìm thấy nội dung"
            else:
                title = (
                    soup.find('h1', class_='title-detail') or
                    soup.find('h1', class_='title-news') or
                    soup.find('h1', class_='title-page detail') or
                    soup.find('title')
                )
                title_text = title.get_text(strip=True) if title else 'Không tìm thấy tiêu đề'
                content = (
                    soup.find('article', class_='fck_detail') or
                    soup.find('div', class_='podcast-content')
                )
                content_text = (
                    '\n'.join(
                        p.get_text(strip=True)
                        for p in content.find_all('p')
                        if p.get_text(strip=True)
                    ) if content else 'Không tìm thấy nội dung'
                )
                if "Liên hệ:" in content_text:
                    content_text = content_text.split("Liên hệ:")[0].strip()
            article_time = published_time if published_time else time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())
            _LOGGER.debug(f"Lấy thành công: {title_text}")
            return {
                'title': title_text,
                'time': article_time,
                'content': content_text,
                'link': url
            }
    except Exception as e:
        _LOGGER.error(f"Lỗi lấy bài báo: {e}")
        return {
            'title': 'Lỗi',
            'time': time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime()),
            'content': f"Không thể lấy nội dung: {str(e)}",
            'link': url
        }


def get_rss_url(news_source):
    return NEWS_RSS_URLS.get(news_source, NEWS_RSS_URLS["vnexpress"])


async def fetch_rss_and_update_db(api_key, news_source="vnexpress", num_articles=30):
    _LOGGER.debug(f"Lấy tin từ RSS ({news_source}) và cập nhật DB")
    try:
        rss_url = get_rss_url(news_source)
        async with aiohttp.ClientSession() as session:
            async with session.get(rss_url, timeout=10) as response:
                response.raise_for_status()
                rss_content = await response.text()

            def parse_rss_sync():
                return feedparser.parse(rss_content)
            feed = await asyncio.get_event_loop().run_in_executor(None, parse_rss_sync)
            articles = feed.entries
            count_new = 0
            db_news = get_latest_news(500, source=news_source)
            db_titles = set(n['title'] for n in db_news)
            mark_all_old(source=news_source)
            for article in articles[:num_articles]:
                link = article.get('link', '')
                published_time = article.get('published', None)
                if published_time:
                    try:
                        published_time = (
                            datetime.strptime(
                                published_time,
                                '%a, %d %b %Y %H:%M:%S %z'
                            ).strftime('%Y-%m-%d %H:%M:%S')
                        )
                    except ValueError:
                        published_time = None
                title = article.get('title', 'Không tìm thấy tiêu đề')
                if title not in db_titles:
                    full_article = await fetch_full_article(link, published_time, session, news_source=news_source)
                    if full_article['title'] != 'Lỗi':
                        summary = (
                            await summarize_content_async(api_key, full_article['content'])
                            if full_article['content'] else 'Không có nội dung'
                        )
                        new_entry = {
                            'title': title,
                            'time': full_article['time'],
                            'content': full_article['content'],
                            'summary': summary,
                            'link': link,
                            'is_new': 1,
                            'source': news_source
                        }
                        add_or_update_news(new_entry)
                        count_new += 1
                        db_titles.add(title)
            delete_old_news(MAX_TITLES, source=news_source)
            _LOGGER.info(f"Đã cập nhật {count_new} tin mới vào DB")
            return count_new
    except Exception as e:
        _LOGGER.error(f"Lỗi lấy tin RSS: {e}")
        return 0


async def async_setup_entry(hass, config_entry, async_add_entities):
    options = config_entry.options if config_entry.options else config_entry.data
    api_key = options.get(CONF_GEMINI_API_KEY) or get_gemini_api_key()
    news_source = options.get(CONF_NEWS_SOURCE, "vnexpress")
    scan_interval = int(options.get(CONF_SCAN_INTERVAL, 600))
    news_item_count = int(options.get(CONF_NEWS_ITEM_COUNT, 10))
    if not api_key:
        _LOGGER.error("Chưa cấu hình Gemini API Key!")
        return
    hass.data.setdefault(DOMAIN, {})[config_entry.entry_id] = {
        CONF_NEWS_ITEM_COUNT: news_item_count
    }
    sensor = VNExpressNewsSensor(api_key, news_source)
    sensors = [sensor]
    for i in range(1, news_item_count + 1):
        sensors.append(NewsItemSensor(news_source, i))
    async_add_entities(sensors)
    _LOGGER.debug(f"Added {len(sensors)} sensors for news_source: {news_source}")

    # Tạo polling riêng cho entry này
    async def _entry_update(now=None):
        await sensor.async_update()
        for s in sensors[1:]:
            await s.async_update()
    hass.data[DOMAIN][config_entry.entry_id]["unsub_poll"] = async_track_time_interval(
        hass, _entry_update, timedelta(minutes=scan_interval)
    )
    # Không gọi cập nhật lần đầu ở đây nữa để tránh double update
    # await _entry_update()


class VNExpressNewsSensor(SensorEntity, RestoreEntity):
    _attr_should_poll = False
    entity_registry_enabled_default = True

    def __init__(self, api_key, news_source):
        self._api_key = api_key
        self._news_source = news_source
        self._state = "Không có tin mới"
        self._attr_name = f"{news_source.upper()} News"
        self._attr_unique_id = f"vn_news_sensor_{news_source}"
        self._attr_icon = "mdi:newspaper"
        self._new_count = 0
        self._last_update = None
        self._attributes = {}
        self._hass = None
        self._entry_id = None

    async def async_added_to_hass(self):
        self._hass = self.hass
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if entry.unique_id == f"vn_news_{self._news_source}":
                self._entry_id = entry.entry_id
                _LOGGER.debug(f"Found config entry_id: {self._entry_id} for news_source: {self._news_source}")
                break
        if not self._entry_id:
            _LOGGER.error(f"Could not find config entry for news_source: {self._news_source}")
        self.async_schedule_update_ha_state(force_refresh=True)

    async def async_update(self):
        _LOGGER.info(f"Cập nhật sensor News ({self._news_source}) (sqlite)")
        count_new = await fetch_rss_and_update_db(self._api_key, self._news_source)
        self._new_count = count_new
        self._last_update = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        news_list = get_latest_news(30, source=self._news_source)
        news_list = sorted(
            news_list,
            key=lambda x: (
                0 if x.get('is_new', False) else 1,
                -datetime.strptime(x['time'], '%Y-%m-%d %H:%M:%S').timestamp()
            )
        )
        attributes = {}
        for i, news in enumerate(news_list, 1):
            padded_index = f"{i:02d}"
            key = f"Tin {padded_index} (Tin mới)" if news.get('is_new', False) else f"Tin {padded_index}"
            attributes[key] = f"Tiêu Đề: {news['title']}\nNội Dung: {news['summary']}"
        attributes["tin_moi"] = self._new_count
        attributes["cap_nhat_luc"] = self._last_update
        attributes["nguon_tin"] = self._news_source
        self._attributes = attributes
        self._state = f"Có {count_new} tin mới" if count_new > 0 else "Không có tin mới"

        if self._hass and self._entry_id:
            news_item_count = int(self._hass.data.get(DOMAIN, {}).get(self._entry_id, {}).get(CONF_NEWS_ITEM_COUNT, 10))
            _LOGGER.debug(f"Updating {news_item_count} NewsItemSensors for {self._news_source}")
            for i in range(1, news_item_count + 1):
                entity_id = f"sensor.tin_{i}_{self._news_source}"
                await self._hass.services.async_call(
                    "homeassistant",
                    "update_entity",
                    {"entity_id": entity_id},
                    blocking=False
                )
        else:
            _LOGGER.warning(f"Cannot update NewsItemSensors: hass or entry_id not set for {self._news_source}")

    @property
    def state(self):
        return self._state

    @property
    def extra_state_attributes(self):
        return self._attributes

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, f"vn_news_{self._news_source}")},
            "name": f"News ({self._news_source})",
            "manufacturer": "smarthomeblack",
            "model": "News Aggregator",
            "entry_type": "service"
        }


class NewsItemSensor(SensorEntity):
    _attr_should_poll = False
    entity_registry_enabled_default = True

    def __init__(self, news_source, index, news_data=None):
        self._news_source = news_source
        self._index = index
        self._attr_name = f"Tin {index} ({news_source})"
        self._attr_unique_id = f"vn_news_{news_source}_item_{index}"
        self._attr_icon = "mdi:newspaper-variant-outline"
        self._state = None
        self._news_data = news_data or {}

    async def async_added_to_hass(self):
        self.async_schedule_update_ha_state(force_refresh=True)

    async def async_update(self):
        # Lấy tất cả tin từ DB, ưu tiên is_new==1, thiếu thì lấy tin cũ, tất cả theo time mới nhất
        all_news = get_latest_news(60, source=self._news_source)
        news_moi = [n for n in all_news if n.get('is_new', 0) == 1]
        news_cu = [n for n in all_news if n.get('is_new', 0) != 1]
        news_moi = sorted(news_moi, key=lambda x: -datetime.strptime(x['time'], '%Y-%m-%d %H:%M:%S').timestamp())
        news_cu = sorted(news_cu, key=lambda x: -datetime.strptime(x['time'], '%Y-%m-%d %H:%M:%S').timestamp())
        news_list = news_moi + news_cu
        if len(news_list) >= self._index:
            summary = news_list[self._index - 1]['summary']
            self._state = summary[:255] if summary else ""
        else:
            summary = news_list[-1]['summary'] if news_list else ""
            self._state = summary[:255] if summary else "Không có dữ liệu"

    @property
    def state(self):
        return self._state

    @property
    def extra_state_attributes(self):
        return {}

    @property
    def device_info(self):
        # Đặt tên thiết bị đúng như cảm biến tổng
        source_label = self._news_source
        if source_label == "vnexpress":
            source_label = "VNExpress"
        elif source_label == "24h":
            source_label = "24h.com.vn"
        return {
            "identifiers": {(DOMAIN, f"vn_news_{self._news_source}")},
            "name": f"VN News ({source_label})",
            "manufacturer": "smarthomeblack",
            "model": "Việt Nam News",
            "entry_type": "service"
        }
