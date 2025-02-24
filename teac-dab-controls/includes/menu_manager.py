import logging
logger = logging.getLogger("Menu Manager")
logger.setLevel(logging.WARNING)
# Create a handler that prints to console
ch = logging.StreamHandler()
ch.setLevel(logging.WARNING)
logger.addHandler(ch)

from collections import deque
import json
import re

from subprocess import call
from time import sleep
from datetime import datetime

from rpilcdmenu import *
from rpilcdmenu.items import *

class menu_manager:

    def __init__(self ,controlQ, volumioQ, menuManagerQ, lcdRS=7, lcdE=8, lcdD4=25, lcdD5=24, lcdD6=23, lcdD7=15):
        self.controlQ = controlQ
        self.volumioQ = volumioQ
        self.menuManagerQ = menuManagerQ

        # put the queues in a list
        queues = [self.controlQ, self.menuManagerQ]

        # menu access times
        self.menuAccessTime = datetime.now()
        self.lastMessageTime = datetime.now()
        self.messageTime = datetime.now()
        self.last_10_items = deque([],maxlen=10)

        # log last message for deduplication
        self.lastMessage = ""

        # init menu
        self.menu = RpiLCDMenu(lcdRS, lcdE, [lcdD4, lcdD5, lcdD6, lcdD7], scrolling_menu=False)
        self.menu.message(('Initialising...').upper(), autoscroll=True)

        # render main menu
        self.volumioQ.put({'button': 'menu'})

        # define control actions
        self.control_actions = {
            'menu_up': self.menu.processDown,
            'menu_down': self.menu.processUp,
            'btn_main_menu': lambda: self.volumioQ.put({'button': 'menu'}),
            'btn_enter': self.menu.processEnter,
            'btn_radio': lambda: self.volumioQ.put({'button': 'radio'}),
            'btn_stop': lambda: self.volumioQ.put({'button': 'stop'}),
            'btn_info': lambda: self.volumioQ.put({'show': 'info'}),
            'btn_spotify': lambda: self.volumioQ.put({'button': 'spotify'}),
            'btn_favourite': self.add_favorite,
            'btn_back': lambda: self.menuManagerQ.put({'menu': self.go_back(), 'remember':False})
        }


        while True:
            for queue in queues:
                while not queue.empty():
                    queueItem = queue.get()
                    logger.debug(f"Processing item {queueItem} from queue {queue}")

                    try:
                        if 'control' in queueItem:
                            action = queueItem['control']
                            if action in self.control_actions:
                                self.menuAccessTime = datetime.now()
                                self.control_actions[action]()
                            else:
                                logging.warning("Unknown control action: " + action)
                        elif 'menu' in queueItem:
                            if queueItem['menu']:
                                self.build_menu(queueItem['menu'],queueItem.get('remember', True))
                        elif 'info' in queueItem:
                            self.show_track_info(queueItem['info'])
                        elif 'message' in queueItem:
                            self.show_message(queueItem['message'])
                        elif 'clear' in queueItem:
                            self.display_message("", clear=True)
                        else:
                            logging.warning("Queue item did not match any filters: " + str(queueItem))


                    except Exception as e:
                        logger.error("Failed to process queue item: " + str(e))
                        try:
                            logger.error(f"Failed item {queueItem} from queue {queue}")
                            logger.error("processEnter needs to be resolved in the upstream module")
                        except:
                            logger.error(e)

            sleep(0.2)


    def remember(self):
        # save the last menu for history
        menu = []
        index = self.menu.current_option

        for item in self.menu.items:
            menuItem = item.__getattribute__('args')
            # logger.debug(item.__getattribute__('args'))
            # Create a dictionary for the current item
            saveData = {
                'position': menuItem[0],
                'title': menuItem[1],
                'uri': menuItem[2],
                # Return None if theres no service
                'service': next(iter(menuItem[3:]), None)
            }
            menu.append(saveData)

        menu = {'menu': menu, 'index':index}
        
        self.last_10_items.appendleft(json.dumps(menu))

    def go_back(self):
        if len(self.last_10_items) > 1:
            return self.last_10_items.popleft()
        else:
            return None

    def add_favorite(self):
        # get the arguments sent to the menu item (menu name, link to item and service type etc)

        args = self.menu.items[self.menu.current_option].__getattribute__('args')
        menuItem = args[0]
        menuName = args[1]
        menuLink = args[2]
        menuService = args[3]

        # logging
        logger.debug("Menu item: %s" % menuItem)
        logger.debug("Menu item name: %s" % menuName)
        logger.debug("Menu item link: %s" % menuLink)
        logger.debug("Menu item service: %s" % menuService)

        # create required json
        favourite = {}
        favourite['title'] = menuName
        favourite['uri'] = menuLink
        favourite['service'] = menuService
        logger.debug(favourite)
        favourite = json.dumps(favourite)

        # send to queue to create favourite
        self.volumioQ.put({'memory':favourite})


    def display_message(self, message, clear=False, static=False, autoscroll=False):
        # clear will clear the display and not render anything after (ie for shut down)
        # static will leave the message on screen, assuming nothing renders over it immedaitely after
        # autoscroll will scroll the message then leave on screen
        # the default will show the message, then render the menu after 2 seconds

        self.messageTime = datetime.now()
        lastMessageTime = (self.messageTime - self.lastMessageTime).total_seconds()

        # check if message is a duplicate, or allow duplicates if last message was longer than 5 seconds ago
        if self.lastMessage != message and lastMessageTime > 2 or lastMessageTime > 5:
             
            if self.menu != None:
                # self.menu.clearDisplay()
                if clear == True:
                    self.menu.message(message.upper())
                    sleep(2)
                    self.lastMessageTime = datetime.now()
                    return self.menu.clearDisplay()
                elif static == True:
                    self.lastMessageTime = datetime.now()
                    self.lastMessage = message
                    return self.menu.message(message.upper(), autoscroll=False)
                elif autoscroll == True:
                    self.lastMessageTime = datetime.now()
                    self.lastMessage = message
                    return self.menu.message(message.upper(), autoscroll=True)
                else:
                    self.menu.message(message.upper())
                    self.lastMessageTime = datetime.now()
                    sleep(2)
                    self.lastMessage = message
                    return self.menu.render()
                
            return self
        else:
            logger.debug("Skipping duplicate message")


    def show_track_info(self, input):
        try:

            statusSymbols = {'play':'Now playing','stop':'Stopped','pause':'Paused'}

            logger.debug("Track info args: " + str(input))
            input = json.loads(input)

            for i in input:
                logger.debug("Track info input: " + str(i))
                
                if i['status'] in statusSymbols:
                    status = statusSymbols[i['status']]
                else:
                    status = i['status']
                artist = i['artist']
                title = i['title']
                album = i['album']
                bitrate = i['bitrate']
                samplerate = i['samplerate']
                bitdepth = i['bitdepth']
                channels = i['channels']

                tech_info_list = [status, bitrate, samplerate, bitdepth, channels]
                # only join items with a status that isn't None
                tech_info_filtered = ': '.join(str(item) for item in tech_info_list if item is not None)
                tech_info = "({tech})".format(tech=tech_info_filtered)

                first_line_list = [title, artist]
                second_line_list = [album, tech_info]

                # only join items with a status that isn't None
                first_line = ': '.join(str(item) for item in first_line_list if item is not None)
                second_line = ' '.join(str(item) for item in second_line_list if item is not None)

                message = "{first}\n{second}".format(first=first_line, second=second_line)
                self.display_message(message, autoscroll=True)

        except Exception as e:
            logger.error("Failed to process track info: " + str(e))


    def show_message(self, input):
        ## Example
        # message = []
        # message.append({
        #     'type': None,
        #     'title': None,
        #     'message': 'No media is playing'
        # })
        # message = json.dumps(message)
        # self.menuManagerQ.put({'message':message})

        logger.debug("Message input: " + str(input))
        input = json.loads(input)

        for i in input:
            logger.debug("Message input: " + str(i))
            try:
                type = i.get('type', None)
                title = i.get('title', None)
                message = i.get('message', None)

                if title:
                    message = "{title}\n{message}".format(title=title, message=message)
                else:
                    message = message
                    
                self.display_message(message, autoscroll=True)
            except Exception as e:
                logger.error("Failed to process message: " + str(e))


    def build_menu(self, input, remember=True):

        # possible types that are folders
        folderTypes = ['folder', '-category', 'favourites', 'playlist', 'music_service']

        logger.debug("Message menu: " + str(input))
        input = json.loads(input)
        
        # check if the instance is a list (i.e. the input from volumio)
        if isinstance(input, list):
            input = {'menu': input, 'index': 0}

        index = input.get('index', 0)
        menu = input.get('menu', None)

        # save last rendered menu for back button
        if remember:
            logger.debug("Saving last menu")
            self.remember()

        # clear the menu if the next menu has some items
        if menu:
            if self.menu != None:
                self.menu.items = []
        else:
            return(self.display_message("No items in menu"))

        # sort menu by type if it wasnt sorted already
        if menu[0].get('position', None) != None:
            menu = sorted(menu, key=lambda x: (
                (x.get('position'))  # Sort by position
            ))
        else:
            menu = sorted(menu, key=lambda x: (
                (any(x.get('type', '').endswith(folder_type) for folder_type in folderTypes),  # Check if any folderType matches the end of the 'type'
                x.get('title', '').strip().lower()  # Sort by title in ascending order
            )))

        # parse menu
        counter = 0

        for i in menu:
            logger.debug("Menu input: " + str(i))
            try:
                buttonName = i.get('title', None)
                buttonLink = i.get('uri', None)
                buttonService = i.get('service', None)
                buttonType = i.get('type', None)

                if buttonName == "":
                    buttonName = f"Untitled {counter}"

                if buttonType:
                    if any(buttonType.endswith(folder_type) for folder_type in folderTypes):
                        buttonName = f"+{buttonName}"

                if buttonService:
                    menuItem = FunctionItem(buttonName, self.resolveItem, [counter, buttonName, buttonLink, buttonService])
                # genres in webradio do not seem to return it's service type, so capture this and resolve
                elif not buttonService and re.match('radio(\/.+)?', buttonLink):
                    menuItem = FunctionItem(buttonName, self.resolveItem, [counter, buttonName, buttonLink, 'webradio'])
                else:
                    menuItem = FunctionItem(buttonName, self.resolveItem, [counter, buttonName, buttonLink, None])
                # add to main menu
                self.menu.append_item(menuItem)
                counter += 1

            except Exception as e:
                logger.error("Failed to process menu input: " +str(e))
        
        self.menu.current_option = index

        # return rendered menu
        # if you do not return the menu it will render the original one again
        return self.menu.render()


    def resolveItem(self, item_index, buttonName, buttonLink, buttonService):
        logger.debug("item %d pressed" % (item_index))
        logger.debug("item name: %s" % (buttonName))
        logger.debug("item link: %s" % (buttonLink))
        logger.debug("item link: %s" % (buttonService))
        self.volumioQ.put({'button':buttonLink})


    # exit sub menu
    def exitSubMenu(self, submenu):
        return submenu.exit()


    def dimmer(self):
        self.menu.lcd.displayToggle()


    def render_bars(self, input):
        bar = int(input / 100 * 16)
        bars = '\240' * bar
        return bars


