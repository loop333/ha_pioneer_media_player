"""
Pioneer X-SMC55-S
"""
import logging
import telnetlib
import voluptuous as vol

from datetime import timedelta, datetime
import time
import queue
import re

from homeassistant.components.media_player import (
    MediaPlayerEntity, PLATFORM_SCHEMA)
from homeassistant.components.media_player.const import (
    SUPPORT_PAUSE, SUPPORT_SELECT_SOURCE, SUPPORT_SELECT_SOUND_MODE,
    SUPPORT_TURN_OFF, SUPPORT_TURN_ON, SUPPORT_VOLUME_MUTE, SUPPORT_VOLUME_SET, SUPPORT_VOLUME_STEP,
    SUPPORT_PLAY, SUPPORT_PLAY_MEDIA, MEDIA_TYPE_MUSIC, MEDIA_TYPE_CHANNEL, MEDIA_TYPE_PLAYLIST,
    SUPPORT_NEXT_TRACK, SUPPORT_PREVIOUS_TRACK)
from homeassistant.const import (
    CONF_HOST, CONF_NAME, CONF_PORT, CONF_TIMEOUT, STATE_OFF, STATE_ON, STATE_UNKNOWN,
    STATE_PAUSED, STATE_PLAYING, STATE_IDLE, STATE_STANDBY)
import homeassistant.helpers.config_validation as cv

class mylogger():
    def debug(self, format, *args):
        print('DEBUG:'+format % args)
    def warning(self, format, *args):
        print('WARNING: '+format % args)
    def error(self, format, *args):
        print('ERROR: '+format % args)

if __name__ == '__main__':
    _LOGGER = mylogger()
else:
    _LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = 'pioneer'
DEFAULT_PORT = 8102
DEFAULT_TIMEOUT = 1
ANSWER_TIMEOUT = 0.2
SCAN_INTERVAL = timedelta(seconds=15)

SUPPORT_PIONEER = SUPPORT_PAUSE | SUPPORT_VOLUME_STEP | SUPPORT_VOLUME_MUTE | \
                  SUPPORT_TURN_ON | SUPPORT_TURN_OFF | SUPPORT_SELECT_SOUND_MODE | \
                  SUPPORT_SELECT_SOURCE | SUPPORT_PLAY | SUPPORT_PLAY_MEDIA | \
                  SUPPORT_NEXT_TRACK | SUPPORT_PREVIOUS_TRACK

MAX_VOLUME = 185
MAX_SOURCE_NUMBERS = 60

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_HOST): cv.string,
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
    vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): cv.socket_timeout,
})

def setup_platform(hass, config, add_entities, discovery_info=None):
#    _LOGGER.debug('setup_platform')
    pioneer = PioneerDevice(
        config.get(CONF_NAME),
        config.get(CONF_HOST),
        config.get(CONF_PORT),
        config.get(CONF_TIMEOUT))
    add_entities([pioneer])

class PioneerDevice(MediaPlayerEntity):

    def __init__(self, name, host, port, timeout):
#        _LOGGER.debug('__init__')
        self._name = name
        self._host = host
        self._port = port
        self._timeout = timeout
        self._pwstate = 'PWR2'
        self._volume = 0
        self._muted = False
        self._selected_source = None
        self._source_number_to_name = {'02': 'Tuner', '45': 'Favorites', '38': 'Internet Radio'}
        self._source_name_to_number = {v: k for k, v in self._source_number_to_name.items()}
        self._cmd_queue = queue.Queue()
        self._image_url = None
        self._state = STATE_UNKNOWN
        self._media_title = None
        self._media_artist = None
        self._sound_mode_list = None
        self._last_update = datetime.now()

    def queue_command(self, command):
#        _LOGGER.debug('queue_command %s', command)
        self._cmd_queue.put(command)

    def telnet_command(self, telnet, command):
#        _LOGGER.debug('telnet_command %s', command)
        num_lines = 0
        gcp_type = None
        gep_type = None
        try:
            telnet.write(command.encode('ASCII') + b'\r')
            while True:
                line = telnet.read_until(b'\n', timeout=ANSWER_TIMEOUT).decode('ASCII').strip()
                if line == '':
                    break
