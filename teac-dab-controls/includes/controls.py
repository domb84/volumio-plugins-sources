import ctypes
import RPi.GPIO as GPIO
import pigpio
import spidev
import platform
import threading
import time
import logging
from dataclasses import dataclass, field
from queue import Queue
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("Controls")
from .utils import parse_button_config

def get_native_thread_id() -> Optional[int]:
    if hasattr(threading, 'get_native_id'):
        return threading.get_native_id()
    try:
        libc = ctypes.CDLL('libc.so.6', use_errno=True)
        if hasattr(libc, 'gettid'):
            tid = libc.gettid()
            tid = int(tid)
            return tid if tid > 0 else None
        arch = platform.machine()
        syscall_map = {
            'x86_64': 186,
            'i386': 224,
            'i686': 224,
            'armv7l': 224,
            'armv6l': 224,
            'aarch64': 178,
        }
        nr = syscall_map.get(arch)
        if nr is None:
            return None
        tid = libc.syscall(nr)
        tid = int(tid)
        return tid if tid > 0 else None
    except Exception:
        return None

@dataclass
class ControlsConfig:
    encA: int = 17
    encB: int = 27
    butClk: int = 11
    butDOUT: int = 9
    butDIN: int = 10
    butCS: int = 22
    but1: int = 0
    but2: int = 7
    spi_bus: int = 1
    spi: bool = True
    btn_config: Dict[str, Tuple[str, ...]] = field(default_factory=dict)
    btn_skip_config: Dict[str, Tuple[str, ...]] = field(default_factory=dict)
    button_poll_rate: int = 10
    button_debounce_rate: int = 50
    button_cooldown_rate: int = 500

