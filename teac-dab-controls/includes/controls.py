import RPi.GPIO as GPIO
import pigpio
import spidev
import time
import logging
logger = logging.getLogger("Controls")
logger.setLevel(logging.WARNING)
# Create a handler that prints to console
ch = logging.StreamHandler()
ch.setLevel(logging.WARNING)
logger.addHandler(ch)

class controls:

    def __init__(self, controlQ=None, encA=17, encB=27, butClk=11, butDOUT=9, butDIN=10, butCS=22, but1=0, but2=7, spi_bus=1, spi=True, btn_config=None, btn_skip_config=None, button_poll_rate=10, button_debounce_rate=50, button_cooldown_rate=500):
        logger.debug("Loading controls")
        self.controlQ = controlQ

        self.rotary_encoder(encA,encB)

        if spi:
            logger.debug('SPI mode')
            self.buttons_spi(spi_bus,butCS,but1,but2,btn_config, btn_skip_config)

        else:
            logger.debug('Software mode')
            self.buttons(butClk,butDOUT,butDIN,butCS,but1,but2,btn_config, btn_skip_config, button_poll_rate, button_debounce_rate, button_cooldown_rate)


    def normalize_value(self, value, min_value, max_value, target_range):
        normalized_value = 1 - (value - min_value) / (max_value - min_value)
        scaled_value = normalized_value * target_range
        return int(scaled_value)

    def rotary_encoder(self,encA,encB):
        # setup rotary encoder variables for pigpio
        # BE SURE TO START PIGPIO IN PWM MODE 't -0'
        Enc_A = encA  # Encoder input A: input GPIO 17
        Enc_B = encB  # Encoder input B: input GPIO 27

        # set globals for encoder
        self.last_A = 1
        self.last_B = 1
        self.last_gpio = 0



        def rotary_interrupt(gpio, level, tim):
            if gpio == Enc_A:
                self.last_A = level
            else:
                self.last_B = level

            if gpio != self.last_gpio:  # debounce
                self.last_gpio = gpio
                if gpio == Enc_A and level == 1:
                    if self.last_B == 1:
                        logger.debug('Menu down')
                        self.controlQ.put({'control':'menu_down'})
                elif gpio == Enc_B and level == 1:
                    if self.last_A == 1:
                        logger.debug('Menu up')
                        self.controlQ.put({'control':'menu_up'})


        # setup rotary encoder in pigpio
        pi = pigpio.pi()  # init pigpio deamon
        pi.set_mode(Enc_A, pigpio.INPUT)
        pi.set_pull_up_down(Enc_A, pigpio.PUD_UP)
        pi.set_mode(Enc_B, pigpio.INPUT)
        pi.set_pull_up_down(Enc_B, pigpio.PUD_UP)
        pi.callback(Enc_A, pigpio.EITHER_EDGE, rotary_interrupt)
        pi.callback(Enc_B, pigpio.EITHER_EDGE, rotary_interrupt)

        logger.info('Rotary thread start successfully, listening for turns')

    def buttons(self, butClk, butDOUT, butDIN, butCS, but1, but2, btn_config, btn_skip_config, button_poll_rate, button_debounce_rate, button_cooldown_rate):
        CLK = butClk
        DOUT = butDOUT
        DIN = butDIN
        CS = butCS

        channels = [but1, but2]

        button_poll_rate /= 1000
        button_debounce_rate /= 1000  
        button_cooldown_rate /= 1000

        button_states = {
            channel: {
                "last_value": None,
                "stable_since": None,
                "last_sent": 0  # Track last time the button was activated
            } 
            for channel in channels
        }

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(CLK, GPIO.OUT)
        GPIO.setup(DOUT, GPIO.IN)
        GPIO.setup(DIN, GPIO.OUT)
        GPIO.setup(CS, GPIO.OUT)

        def read_mcp3008(channel):
            GPIO.output(CS, GPIO.LOW)
            command = channel | 0x18
            command <<= 3  

            for _ in range(5):
                GPIO.output(DIN, GPIO.HIGH if command & 0x80 else GPIO.LOW)
                command <<= 1
                GPIO.output(CLK, GPIO.HIGH)
                GPIO.output(CLK, GPIO.LOW)

            value = 0
            for _ in range(10):
                GPIO.output(CLK, GPIO.HIGH)
                GPIO.output(CLK, GPIO.LOW)
                value <<= 1
                if GPIO.input(DOUT):
                    value |= 0x1

            GPIO.output(CS, GPIO.HIGH)
            return value

        while True:
            batch_data = [read_mcp3008(channel) for channel in channels]

            for data, channel in zip(batch_data, channels):
                data = self.normalize_value(data, 0, 1024, 32)
                state = button_states[channel]

                if data != state["last_value"]:
                    state["stable_since"] = time.time()
                    state["last_value"] = data
                elif time.time() - state["stable_since"] >= button_debounce_rate:
                    current_time = time.time()
                    
                    # Skip if within cooldown period
                    if current_time - state["last_sent"] < button_cooldown_rate:
                        continue

                    logger.debug(f"Channel {channel} stable value: {data}")

                    for btn, (btn_channel, btn_data) in btn_skip_config.items():
                        btn_data_values = btn_data.split("-")
                        if len(btn_data_values) == 2:
                            lower_value, upper_value = sorted(map(int, btn_data_values))
                            btn_channel = int(btn_channel)

                            if btn_channel == channel and lower_value <= data <= upper_value:
                                break
                        else:
                            if int(btn_channel) == channel and int(btn_data_values[0]) == data:
                                break
                    else:
                        for btn, (btn_channel, btn_data) in btn_config.items():
                            btn_data_values = btn_data.split("-")
                            if len(btn_data_values) == 2:
                                lower_value, upper_value = sorted(map(int, btn_data_values))
                                btn_channel = int(btn_channel)

                                if btn_channel == channel and lower_value <= data <= upper_value:
                                    self.controlQ.put({'control': btn})
                                    state["last_sent"] = current_time  # Update last sent time
                                    break
                            else:
                                if int(btn_channel) == channel and int(btn_data_values[0]) == data:
                                    self.controlQ.put({'control': btn})
                                    state["last_sent"] = current_time  # Update last sent time
                                    break
                        else:
                            logger.warning(f"Uncaught press on Channel {channel}: {data}")

            time.sleep(button_poll_rate)

    ## TODO: Add debounce and poll rate support
    def buttons_spi(self,spi_bus,butCS,but1,but2,btn_config,btn_skip_config):
        # Define MCP3008 pins
        spi = spidev.SpiDev()
        spi.open(0, spi_bus)  # Open SPI bus X, device 0
        spi.max_speed_hz = 1000000  # Set SPI speed (1 MHz)

        # Set up GPIO for chip select (CS)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(butCS, GPIO.OUT)

        # channels to read from MCP 3008
        channels = [but1, but2]

        # Define function to read data from MCP3008
        def read_mcp3008(channel):
            # Set CS low to start the conversion
            GPIO.output(butCS, GPIO.LOW)

            # MCP3008 expects a 10-bit command for single-ended mode
            command = [1, 8 + channel << 4, 0]  # Start bit, single-ended, channel number (3 bits)
            # Transmit data and receive the response
            adc_data = spi.xfer2(command)
            # Extract the ADC value from the received bytes
            adc_value = ((adc_data[1] & 3) << 8) + adc_data[2]

            # Set CS high to end the conversion
            GPIO.output(butCS, GPIO.HIGH)

            return adc_value

        # Adjust sleep time to reduce loop frequency
        while True:
            # Read data from channels in the list
            batch_data = [read_mcp3008(channel) for channel in channels]

            # Process batch data
            for data, channel in zip(batch_data, channels):
                data = self.normalize_value(data, 0, 1024, 32)
                logger.debug('Normalized on Channel: {channel}: {data}'.format(channel=channel, data=data))

                # Check btn_skip_config first
                for btn, (btn_channel, btn_data) in btn_skip_config.items():
                    logger.debug('Checking: {btn_channel}: {btn_data}'.format(btn_channel=btn_channel,btn_data=btn_data))

                    if btn_channel == channel and btn_data == data:
                        break
                else:
                    # If not found in btn_skip_config, check btn_config
                    for btn, (btn_channel, btn_data) in btn_config.items():
                        btn_data_values = btn_data.split("-")
                        # Check if there are exactly two parts after splitting
                        if len(btn_data_values) == 2:
                            # sort values
                            btn_data_values.sort()
                            lower_value = int(btn_data_values[0])
                            upper_value = int(btn_data_values[1])
                            btn_channel = int(btn_channel)

                            logger.debug('Checking: {btn_channel}: {lower_value}-{upper_value}'.format(btn_channel=btn_channel,lower_value=lower_value,upper_value=upper_value))

                            # check for button values in range
                            if btn_channel == int(channel) and lower_value <= data <= upper_value:
                                logger.debug('Pressed button:{btn} on channel:{channel} with value:{data}'.format(btn=btn, channel=channel, data=data))
                                self.controlQ.put({'control': btn})
                                break

                        # check for single button value
                        else:
                            btn_data = int(btn_data_values[0])
                            btn_channel = int(btn_channel)

                            logger.debug('Checking: {btn_channel}: {btn_data}'.format(btn_channel=btn_channel,btn_data=btn_data))

                            if btn_channel == int(channel) and btn_data == data:
                                logger.debug('Pressed button:{btn} on channel:{channel} with value:{data}'.format(btn=btn, channel=channel, data=data))
                                self.controlQ.put({'control': btn})
                                break

                    else:
                        logger.warning('Uncaught press on Channel: {channel}: {data}'.format(channel=channel, data=data))

            # Adjust sleep time to reduce loop frequency
            time.sleep(0.25)

        # Close SPI connection when done
        spi.close()
