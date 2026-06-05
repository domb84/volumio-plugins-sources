import json
import logging
import queue
import signal
import sys
import threading
from pathlib import Path

from includes import api, controls, menu_manager, volumio

CONFIG_PATH = Path("/data/configuration/user_interface/teac-dab-controls/config.json")

logger = logging.getLogger("Teac DAB Controls")
logger.setLevel(logging.DEBUG)
stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.DEBUG)
logger.addHandler(stream_handler)


def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        logger.error("Config file does not exist: %s", config_path)
        raise FileNotFoundError(config_path)

    with config_path.open("r", encoding="utf-8") as config_file:
        return json.load(config_file)


def parse_pin_tuple(raw_value) -> tuple[str, ...]:
    return tuple(str(raw_value).strip().split(","))


def int_value(config_data: dict, key: str) -> int:
    return int(config_data[key]["value"])


def bool_value(config_data: dict, key: str) -> bool:
    raw_value = config_data[key]["value"]
    if isinstance(raw_value, bool):
        return raw_value
    return str(raw_value).strip().lower() in ("1", "true", "yes", "on")


def build_button_config(config_data: dict) -> dict:
    return {
        "btn_enter": parse_pin_tuple(config_data["btn_enter"]["value"]),
        "btn_radio": parse_pin_tuple(config_data["btn_radio"]["value"]),
        "btn_spotify": parse_pin_tuple(config_data["btn_spotify"]["value"]),
        "btn_stop": parse_pin_tuple(config_data["btn_stop"]["value"]),
        "btn_info": parse_pin_tuple(config_data["btn_info"]["value"]),
        "btn_favourite": parse_pin_tuple(config_data["btn_favourite"]["value"]),
        "btn_main_menu": parse_pin_tuple(config_data["btn_main_menu"]["value"]),
        "btn_back": parse_pin_tuple(config_data["btn_back"]["value"]),
    }


def build_skip_button_config(config_data: dict) -> dict:
    return {
        "btn_no_press_channel1": parse_pin_tuple(config_data["btn_no_press_channel1"]["value"]),
        "btn_no_press_channel2": parse_pin_tuple(config_data["btn_no_press_channel2"]["value"]),
    }


def create_threads(
    control_queue: queue.Queue,
    volumio_queue: queue.Queue,
    menu_manager_queue: queue.Queue,
    config_data: dict,
    stop_event: threading.Event,
) -> list[threading.Thread]:
    api_wrapper = api.ApiWrapper(control_queue)

    button_settings = {
        "buttons_clk": int_value(config_data, "buttons_clk"),
        "buttons_miso": int_value(config_data, "buttons_miso"),
        "buttons_mosi": int_value(config_data, "buttons_mosi"),
        "buttons_cs": int_value(config_data, "buttons_cs"),
        "buttons_channel1": int_value(config_data, "buttons_channel1"),
        "buttons_channel2": int_value(config_data, "buttons_channel2"),
        "spi_bus": int_value(config_data, "spi_bus"),
        "spi": bool_value(config_data, "spi"),
        "button_poll_rate": int_value(config_data, "button_poll_rate"),
        "button_debounce_rate": int_value(config_data, "button_debounce_rate"),
        "button_cooldown_rate": int_value(config_data, "button_cooldown_rate"),
        "btn_config": build_button_config(config_data),
        "btn_skip_config": build_skip_button_config(config_data),
        "rot_enc_A": int_value(config_data, "rot_enc_A"),
        "rot_enc_B": int_value(config_data, "rot_enc_B"),
        "lcd_rs": int_value(config_data, "lcd_rs"),
        "lcd_e": int_value(config_data, "lcd_e"),
        "lcd_d4": int_value(config_data, "lcd_d4"),
        "lcd_d5": int_value(config_data, "lcd_d5"),
        "lcd_d6": int_value(config_data, "lcd_d6"),
        "lcd_d7": int_value(config_data, "lcd_d7"),
    }

    return [
        threading.Thread(
            target=controls.controls,
            args=(
                control_queue,
                button_settings["rot_enc_A"],
                button_settings["rot_enc_B"],
                button_settings["buttons_clk"],
                button_settings["buttons_miso"],
                button_settings["buttons_mosi"],
                button_settings["buttons_cs"],
                button_settings["buttons_channel1"],
                button_settings["buttons_channel2"],
                button_settings["spi_bus"],
                button_settings["spi"],
                button_settings["btn_config"],
                button_settings["btn_skip_config"],
                button_settings["button_poll_rate"],
                button_settings["button_debounce_rate"],
                button_settings["button_cooldown_rate"],
                stop_event,
            ),
            name="controls-thread",
        ),
        threading.Thread(
            target=menu_manager.menu_manager,
            args=(
                control_queue,
                volumio_queue,
                menu_manager_queue,
                button_settings["lcd_rs"],
                button_settings["lcd_e"],
                button_settings["lcd_d4"],
                button_settings["lcd_d5"],
                button_settings["lcd_d6"],
                button_settings["lcd_d7"],
                stop_event,
            ),
            name="menu-manager-thread",
        ),
        threading.Thread(
            target=volumio.volumio,
            args=(volumio_queue, menu_manager_queue, stop_event),
            name="volumio-thread",
        ),
        threading.Thread(
            target=api_wrapper.run_app,
            args=("0.0.0.0", 8889, stop_event),
            name="api-thread",
        ),
    ]


def register_signal_handlers(
    shutdown_event: threading.Event,
    menu_manager_queue: queue.Queue,
) -> None:
    def _shutdown_handler(sig, frame):
        logger.info("Caught signal %s, requesting shutdown", sig)
        try:
            menu_manager_queue.put({"clear": ""})
        except Exception:
            logger.exception("Failed to queue shutdown clear message")
        shutdown_event.set()

    signal.signal(signal.SIGTERM, _shutdown_handler)
    signal.signal(signal.SIGINT, _shutdown_handler)


def main() -> None:
    config_data = load_config(CONFIG_PATH)

    control_queue = queue.Queue()
    volumio_queue = queue.Queue()
    menu_manager_queue = queue.Queue()
    shutdown_event = threading.Event()

    register_signal_handlers(shutdown_event, menu_manager_queue)

    threads = create_threads(
        control_queue,
        volumio_queue,
        menu_manager_queue,
        config_data,
        shutdown_event,
    )

    for thread in threads:
        logger.debug("Starting %s", thread.name)
        thread.start()

    logger.info("Teac DAB Controls is running")

    try:
        while not shutdown_event.wait(timeout=1):
            pass
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received, stopping")
        shutdown_event.set()

    logger.info("Shutdown requested, waiting for workers to stop")
    for thread in threads:
        thread.join(timeout=5)
        if thread.is_alive():
            logger.warning("%s did not stop in time", thread.name)

    logger.info("All worker threads stopped, exiting")
    sys.exit(0)


if __name__ == "__main__":
    main()
