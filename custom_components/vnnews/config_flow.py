import voluptuous as vol
import logging
from homeassistant import config_entries
from homeassistant.helpers import selector
from .const import DOMAIN
from .utils import set_gemini_api_key, get_gemini_api_key

_LOGGER = logging.getLogger(__name__)

CONF_GEMINI_API_KEY = "gemini_api_key"
CONF_NEWS_SOURCE = "news_source"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_NEWS_ITEM_COUNT = "news_item_count"

NEWS_SOURCES = {
    "vnexpress": "VNExpress",
    "24h": "24h.com.vn"
}


class VNExpressNewsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        self._pending_data = {}

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        _LOGGER.debug(f"User input: {user_input}")
        if user_input is not None:
            api_key = user_input.get(CONF_GEMINI_API_KEY, "").strip()
            news_source = user_input.get(CONF_NEWS_SOURCE, "vnexpress")
            try:
                scan_interval = int(user_input.get(CONF_SCAN_INTERVAL, 600))
                news_item_count = int(user_input.get(CONF_NEWS_ITEM_COUNT, 10))
            except (ValueError, TypeError) as e:
                _LOGGER.error(f"Invalid input types: {e}")
                errors["base"] = "invalid_input"
            else:
                # Validate inputs
                if not api_key or len(api_key) < 10:
                    errors[CONF_GEMINI_API_KEY] = "invalid_key"
                elif news_source not in NEWS_SOURCES:
                    errors[CONF_NEWS_SOURCE] = "invalid_source"
                elif not (1 <= news_item_count <= 30):
                    errors[CONF_NEWS_ITEM_COUNT] = "invalid_count"
                elif not (1 <= scan_interval <= 600):
                    errors[CONF_SCAN_INTERVAL] = "invalid_interval"
                else:
                    # Check for duplicate configurations
                    unique_id = f"vn_news_{news_source}"
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured()
                    # Store data for confirmation step
                    self._pending_data = {
                        CONF_GEMINI_API_KEY: api_key,
                        CONF_NEWS_SOURCE: news_source,
                        CONF_SCAN_INTERVAL: scan_interval,
                        CONF_NEWS_ITEM_COUNT: news_item_count
                    }
                    _LOGGER.debug(f"Pending data: {self._pending_data}")
                    return await self.async_step_confirm()
        default_api_key = get_gemini_api_key() or ""
        schema = vol.Schema({
            vol.Required(CONF_GEMINI_API_KEY, default=default_api_key): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Required(CONF_NEWS_SOURCE, default="vnexpress"): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[{"value": k, "label": v} for k, v in NEWS_SOURCES.items()],
                    mode=selector.SelectSelectorMode.DROPDOWN
                )
            ),
            vol.Required(CONF_SCAN_INTERVAL, default=600): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1, max=600, step=1, unit_of_measurement="minutes",
                    mode=selector.NumberSelectorMode.BOX
                )
            ),
            vol.Required(CONF_NEWS_ITEM_COUNT, default=10): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1, max=30, step=1, unit_of_measurement="sensors",
                    mode=selector.NumberSelectorMode.BOX
                )
            )
        })
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors
        )

    async def async_step_confirm(self, user_input=None):
        """Handle the confirmation step."""
        if not self._pending_data:
            return await self.async_step_user()
        api_key = self._pending_data[CONF_GEMINI_API_KEY]
        news_source = self._pending_data[CONF_NEWS_SOURCE]
        scan_interval = self._pending_data[CONF_SCAN_INTERVAL]
        news_item_count = self._pending_data[CONF_NEWS_ITEM_COUNT]
        if user_input is not None:
            if user_input.get("confirm"):
                set_gemini_api_key(api_key)
                return self.async_create_entry(
                    title=f"VN News ({NEWS_SOURCES[news_source]})",
                    data={
                        CONF_GEMINI_API_KEY: api_key,
                        CONF_NEWS_SOURCE: news_source,
                        CONF_SCAN_INTERVAL: scan_interval,
                        CONF_NEWS_ITEM_COUNT: news_item_count
                    }
                )
            elif user_input.get("back"):
                return await self.async_step_user()
        schema = vol.Schema({
            vol.Optional("confirm", default=False): selector.BooleanSelector(),
            vol.Optional("back", default=False): selector.BooleanSelector()
        })
        return self.async_show_form(
            step_id="confirm",
            data_schema=schema,
            description_placeholders={
                "api_key_masked": '*' * min(len(api_key), 20) if api_key else '',
                "news_source": NEWS_SOURCES.get(news_source, news_source),
                "scan_interval": str(scan_interval),
                "news_item_count": str(news_item_count)
            }
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        """Return the options flow."""
        return VNExpressNewsOptionsFlowHandler(config_entry)


class VNExpressNewsOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for VN News."""
    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        errors = {}
        current = self.config_entry.options if self.config_entry.options else self.config_entry.data
        _LOGGER.debug(f"Options flow input: {user_input}")
        if user_input is not None:
            api_key = user_input.get(CONF_GEMINI_API_KEY, "").strip()
            try:
                scan_interval = int(user_input.get(CONF_SCAN_INTERVAL, 600))
                news_item_count = int(user_input.get(CONF_NEWS_ITEM_COUNT, 10))
            except (ValueError, TypeError) as e:
                _LOGGER.error(f"Invalid input types: {e}")
                errors["base"] = "invalid_input"
            else:
                if not api_key or len(api_key) < 10:
                    errors[CONF_GEMINI_API_KEY] = "invalid_key"
                elif not (1 <= news_item_count <= 30):
                    errors[CONF_NEWS_ITEM_COUNT] = "invalid_count"
                elif not (1 <= scan_interval <= 600):
                    errors[CONF_SCAN_INTERVAL] = "invalid_interval"
                else:
                    set_gemini_api_key(api_key)
                    return self.async_create_entry(
                        title="",
                        data={
                            CONF_GEMINI_API_KEY: api_key,
                            CONF_NEWS_SOURCE: current.get(CONF_NEWS_SOURCE, "vnexpress"),
                            CONF_SCAN_INTERVAL: scan_interval,
                            CONF_NEWS_ITEM_COUNT: news_item_count
                        }
                    )
        current_api_key = current.get(CONF_GEMINI_API_KEY, get_gemini_api_key() or "")
        schema = vol.Schema({
            vol.Required(CONF_GEMINI_API_KEY, default=current_api_key): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Required(CONF_SCAN_INTERVAL, default=current.get(CONF_SCAN_INTERVAL, 600)): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1, max=600, step=1, unit_of_measurement="minutes",
                    mode=selector.NumberSelectorMode.BOX
                )
            ),
            vol.Required(CONF_NEWS_ITEM_COUNT, default=current.get(CONF_NEWS_ITEM_COUNT, 10)): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1, max=30, step=1, unit_of_measurement="sensors",
                    mode=selector.NumberSelectorMode.BOX
                )
            )
        })
        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors
        )
