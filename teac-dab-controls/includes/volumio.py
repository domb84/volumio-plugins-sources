# https://volumio.github.io/docs/API/API_Overview.html
from time import sleep

import ctypes
import logging
import platform
import queue
import threading
from typing import Optional
logger = logging.getLogger("Volumio Functions")

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

# set socketio logging
logging.getLogger('socketio').setLevel(logging.WARNING)

import json
import socketio
import re
from retrying import retry

class Volumio:
    """Socket.IO client to Volumio: translates events into menu messages."""

    def __init__(self, volumioQ: 'queue.Queue', menuManagerQ: 'queue.Queue', stop_event=None):
        current = threading.current_thread()
        native_id = getattr(current, 'native_id', None) or get_native_thread_id()
        logger.info("Volumio starting in thread %s native_id=%s ident=%s", current.name, native_id, current.ident)
        self.volumioQ = volumioQ
        self.menuManagerQ = menuManagerQ
        self._waiting = .1
        self.stop_event = stop_event


        self.ws_api = "http://localhost:3000"
        self.sio = socketio.Client(logger=False, engineio_logger=False,reconnection=True)
        # self.sio.connect(url=self.ws_api)

        # use retry from the retrying module to reconnect until it's up
        @retry(wait_fixed=1000)
        def connect():
            self.sio.connect(url=self.ws_api)

        connect()

        # define callback functions
        self.sio.on('pushState', self._on_push_state)
        self.sio.on('pushBrowseLibrary', self._on_push_browse_library)
        self.sio.on('addToFavourites', self._on_response)
        self.sio.on('pushToastMessage', self._on_toast)
        self.sio.on('urifavourites', self._on_response)
        self.sio.on('pushBrowseSources', self._on_push_browse_sources)

        # setup globals
        self.last_state_list = list()

        thread_enumeration = []
        for t in threading.enumerate():
            thread_enumeration.append(
                f"{t.name} ident={t.ident} native_id={getattr(t, 'native_id', None)} alive={t.is_alive()}"
            )
        logger.info("Volumio active Python threads after connect: %s", " | ".join(thread_enumeration))

        # Process incoming requests from the volumioQ using blocking get
        while not (self.stop_event and self.stop_event.is_set()):
            try:
                item = self.volumioQ.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                # parse uri
                if 'show' in item:
                    if item['show'] == 'info':
                        self.get_state()
                        logger.debug("%s", item)

                elif 'button' in item:
                    if item['button'] == 'menu':
                        self.get_browse_sources()
                        logger.debug("%s", item)
                        self.volumioQ.task_done()
                        continue

                    # if it's a stream, play it
                    if re.match(r'^(https?|spotify:track):(\/\/)?.+', item['button']):
                        self.play(item['button'])
                        logger.debug("%s", item)

                    # Spotify playlists, albums, artists, shows, web radio and other browseable URIs
                    elif re.match(r'^(?:radio(?:\/.*)?|spotify(?::(?!track:).+|\/.*)?)$', item['button']):
                        self.get_sources(item['button'])
                        logger.debug("%s", item)

                    # else list the items below it 
                    elif item['button'] == 'stop':
                        self.stop()
                        logger.debug("%s", item)

                    # TODO: this is too broad, fix so only menus are rendered
                    elif re.match(r'^[A-Za-z0-9_-]+$', item['button']):
                        self.get_sources(item['button'])
                        logger.debug("%s", item)

                    self.volumioQ.task_done()

                elif 'memory' in item:
                    input = json.loads(item['memory'])
                    logger.debug(input)
                    title = input.get('title', None)
                    uri = input.get('uri', None)
                    service = input.get('service', None)

                    # TODO: search to see if it's already been added and remove in that instance
                    # self.search(title,uri,service)
                    # self.remove_favourite(title,uri,service)
                    self.add_favourite(title,uri,service)
                    self.volumioQ.task_done()

                else:
                    logger.warning("Queue item did not match filter: %s", item)
                    self.volumioQ.task_done()

            except Exception as e:
                logger.error("Failed to process queue item: %s", e)
                try:
                    self.volumioQ.task_done()
                except Exception:
                    pass

        logger.info('Volumio worker stopping')

    def _send(self, command, args=None, callback=None, namespace=None):
        self.sio.emit(command, args, callback=callback, namespace=namespace)


    def get_state(self):
        logger.debug("Getting state")
        self._send('getState', args=None, callback=self._on_push_state)


    def _on_toast(self, *args):
        try:
            logger.debug("Toast args: %s", args)
            logger.debug("Toast args length: %d", len(args))
            toast = args[0]
            logger.debug("Toast: %s", toast)

            type = toast.get('type', None)
            title = toast.get('title', None)
            message = toast.get('message', None)

            toast_list = list()
            toast_list.append({
                'type': type,
                'title': title,
                'message': message
            })
            logger.debug("Toast: %s", toast_list)
            result = json.dumps(toast_list)
            logger.debug("Toast as json: %s", result)
            self.menuManagerQ.put({'message':result})

        except Exception as e:
            logger.error("Failed to processes incoming toast: " + str(e))

    def _on_response(self, *args):
        logger.debug("%s", args)


    def _on_push_state(self, *args):
        try:
            # logger.debug("State: " + str(args))
            state = args[0]

            # Use dictionary.get('item', None) to get an item from a dictionary and return None if it's missing rather than needing to test for the item
            status = state.get('status', None)
            position = state.get('position', None)
            title = state.get('title', None)
            artist = state.get('artist', None)
            album = state.get('album', None)
            uri = state.get('uri', None)
            trackType = state.get('trackType', None)
            seek = state.get('seek', None)
            duration = state.get('duration', None)           
            bitrate = state.get('bitrate', None)
            samplerate = state.get('samplerate', None)
            bitdepth = state.get('bitdepth', None)            
            channels = state.get('channels', None)            
            random = state.get('random', None)            
            repeatSingle = state.get('repeatSingle', None)            
            consume = state.get('consume', None)            
            volume = state.get('volume', None)            
            dbVolume = state.get('dbVolume', None)            
            mute = state.get('mute', None)            
            disableVolumeControl = state.get('disableVolumeControl', None)            
            stream = state.get('stream', None)            
            updatedb = state.get('updatedb', None)            
            volatile = state.get('volatile', None)            
            service = state.get('service', None)

            state_list = list()
            state_list.append({
                'status': status,
                'artist': artist,
                'title': title,
                'album': album,
                'uri': uri,
                'service': service,
                'bitrate': bitrate,
                'samplerate': samplerate,
                'bitdepth': bitdepth,
                'channels': channels
            })


            # replace any occurences of null or "" with None so we can just check for None
            clean_state_list = [{k: None if v == "" else v for k, v in d.items()} for d in state_list]
            
            # check for missing items
            key_to_check = ['artist', 'title']
            all_none = True

            for dictionary in clean_state_list:
                if not all(dictionary[key] is None for key in key_to_check):
                    all_none = False
                    break

            # if theres too many missing items log it and skip the rest
            if status == 'play' and all_none:
                logger.warning("Now playing item missing state")
            # check if we're not actually playing anything.
            # This happens between every track change so don't show anything in this instance else we spam the display with 'stop' events.
            elif status != 'play' and all_none:
                message = [{'message':'No media is playing'}]
                message = json.dumps(message)
                self.menuManagerQ.put({'message':message})

            # elif clean_state_list == self.last_state_list:
            #     logger.debug("State not changed")

            else:
                result = json.dumps(clean_state_list)
                self.last_state_list = clean_state_list
                logger.debug("State list was this before cleaning: %s", state_list)
                logger.debug("Sending clean state list: %s", result)
                self.menuManagerQ.put({'info':result})


        except Exception as e:
            logger.error("Failed to processes incoming state: " + str(e))
            

    def _on_push_browse_library(self, *args):
        logger.debug("Received: %s", args)

        sources_list = list()

        if args[0] != {}:
            # Some sources are a mix of list items and sources, so iterate over all of them
            main_source = args[0].get('navigation', {}).get('lists', [])

            if main_source:
                for lists in main_source:

                    sources = lists['items']

                    for source in sources:
                        sources_list.append({
                            'title': source.get('title', None),
                            'uri': source.get('uri', None),
                            'service': source.get('service', None),
                            'type': source.get('type', None),
                            'position': source.get('position', None)
                        })
        
        else:
            logger.warning("Received empty data: %s", args)
            return
 
        
        result = json.dumps(sources_list)
        logger.debug("%s", result)
        self.menuManagerQ.put({'menu':result})

        
    def _on_push_browse_sources(self, *args):
    
        sources_list = list()

        items = args[0]
        # Rename fields
        for item in items:
            item['title'] = item.pop('name', None)
            item['type'] = item.pop('plugin_type', None)
            item['service'] = item.pop('plugin_name', None)

        main_source = [{
        "availableListViews":[
            "grid",
            "list"
        ],
        "items":items
        }]

        for lists in main_source:

            sources = lists['items']

            for source in sources:
                # Ensure menuType is always defined; use uri as fallback for empty type
                menuType = source.get('type', None)
                if isinstance(menuType, str) and menuType.strip() == '':
                    menuType = source.get('uri', None)

                sources_list.append({
                    'title': source.get('title', None),
                    'uri': source.get('uri', None),
                    'service': source.get('service', None),
                    'type': menuType,
                    'position': source.get('position', None)
                })

        result = json.dumps(sources_list)
        logger.debug(result)
        self.menuManagerQ.put({'menu':result})

    def get_browse_sources(self) -> None:
        self._send('getBrowseSources')

    # Backwards compatibility alias
    getBrowseSources = get_browse_sources

    def get_sources(self, link: str) -> None:
        logger.debug("Get sources from %s", link)
        self._send('browseLibrary', {'uri': link})

    def add_favourite(self, title: Optional[str], link: Optional[str], service: Optional[str]) -> None:
        logger.debug(f"Add {title} from {link} to {service} favourites")
        self._send('addToFavourites', {'uri': link, 'title': title, 'service': service})

    def remove_favourite(self, title: Optional[str], link: Optional[str], service: Optional[str]) -> None:
        logger.debug(f"Remove {title} from {link} to {service} favourites")
        self._send('removeFromFavourites', {'uri': link, 'title': title, 'service': service})

    def search(self, title: str, link: str, service: str, playlist: Optional[str] = None) -> None:
        # TODO:
        # this feature does not work as search query is not documented
        # https://volumio.github.io/docs/API/WebSocket_APIs.html
        # https://community.volumio.org/t/rest-api-uri-for-browsing/10671
        logger.debug(f"Search for {title} from {link} in {service}")
        if playlist:
            self._send('search', {'uri':link, 'title':title, 'service':service, 'playlist':playlist})
        else:
            self._send('search', {'uri':link, 'title':title, 'service':service})

    
    def play(self, uri: str) -> None:
        # self._send('clearQueue')
        if re.match('(https|http):\/\/.+\/.+', uri):
            self._send('addPlay', {'status':'play', 'service':'webradio', 'uri':uri})
        elif re.match('spotify:track:.+', uri):
            self._send('addPlay', {'status':'play', 'service':'spotify', 'uri':uri})
        else:
            logger.debug("URi does not match webradio or spotify: " + str(uri))


    def stop(self) -> None:
        self._send('stop')
        self._send('clearQueue')

# Backwards compatibility alias
volumio = Volumio
