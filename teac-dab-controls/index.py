import queue
import threading
from includes import menu_manager, controls, volumio, api
import logging
import json
import os, sys, time
import signal

logger = logging.getLogger("Teac DAB controls")
logger.setLevel(logging.DEBUG)

def signal_handler(sig, frame):
    logger.debug("Caught signal: %s", sig)
    # Perform cleanup or additional actions if needed
    try:
        menuManagerQ.put({'clear':''})
        time.sleep(3)      
        sys.exit(0)
    except Exception as e:
        logger.debug(f'{e}')
        sys.exit(1)


# Register the signal handler
logger.debug("Registering signal handler")
signal.signal(signal.SIGTERM, signal_handler)

# Specify the path to your JSON configuration file
config_file_path = '/data/configuration/user_interface/teac-dab-controls/config.json'

if os.path.exists(config_file_path):
    logger.info(f'The file {config_file_path} exists. Loading config.')
    # Read the JSON file
    with open(config_file_path, 'r') as file:
        config_data = json.load(file)

else:
    logger.error(f'The file {config_file_path} does not exist. Exiting.')
    exit(1)

# Access button configuration values
buttons_clk = int(config_data['buttons_clk']['value'])
buttons_miso = int(config_data['buttons_miso']['value'])
buttons_mosi = int(config_data['buttons_mosi']['value'])
buttons_cs = int(config_data['buttons_cs']['value'])
buttons_channel1 = int(config_data['buttons_channel1']['value'])
buttons_channel2 = int(config_data['buttons_channel2']['value'])
spi_bus = int(config_data['spi_bus']['value'])
spi = bool(config_data['spi']['value'])

# read button digital values
btn_config = {
    'btn_enter': tuple(map(int, config_data['btn_enter']['value'].split(','))),
    'btn_radio': tuple(map(int, config_data['btn_radio']['value'].split(','))),
    'btn_spotify': tuple(map(int, config_data['btn_spotify']['value'].split(','))),
    'btn_stop': tuple(map(int, config_data['btn_stop']['value'].split(','))),
    'btn_info': tuple(map(int, config_data['btn_info']['value'].split(','))),
    'btn_favourite': tuple(map(int, config_data['btn_favourite']['value'].split(','))),
    'btn_main_menu': tuple(map(int, config_data['btn_main_menu']['value'].split(','))),
    'btn_back': tuple(map(int, config_data['btn_back']['value'].split(',')))
}

btn_skip_config = {
    'btn_no_press_channel1': tuple(map(int, config_data['btn_no_press_channel1']['value'].split(','))),
    'btn_no_press_channel2': tuple(map(int, config_data['btn_no_press_channel2']['value'].split(',')))
}

# Access rotary encoder configuration values
rot_enc_A = int(config_data['rot_enc_A']['value'])
rot_enc_B = int(config_data['rot_enc_B']['value'])

# Access LCD display configuration values
lcd_rs = int(config_data['lcd_rs']['value'])
lcd_e = int(config_data['lcd_e']['value'])
lcd_d4 = int(config_data['lcd_d4']['value'])
lcd_d5 = int(config_data['lcd_d5']['value'])
lcd_d6 = int(config_data['lcd_d6']['value'])
lcd_d7 = int(config_data['lcd_d7']['value'])

# setup queues
controlQ = queue.Queue()
volumioQ = queue.Queue()
menuManagerQ = queue.Queue()

# init api
api_wrapper = api.ApiWrapper(controlQ)


# start threads
t1 = threading.Thread(target=controls.controls, args=(controlQ, rot_enc_A, rot_enc_B, buttons_clk, buttons_miso, buttons_mosi, buttons_cs, buttons_channel1, buttons_channel2, spi_bus, spi, btn_config, btn_skip_config))
t2 = threading.Thread(target=menu_manager.menu_manager, args=(controlQ, volumioQ, menuManagerQ, lcd_rs, lcd_e, lcd_d4, lcd_d5, lcd_d6, lcd_d7))
t3 = threading.Thread(target=volumio.volumio, args=(volumioQ, menuManagerQ,))
t4 = threading.Thread(target=api_wrapper.run_app, args=('0.0.0.0', 8889))

t1.start()
t2.start()
t3.start()
t4.start()