import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector
from .const import DOMAIN
from .utils import set_gemini_api_key, get_gemini_api_key

CONF_GEMINI_API_KEY = "gemini_api_key"
CONF_NEWS_SOURCE = "news_source"
NEWS_SOURCES = {
    "vnexpress": "VNExpress",
    "24h": "24h.com.vn"
}


class VNExpressNewsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            api_key = user_input[CONF_GEMINI_API_KEY]
            news_source = user_input[CONF_NEWS_SOURCE]
            if not api_key or len(api_key) < 10:
                errors[CONF_GEMINI_API_KEY] = "invalid_key"
            elif news_source not in NEWS_SOURCES:
                errors[CONF_NEWS_SOURCE] = "invalid_source"
            else:
                await self.async_set_unique_id(f"vn_news_{news_source}")
                if self._async_current_entries():
                    for entry in self._async_current_entries():
                        if entry.unique_id == f"vn_news_{news_source}":
                            return self.async_abort(
                                reason="already_configured"
                            )
                self._pending_data = {
                    CONF_GEMINI_API_KEY: api_key,
                    CONF_NEWS_SOURCE: news_source
                }
                return await self.async_step_confirm()
        schema = vol.Schema({
            vol.Required(CONF_GEMINI_API_KEY, default=get_gemini_api_key() or ""): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Required(CONF_NEWS_SOURCE, default="vnexpress"): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[{"value": k, "label": v} for k, v in NEWS_SOURCES.items()],
                    mode=selector.SelectSelectorMode.DROPDOWN
                )
            )
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors, description_placeholders={
            "desc": "Nhập API Key và chọn nguồn tin, nhấn Tiếp tục để xác nhận."
        })

    async def async_step_confirm(self, user_input=None):
        api_key = self._pending_data[CONF_GEMINI_API_KEY]
        news_source = self._pending_data[CONF_NEWS_SOURCE]
        errors = {}
        if user_input is not None:
            if user_input.get("confirm"):
                set_gemini_api_key(api_key)
                await self.async_set_unique_id(f"vn_news_{news_source}")
                entry = self.async_create_entry(
                    title=f"VN News ({NEWS_SOURCES[news_source]})",
                    data={
                        CONF_GEMINI_API_KEY: api_key,
                        CONF_NEWS_SOURCE: news_source
                    }
                )
                return entry
            elif user_input.get("back"):
                return await self.async_step_user()
        schema = vol.Schema({
            vol.Optional("confirm", default=False): selector.BooleanSelector(
                selector.BooleanSelectorConfig()
            ),
            vol.Optional("back", default=False): selector.BooleanSelector(
                selector.BooleanSelectorConfig()
            )
        })
        return self.async_show_form(
            step_id="confirm",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "preview": f"""
🔑 **Gemini API Key**: {'*' * len(api_key) if api_key else ''}
📰 **Nguồn tin**: {NEWS_SOURCES.get(news_source, news_source)}

✅ Nhấn Confirm để lưu cấu hình, hoặc Back để sửa lại.
"""
            }
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        return VNExpressNewsOptionsFlowHandler(config_entry)


class VNExpressNewsOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        errors = {}
        current = self.config_entry.options if self.config_entry.options else self.config_entry.data
        if user_input is not None:
            api_key = user_input[CONF_GEMINI_API_KEY]
            if not api_key or len(api_key) < 10:
                errors[CONF_GEMINI_API_KEY] = "invalid_key"
            else:
                set_gemini_api_key(api_key)
                entry = self.async_create_entry(
                    title="Tùy chọn VN News",
                    data={
                        CONF_GEMINI_API_KEY: api_key,
                        CONF_NEWS_SOURCE: current.get(CONF_NEWS_SOURCE, "vnexpress")
                    }
                )
                return entry
        schema = vol.Schema({
            vol.Required(
                CONF_GEMINI_API_KEY,
                default=current.get(
                    CONF_GEMINI_API_KEY,
                    get_gemini_api_key() or ""
                )
            ): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            )
        })
        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "desc": (
                    "Bạn chỉ có thể sửa lại API Key ở đây. "
                    "Nếu muốn thêm nguồn tin, hãy thêm mục mới qua Add Integration."
                )
            }
        )