#                _LOGGER.debug('read_until %s', line)
                if line.startswith('FN'):
                    self._selected_source = self._source_number_to_name.get(line[2:])
                elif line.startswith('PWR'):
                    self._pwstate = line
                elif line.startswith('VOL'):
                    self._volume = int(line[3:]) / MAX_VOLUME
                elif line.startswith('MUT'):
                    self._muted = (line == 'MUT0')
                elif line.startswith('GIC'):
                    r = re.match(r'^GIC(?P<len>\d{3})\"(?P<url>.*)\"$', line)
                    self._image_url = None
                    if r:
                        gic = r.groupdict()
                        self._image_url = gic['url']
                elif line.startswith('GBP'):
                    num_lines = int(line[3:])
                elif line.startswith('GCP'):
                    r = re.match(r'^GCP(?P<type>\d{2})(?P<hier>\d)(?P<top>\d)0(?P<return>\d)0(?P<shuffle>\d)(?P<repeat>\d)0{8}\"(?P<text>.*)\"$', line)
                    if r:
                        gcp = r.groupdict()
#                        print(gcp)
                        gcp_type = gcp['type']
                        if gcp_type == '02':
                            self._state = STATE_PLAYING
                        elif gcp_type == '06':
                            self._state = STATE_PAUSED
                        elif gcp_type == '01':
                            self._state = STATE_PAUSED
                        else:
                            _LOGGER.debug('Unknown GCP type: %s', gcp_type)
                elif line.startswith('GDP'):
                    r = re.match(r'^GDP(?P<first>\d{5})(?P<last>\d{5})(?P<len>\d{5})$', line)
                    if r:
                        gdp = r.groupdict()
#                        print(gdp)
                elif line.startswith('GEP'):
                    r = re.match(r'^GEP(?P<line>\d{2})(?P<focus>\d)(?P<type>\d{2})\"(?P<text>.*)\"$', line)
                    if r:
                        gep = r.groupdict()
#                        print(gep)
                        gep_type = gep['type']
                        if gcp_type == '02' and gep_type == '20':
                            self._media_title = gep['text']
                        if gcp_type == '02' and gep_type == '32':
                            self._media_artist = gep['text']
                        if gcp_type == '01' and int(gep['line']) == 1:
                            self._sound_mode_list = []
                        if gcp_type == '01':
                            self._sound_mode_list.append(gep['text'])
                elif line.startswith('GIB'):
                    r = re.match(r'^GIB(?P<num>\d{5})(?P<line>\d{5})(?P<type>\d{2})(?P<text_len>\d{3})\"(?P<text>.*)\"(?P<url_len>\d{3})\"(?P<url>.*)\"$', line)
                    if r:
                        gib = r.groupdict()
#                        print(gib)
                        if int(gib['line']) == 1:
                            self._sound_mode_list = []
                        self._sound_mode_list.append(gib['text'])
                else:
                    _LOGGER.debug('Found unknown answer: %s', line)
        except telnetlib.socket.timeout:
            _LOGGER.debug('Pioneer %s command %s timed out', self._name, command)

    def update(self):
#        _LOGGER.debug('update')
        now = datetime.now()
        if now - self._last_update < timedelta(seconds=ANSWER_TIMEOUT):
            time.sleep(ANSWER_TIMEOUT)

        try:
            telnet = telnetlib.Telnet(self._host, self._port, self._timeout)
        except (ConnectionRefusedError, OSError):
            _LOGGER.warning('update: Pioneer %s refused connection', self._name)
            return False

        try:
            while True:
                cmd = self._cmd_queue.get_nowait()
                self.telnet_command(telnet, cmd)
        except queue.Empty:
            pass

        self.telnet_command(telnet, '?P')
        self.telnet_command(telnet, '?V')
        self.telnet_command(telnet, '?M')
        self.telnet_command(telnet, '?F')
        if self._selected_source in ['Favorites', 'Internet Radio']:
            self.telnet_command(telnet, '?GAP')
            self.telnet_command(telnet, '?GIC')
            self.telnet_command(telnet, '?GIA0000199999')

        telnet.close()
        self._last_update = datetime.now()
#        _LOGGER.debug('update end')

        return True

    @property
    def name(self):
#        _LOGGER.debug('name')
        return self._name

    @property
    def state(self):
#        _LOGGER.debug('state')
        if self._pwstate == 'PWR1' or self._pwstate == 'PWR2':
            return STATE_OFF
        if self._selected_source == 'Tuner':
            return STATE_PLAYING
        if self._selected_source in ['Favorites', 'Internet Radio']:
            return self._state

        return STATE_UNKNOWN

    @property
    def volume_level(self):
#        _LOGGER.debug('volume_level')
        return self._volume

    @property
    def is_volume_muted(self):
#        _LOGGER.debug('is_volume_muted')
        return self._muted

    @property
    def supported_features(self):
#        _LOGGER.debug('suported_features')
        return SUPPORT_PIONEER

    @property
    def source(self):
#        _LOGGER.debug('source')
        return self._selected_source

    @property
    def source_list(self):
