import RPi.GPIO as GPIO
import pigpio
import spidev
import time
import logging
logger = logging.getLogger("Controls")
logger.setLevel(logging.DEBUG)

class controls:

    def __init__(self, controlQ=None, encA=17, encB=27, butClk=11, butDOUT=9, butDIN=10, butCS=22, but1=0, but2=7, spi_bus=1, spi=True, btn_config=None, btn_skip_config=None):
        logger.warning("Loading controls")
        self.controlQ = controlQ

        self.rotary_encoder(encA,encB)

        logger.warning(f'Controls: SPI: {spi}. Bus: {spi_bus}')

        if spi:
            logger.warning('SPI mode')
            self.buttons_spi(spi_bus,butCS,but1,but2,btn_config, btn_skip_config)

        else:
            logger.warning('Software mode')
            self.buttons(butClk,butDOUT,butDIN,butCS,but1,but2,btn_config, btn_skip_config)


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
                        logger.warning('Volume down')
                        self.controlQ.put({'control':'vol-down'})
                elif gpio == Enc_B and level == 1:
                    if self.last_A == 1:
                        logger.warning('Volume up')
                        self.controlQ.put({'control':'vol-up'})


        # setup rotary encoder in pigpio
        pi = pigpio.pi()  # init pigpio deamon
        pi.set_mode(Enc_A, pigpio.INPUT)
        pi.set_pull_up_down(Enc_A, pigpio.PUD_UP)
        pi.set_mode(Enc_B, pigpio.INPUT)
        pi.set_pull_up_down(Enc_B, pigpio.PUD_UP)
        pi.callback(Enc_A, pigpio.EITHER_EDGE, rotary_interrupt)
        pi.callback(Enc_B, pigpio.EITHER_EDGE, rotary_interrupt)

        logger.info('Rotary thread start successfully, listening for turns')


    def buttons(self,butClk,butDOUT,butDIN,butCS,but1,but2,btn_config,btn_skip_config):
        # Define MCP3008 pins
        CLK = butClk # CLK
        DOUT = butDOUT # MISO
        DIN = butDIN # MOSI
        CS = butCS # CS

        # channels to read from MCP 3008
        channels = [but1,but2]

        # Set up GPIO pins
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(CLK, GPIO.OUT)
        GPIO.setup(DOUT, GPIO.IN)
        GPIO.setup(DIN, GPIO.OUT)
        GPIO.setup(CS, GPIO.OUT)

        # Define function to read data from MCP3008
        def read_mcp3008(channel):
            # Set CS low to start the conversion
            GPIO.output(CS, GPIO.LOW)

            # Send start bit (1), single-ended (1), and channel number (3)
            command = channel
            command |= 0x18  # start bit + single-ended
            command <<= 3    # we only need to send 5 bits

            # use an _ as we do not need to retrieve a value from the loop
            for _ in range(5):
                if command & 0x80:
                    GPIO.output(DIN, GPIO.HIGH)
                else:
                    GPIO.output(DIN, GPIO.LOW)
                command <<= 1
                GPIO.output(CLK, GPIO.HIGH)
                GPIO.output(CLK, GPIO.LOW)

            # Read the 10-bit data from the MCP3008
            value = 0
            for _ in range(10):
                GPIO.output(CLK, GPIO.HIGH)
                GPIO.output(CLK, GPIO.LOW)
                value <<= 1
                if GPIO.input(DOUT):
                    value |= 0x1

            # Set CS high to end the conversion
            GPIO.output(CS, GPIO.HIGH)

            return value

        # Adjust sleep time to reduce loop frequency
        while True:
            # Read data from channels in the list
            batch_data = [read_mcp3008(channel) for channel in channels]

            # Process batch data
            for data, channel in zip(batch_data, channels):
                data = self.normalize_value(data, 0, 1024, 24)
                logger.debug('Normalized on Channel: {channel}: {data}'.format(channel=channel, data=data))

                # Check btn_skip_config first
                for btn, (btn_channel, btn_data) in btn_skip_config.items():
                    if btn_channel == channel and btn_data == data:
                        break
                else:
                    # If not found in btn_skip_config, check btn_config
                    for btn, (btn_channel, btn_data) in btn_config.items():
                        if btn_channel == channel and btn_data == data:
                            logger.warning('Pressed button:{btn} on channel:{btn_channel} with value:{btn_data}'.format(btn=btn, btn_channel=btn_channel, btn_data=btn_data))
                            self.controlQ.put({'control': btn})
                            break
                    else:
                        logger.warning('Uncaught press on Channel: {channel}: {data}'.format(channel=channel, data=data))

            # Adjust sleep time to reduce loop frequency
            time.sleep(0.25)


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
                data = self.normalize_value(data, 0, 1024, 24)
                logger.debug('Normalized on Channel: {channel}: {data}'.format(channel=channel, data=data))

                # Check btn_skip_config first
                for btn, (btn_channel, btn_data) in btn_skip_config.items():
                    if btn_channel == channel and btn_data == data:
                        break
                else:
                    # If not found in btn_skip_config, check btn_config
                    for btn, (btn_channel, btn_data) in btn_config.items():
                        if btn_channel == channel and btn_data == data:
                            logger.warning('Pressed button:{btn} on channel:{btn_channel} with value:{btn_data}'.format(btn=btn, btn_channel=btn_channel, btn_data=btn_data))
                            self.controlQ.put({'control': btn})
                            break
                    else:
                        logger.warning('Uncaught press on Channel: {channel}: {data}'.format(channel=channel, data=data))

            # Adjust sleep time to reduce loop frequency
            time.sleep(0.25)

        # Close SPI connection when done
        spi.close()
