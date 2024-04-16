import RPi.GPIO as GPIO
import pigpio
import spidev
import time
import logging
logger = logging.getLogger("Controls")
logger.setLevel(logging.DEBUG)

class controls:

    def __init__(self, controlQ=None, encA=17, encB=27, butClk=11, butDOUT=9, butDIN=10, butCS=22, but1=0, but2=7, spi_bus=1, spi=True):
        logger.warning("Loading controls")
        self.controlQ = controlQ

        self.rotary_encoder(encA,encB)

        logger.warning(f'Controls: SPI: {spi}. Bus: {spi_bus}')

        if spi:
            logger.warning('SPI mode')
            self.buttons_spi(spi_bus,butCS,but1,but2)

        else:
            logger.warning('Software mode')
            self.buttons(butClk,butDOUT,butDIN,butCS,but1,but2)


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


    def buttons(self,butClk,butDOUT,butDIN,butCS,but1,but2):
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

        # Main loop to continuously read data from MCP3008
        # far more CPU effecient than PIGPIO or bitbangio from ADAFRUIT
        while True:

            # read data from channels in the list
            for channel in channels:
                data = read_mcp3008(channel)
                logger.debug('Caught press on Channel: {channel}: {data}'.format(channel=channel, data=data))

                data = self.normalize_value(data, 0, 1024, 16)
                logger.debug('Normlaised on Channel: {channel}: {data}'.format(channel=channel, data=data))
                # pause between caught button presses to stop double presses
                time.sleep(0.25)
                if channel == 0:
                    if data == 0:
                        logger.debug('Nothing pressed')
                    elif data == 15:
                        logger.debug('Power button')
                        self.controlQ.put({'control':'power'})
                    elif data == 4:
                        logger.debug('Dimmer button')
                        self.controlQ.put({'control':'dimmer'})
                    elif data == 7:
                        logger.debug('Memory button')
                        self.controlQ.put({'control':'memory'})
                    elif data == 6:
                        logger.debug('Auto tuning button')
                        self.controlQ.put({'control':'auto-tuning'})
                    elif data == 9:
                        logger.debug('Enter button')
                        self.controlQ.put({'control':'enter'})
                    elif data == 12:
                        logger.debug('Function button')
                        self.controlQ.put({'control':'functon-fm-mode'})
                    elif data == 14:
                        logger.debug('Band button')
                        self.controlQ.put({'control':'band'})
                    elif data == 10:
                        logger.debug('Info button')
                        self.controlQ.put({'control':'info'})
                    else:
                        logger.warning('Uncaught press on Channel: {channel}: {data}'.format(channel=channel, data=data))

                elif channel == 7:
                    if data == 0:
                        logger.debug('Nothing pressed')
                    elif data == 15:
                        logger.debug('Timer button')
                        self.controlQ.put({'control':'timer'})
                    elif data == 14:
                        logger.debug('Time adj button')
                        self.controlQ.put({'control':'time-adj'})
                    elif data == 12:
                        logger.debug('Daily button')
                        self.controlQ.put({'control':'daily'})

                    else:
                        logger.warning('Uncaught press on Channel: {channel}: {data}'.format(channel=channel, data=data))

                else:
                        logger.warning('Uncaught press on Channel: {channel}: {data}'.format(channel=channel, data=data))


            # Wait for a short period before reading again
            time.sleep(0.05)


    def buttons_spi(self,spi_bus,butCS,but1,but2):
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

        # Main loop to continuously read data from MCP3008
        while True:
            # Read data from channels in the list
            for channel in channels:
                data = read_mcp3008(channel)
                logger.debug('Caught press on Channel: {channel}: {data}'.format(channel=channel, data=data))

                data = self.normalize_value(data, 0, 512, 16)
                logger.debug('Normalized on Channel: {channel}: {data}'.format(channel=channel, data=data))

                # Pause between caught button presses to prevent double presses
                time.sleep(0.25)

                # Handle different button presses based on channel and data
                if channel == 0:
                    if data == 0:
                        logger.debug('Nothing pressed')
                    elif data == 15:
                        logger.debug('Power button')
                        self.controlQ.put({'control':'power'})
                    elif data == 4:
                        logger.debug('Dimmer button')
                        self.controlQ.put({'control':'dimmer'})
                    elif data == 7:
                        logger.debug('Memory button')
                        self.controlQ.put({'control':'memory'})
                    elif data == 6:
                        logger.debug('Auto tuning button')
                        self.controlQ.put({'control':'auto-tuning'})
                    elif data == 9:
                        logger.debug('Enter button')
                        self.controlQ.put({'control':'enter'})
                    elif data == 12:
                        logger.debug('Function button')
                        self.controlQ.put({'control':'functon-fm-mode'})
                    elif data == 14:
                        logger.debug('Band button')
                        self.controlQ.put({'control':'band'})
                    elif data == 10:
                        logger.debug('Info button')
                        self.controlQ.put({'control':'info'})
                    else:
                        logger.warning('Uncaught press on Channel: {channel}: {data}'.format(channel=channel, data=data))

                elif channel == 7:
                    if data == 0:
                        logger.debug('Nothing pressed')
                    elif data == 15:
                        logger.debug('Timer button')
                        self.controlQ.put({'control':'timer'})
                    elif data == 14:
                        logger.debug('Time adj button')
                        self.controlQ.put({'control':'time-adj'})
                    elif data == 12:
                        logger.debug('Daily button')
                        self.controlQ.put({'control':'daily'})

                    else:
                        logger.warning('Uncaught press on Channel: {channel}: {data}'.format(channel=channel, data=data))

                else:
                        logger.warning('Uncaught press on Channel: {channel}: {data}'.format(channel=channel, data=data))

            # Add any additional handling or conditions here
            # Wait for a short period before reading again
            time.sleep(0.05)

        # Close SPI connection when done
        spi.close()
