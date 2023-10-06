import queue
import threading
from includes import menu_manager, controls, volumio
import logging
import json
import os

logger = logging.getLogger("Teac DAB controls")
logger.setLevel(logging.WARNING)
logging.basicConfig()

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

controlQ = queue.Queue()
volumioQ = queue.Queue()
menuManagerQ = queue.Queue()

t1 = threading.Thread(target=controls.controls, args=(controlQ, rot_enc_A, rot_enc_B, buttons_clk, buttons_miso, buttons_mosi, buttons_cs, buttons_channel1, buttons_channel2))
t2 = threading.Thread(target=menu_manager.menu_manager, args=(controlQ, volumioQ, menuManagerQ, lcd_rs, lcd_e, lcd_d4, lcd_d5, lcd_d6, lcd_d7))
t3 = threading.Thread(target=volumio.volumio, args=(volumioQ, menuManagerQ,))

t1.start()
t2.start()
t3.start()

controlQ.join()
volumioQ.join()
menuManagerQ.join()