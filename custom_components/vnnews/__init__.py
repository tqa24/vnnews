"""VN News custom component for Home Assistant."""
import logging
from .const import DOMAIN
from .utils import init_db

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass, config):
    """Set up the VN News component."""
    _LOGGER.info("Khởi tạo VN News component")
    _LOGGER.debug("Bắt đầu thiết lập component VN News")
    init_db()

    # Đăng ký service reload_entry để reload lại từng entry (giống amlich)
    async def reload_entry_service(call):
        entry_id = call.data.get("entry_id")
        if not entry_id:
            _LOGGER.error("Thiếu entry_id khi gọi service reload_entry")
            return
        _LOGGER.info(f"VN News: Reloading config entry {entry_id} by service")
        await hass.config_entries.async_reload(entry_id)

    hass.services.async_register(DOMAIN, "reload_entry", reload_entry_service)
    _LOGGER.debug("Đã đăng ký service reload_entry cho VN News")
    return True


async def _options_update_listener(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass, entry):
    init_db()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {}
    entry.async_on_unload(entry.add_update_listener(_options_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    return True


async def async_unload_entry(hass, entry):
    # Huỷ polling nếu có
    if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
        unsub = hass.data[DOMAIN][entry.entry_id].get("unsub_poll")
        if unsub:
            unsub()
        hass.data[DOMAIN].pop(entry.entry_id)
    # Unload sensor platform
    return await hass.config_entries.async_forward_entry_unload(entry, "sensor")