class Controls:
    """Handle rotary encoder and MCP3008 button inputs.

    This class starts pigpio callbacks for the rotary encoder and runs a
    polling loop for MCP3008 button inputs (either bitbanged or via SPI).
    """

    def __init__(self, controlQ: Queue, config: ControlsConfig, stop_event: Optional[threading.Event] = None) -> None:
        current = threading.current_thread()
        native_id = getattr(current, 'native_id', None) or get_native_thread_id()
        logger.info("Controls starting in thread %s native_id=%s ident=%s", current.name, native_id, current.ident)
        logger.debug("Loading controls")
        self.controlQ = controlQ
        self.config = config
        self.stop_event = stop_event

        self.rotary_encoder(config.encA, config.encB)

        if config.spi:
            logger.debug('SPI mode')
            self.buttons_spi(config.spi_bus, config.butCS, config.but1, config.but2, config.btn_config, config.btn_skip_config)
        else:
            logger.debug('Software mode')
            self.buttons(
                config.butClk,
                config.butDOUT,
                config.butDIN,
                config.butCS,
                config.but1,
                config.but2,
                config.btn_config,
                config.btn_skip_config,
                config.button_poll_rate,
                config.button_debounce_rate,
                config.button_cooldown_rate,
            )

        logger.info('Controls initialised')


    def normalize_value(self, value, min_value, max_value, target_range):
        """Normalize sensor `value` into integer in [0, target_range)."""
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

        # Ensure a sensible minimum poll interval to avoid tight busy-loops
        # (a value of 0 can happen if the config is set to 0)
        # Use a lower minimum to increase polling frequency for bit-banged SPI
        MIN_POLL = 0.05
        if button_poll_rate <= 0:
            button_poll_rate = MIN_POLL
        else:
            button_poll_rate = max(button_poll_rate, MIN_POLL)

        logger.info("Bitbanged controls polling every %.3fs", button_poll_rate)

        # Use monotonic time for debounce/cooldown
        button_states = {
            channel: {
                "last_value": None,
                "stable_since": None,
                "last_sent": 0.0  # Track last time the button was activated (monotonic)
            }
            for channel in channels
        }

        # Preprocess button configs to avoid per-loop parsing
        parsed_btns = parse_button_config(btn_config)
        parsed_skips = parse_button_config(btn_skip_config)

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(CLK, GPIO.OUT)
        GPIO.setup(DOUT, GPIO.IN)
        GPIO.setup(DIN, GPIO.OUT)
        GPIO.setup(CS, GPIO.OUT)

        # Precompute command words for bitbanged reads to avoid recomputation
        command_map = {ch: (ch | 0x18) << 3 for ch in channels}

        def read_mcp3008(channel):
            # Manual CS pulse around the full transaction
            GPIO.output(CS, GPIO.LOW)
            command = command_map[channel]

            # Send 5 clock bits for command
            for _ in range(5):
                GPIO.output(DIN, GPIO.HIGH if (command & 0x80) else GPIO.LOW)
                command <<= 1
                GPIO.output(CLK, GPIO.HIGH)
                GPIO.output(CLK, GPIO.LOW)

            # Read 10 bits of response
            value = 0
            for _ in range(10):
                GPIO.output(CLK, GPIO.HIGH)
                GPIO.output(CLK, GPIO.LOW)
                value = (value << 1) | (1 if GPIO.input(DOUT) else 0)

            GPIO.output(CS, GPIO.HIGH)
            return value

        while not (self.stop_event and self.stop_event.is_set()):
            # Read channels one-by-one so we can exit quickly if stop_event is set
            batch_data = []
            for channel in channels:
                if self.stop_event and self.stop_event.is_set():
                    break
                batch_data.append(read_mcp3008(channel))

            for data, channel in zip(batch_data, channels):
                data = self.normalize_value(data, 0, 1024, 32)
                state = button_states[channel]

                now = time.monotonic()
                if data != state["last_value"]:
                    state["stable_since"] = now
                    state["last_value"] = data
                elif now - (state["stable_since"] or 0) >= button_debounce_rate:
                    current_time = now
                    
                    # Skip if within cooldown period
                    if current_time - state["last_sent"] < button_cooldown_rate:
                        continue

                    logger.debug(f"Channel {channel} stable value: {data}")

                    # Check skip ranges first
                    skipped = False
                    for name, ch, spec in parsed_skips:
                        if ch != channel:
                            continue
                        if spec[0] == 'range':
                            _, low, high = spec
                            if low <= data <= high:
                                skipped = True
                                break
                        else:
                            _, val = spec
                            if val == data:
                                skipped = True
                                break

                    if skipped:
                        continue

                    # Now check configured buttons
                    matched = False
                    for name, ch, spec in parsed_btns:
                        if ch != channel:
                            continue
                        if spec[0] == 'range':
                            _, low, high = spec
                            if low <= data <= high:
                                self.controlQ.put({'control': name})
                                state["last_sent"] = current_time
                                matched = True
                                break
                        else:
                            _, val = spec
                            if val == data:
                                self.controlQ.put({'control': name})
                                state["last_sent"] = current_time
                                matched = True
                                break

                    if not matched:
                        logger.warning(f"Uncaught press on Channel {channel}: {data}")

            time.sleep(button_poll_rate)

        # cleanup
        logger.info('Buttons (bitbang) stopping')

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

        # Preprocess configs for faster comparisons
        parsed_btns = parse_button_config(btn_config)
        parsed_skips = parse_button_config(btn_skip_config)

        # Precompute command byte arrays for each channel to avoid allocations
        cmd_bytes = {ch: [1, (8 + ch) << 4, 0] for ch in channels}

        def _read_all_channels_spi(ch_list):
            # Manually assert CS low for batch reads to reduce GPIO toggles
            GPIO.output(butCS, GPIO.LOW)
            results = []
            for ch in ch_list:
                adc_data = spi.xfer2(cmd_bytes[ch])
                adc_value = ((adc_data[1] & 3) << 8) | adc_data[2]
                results.append(adc_value)
            GPIO.output(butCS, GPIO.HIGH)
            return results

        # Adjust sleep time to reduce loop frequency
        while not (self.stop_event and self.stop_event.is_set()):
            # Read data from channels in the list with one CS toggle
            # Check stop_event between channel transfers to reduce shutdown latency
            batch_data = _read_all_channels_spi(channels)

            # Process batch data
            for data, channel in zip(batch_data, channels):
                data = self.normalize_value(data, 0, 1024, 32)
                logger.debug(f'Normalized on Channel: {channel}: {data}')

                # Check skip specs
                skipped = False
                for name, ch, spec in parsed_skips:
                    if ch != channel:
                        continue
                    if spec[0] == 'range':
                        _, low, high = spec
                        if low <= data <= high:
                            skipped = True
                            break
                    else:
                        _, val = spec
                        if val == data:
                            skipped = True
                            break

                if skipped:
                    continue

                matched = False
                for name, ch, spec in parsed_btns:
                    if ch != channel:
                        continue
                    if spec[0] == 'range':
                        _, low, high = spec
                        if low <= data <= high:
                            logger.debug(f'Pressed button:{name} on channel:{channel} with value:{data}')
                            self.controlQ.put({'control': name})
                            matched = True
                            break
                    else:
                        _, val = spec
                        if val == data:
                            logger.debug(f'Pressed button:{name} on channel:{channel} with value:{data}')
                            self.controlQ.put({'control': name})
                            matched = True
                            break

                if not matched:
                    logger.warning('Uncaught press on Channel: {channel}: {data}'.format(channel=channel, data=data))

            # Adjust sleep time to reduce loop frequency
            time.sleep(0.05)

        # Close SPI connection when done
        spi.close()
        logger.info('Buttons (SPI) stopping')

# Preserve backwards compatibility for older import styles
controls = Controls