#        _LOGGER.debug('source_list')
        return list(self._source_name_to_number.keys())

    @property
    def sound_mode(self):
#        _LOGGER.debug('sound_mode')
        if self._selected_source in ['Favorites', 'Internet Radio']:
            return self._media_title

        return None

    @property
    def sound_mode_list(self):
#        _LOGGER.debug('sound_mode_list')
        if self._selected_source in ['Favorites', 'Internet Radio']:
#            _LOGGER.debug('return _sound_mode_list[0] %s', self._sound_mode_list[0])
            return self._sound_mode_list

        return None

    @property
    def media_title(self):
#        _LOGGER.debug('media_title')
        if self._selected_source in ['Favorites', 'Internet Radio']:
            return self._media_title

        return self._selected_source

    def turn_off(self):
        _LOGGER.debug('turn_off')
        self.queue_command('PF')
        self.schedule_update_ha_state()

    def volume_up(self):
        _LOGGER.debug('volume_up')
        self.queue_command('VU')
        self.schedule_update_ha_state()

    def volume_down(self):
        _LOGGER.debug('volume_down')
        self.queue_command('VD')
        self.schedule_update_ha_state()

#    def set_volume_level(self, volume):
#        _LOGGER.debug('set_volume_level %s', str(volume))
#        if self._volume < volume:
#            self.queue_command('VU')
#        if self._volume > volume:
#            self.queue_command('VD')

    def mute_volume(self, mute):
        _LOGGER.debug('mute_volume')
        self.queue_command('MO' if mute else 'MF')
        self.schedule_update_ha_state()

    def turn_on(self):
        _LOGGER.debug('turn_on')
        self.queue_command('PO')
        self.schedule_update_ha_state()

    def select_source(self, source):
        _LOGGER.debug('select_source %s', source)
        self.queue_command(self._source_name_to_number.get(source) + 'FN')
        self.schedule_update_ha_state()

    def select_sound_mode(self, sound_mode):
        _LOGGER.debug('select_sound_mode %s', sound_mode)
        self.queue_command('36PB')
        self.queue_command(str(self._sound_mode_list.index(sound_mode)+1).zfill(5)+'GHP')
        self.schedule_update_ha_state()

    def play_media(self, media_type, media_id, **kwargs):
        _LOGGER.debug('play_media %s %s', media_type, media_id)

    def media_play(self):
        _LOGGER.debug('media_play')
        self.queue_command('30PB')
        self.schedule_update_ha_state()

    def media_pause(self):
        _LOGGER.debug('media_pause')
        self.queue_command('11PB')
        self.schedule_update_ha_state()

    def media_previous_track(self):
        _LOGGER.debug('media_previous_track')
        self.queue_command('12PB')
        self.schedule_update_ha_state()

    def media_next_track(self):
        _LOGGER.debug('media_next_track')
        self.queue_command('13PB')
        self.schedule_update_ha_state()

#    @property
#    def media_channel(self):
#        _LOGGER.debug('media_channel')
#        return 'media_channel'

#    @property
#    def media_playlist(self):
#        _LOGGER.debug('media_playlist')
#        return 'media_playlist'

#    @property
#    def media_content_id(self):
#        _LOGGER.debug('media_content_id')
#        return 'media_content_id'

    @property
    def media_content_type(self):
#        _LOGGER.debug('media_content_type')
        return MEDIA_TYPE_MUSIC

#    @property
#    def media_track(self):
#        _LOGGER.debug('media_track')
#        return 'media_track'

    @property
    def media_artist(self):
#        _LOGGER.debug('media_artist')
        if self._selected_source in ['Favorites', 'Internet Radio']:
            return self._media_artist

        return None

#    @property
#    def media_album_name(self):
#        _LOGGER.debug('media_album_name')
#        return 'media_album_name'

#    @property
#    def media_album_artist(self):
#        _LOGGER.debug('media_album_artist')
#        return 'media_album_artist'

    @property
    def media_image_url(self):
#        _LOGGER.debug('media_image_url')
        if self._selected_source in ['Favorites', 'Internet Radio']:
            return self._image_url
        return None

#    @property
#    def app_id(self):
#        _LOGGER.debug('app_id')
#        return 'app_id'

#    @property
#    def app_name(self):
#        _LOGGER.debug('app_name')
#        return 'app_name'

if __name__ == '__main__':
    pioneer = PioneerDevice('pioneer', '192.168.1.7', '8102', 1)

#    pioneer.queue_command('?GIA0000199999')
#    pioneer.queue_command('36PB')
#    pioneer.queue_command('?GAP')
    pioneer.queue_command('10PB')
#    pioneer.queue_command('00003GHP')
    pioneer.update()
