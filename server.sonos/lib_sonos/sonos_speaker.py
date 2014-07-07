# -*- coding: utf-8 -*-
import logging
from soco.exceptions import SoCoUPnPException
import threading
import time
import json
from lib_sonos import udp_broker
from lib_sonos import utils
from hashlib import sha1

try:
    import xml.etree.cElementTree as XML
except ImportError:
    import xml.etree.ElementTree as XML

logger = logging.getLogger('')
sonos_speakers = {}
_sonos_lock = threading.Lock()

class SonosSpeaker():
    def __init__(self, soco):
        self._soco = soco
        self._uid = self.soco.uid.lower()
        self._volume = self.soco.volume
        self._mute = 0
        self._track_uri = ''
        self._track_duration = "00:00:00"
        self._track_position = "00:00:00"
        self._streamtype = ''
        self._stop = False
        self._play = False
        self._pause = False
        self._radio_station = ''
        self._radio_show = ''
        self._ip = self.soco.ip_address
        self._track_album_art = ''
        self._track_title = ''
        self._track_artist = ''
        self._zone_id = ''
        self._zone_name = ''
        self._zone_coordinator = ''
        self._additional_zone_members = []
        self._zone_icon = self.soco.speaker_info['zone_icon']
        self._zone_name = soco.speaker_info['zone_name']
        self._led = True
        self._bass = self.soco.bass
        self._treble = self.soco.treble
        self._loudness = self.soco.loudness
        self._playmode = self.soco.play_mode
        self._max_volume = -1
        self._playlist_position = 0
        self._model = ''
        self._serial_number = self.soco.speaker_info['serial_number']
        self._software_version = self.soco.speaker_info['software_version']
        self._hardware_version = self.soco.speaker_info['hardware_version']
        self._mac_address = self.soco.speaker_info['mac_address']
        self._status = True
        self._metadata = ''
        self._sub_av_transport = None
        self._sub_rendering_control = None
        self._sub_zone_group = None
        self._properties_hash = None
        self._speaker_zone_coordinator = None

    @property
    def soco(self):
        return self._soco

    @property
    def model(self):
        return self._model

    @model.setter
    def model(self, value):
        self._model = value

    @property
    def metadata(self):
        return self._metadata

    @property
    def speaker_zone_coordinator(self):
        return self._speaker_zone_coordinator

    @speaker_zone_coordinator.setter
    def speaker_zone_coordinator(self, value):
        self._speaker_zone_coordinator = value

    @property
    def sub_av_transport(self):
        return self._sub_av_transport

    @property
    def sub_rendering_control(self):
        return self._sub_rendering_control

    @property
    def sub_zone_group(self):
        return self._sub_zone_group

    @property
    def serial_number(self):
        return self._serial_number

    @property
    def software_version(self):
        return self._software_version

    @property
    def hardware_version(self):
        return self._hardware_version

    @property
    def mac_address(self):
        return self._mac_address

    @property
    def led(self):
        return self._led

    @led.setter
    def led(self, value):
        self.soco.status_light = value
        self._led = value

    @property
    def bass(self):
        return self._bass

    @bass.setter
    def bass(self, value):
        self.soco.bass = value
        self._bass = value

    @property
    def treble(self):
        return self._treble

    @treble.setter
    def treble(self, value):
        self.soco.treble = value
        self._treble = value

    @property
    def loudness(self):
        return self._loudness

    @loudness.setter
    def loudness(self, value):
        self.soco.loudness = value
        self._loudness = value

    @property
    def playmode(self):
        if self.speaker_zone_coordinator is not None:
            logger.debug("forwarding playmode getter to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            return self.speaker_zone_coordinator.playmode
        return self._playmode.lower()

    @playmode.setter
    def playmode(self, value):
        if self.speaker_zone_coordinator is not None:
            logger.debug("forwarding playmode setter to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            self.speaker_zone_coordinator.playmode = value
            self.speaker_zone_coordinator._playmode = value
        else:
            self.soco.play_mode = value
            self._playmode = value

    @property
    def zone_id(self):
        return self._zone_id

    @property
    def zone_name(self):
        if self.speaker_zone_coordinator is not None:
            logger.debug("forwarding zone_name getter to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            return self.speaker_zone_coordinator.zone_name
        return self._zone_name

    @property
    def zone_icon(self):
        if self.speaker_zone_coordinator is not None:
            logger.debug("forwarding zone_icon getter to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            return self.speaker_zone_coordinator.zone_icon
        return self._zone_icon

    @property
    def additional_zone_members(self):
        return self._additional_zone_members

    @additional_zone_members.setter
    def additional_zone_members(self, value):
        self._additional_zone_members = value

    @property
    def ip(self):
        return self._ip

    @property
    def volume(self):
        return int(self._volume)

    @volume.setter
    def volume(self, value):
        volume = int(value)

        if self._volume == volume:
            return

        utils.check_volume_range(volume)
        if utils.check_max_volume_exceeded(volume, self.max_volume):
            volume = self.max_volume
        self.soco.volume = volume

    @property
    def uid(self):
        return self._uid.lower()

    @property
    def mute(self):
        if self.speaker_zone_coordinator is not None:
            logger.debug("forwarding mute getter to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            return self.speaker_zone_coordinator.mute
        return self._mute

    @mute.setter
    def mute(self, value):
        if self.speaker_zone_coordinator is not None:
            logger.debug("forwarding mute setter to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            self.speaker_zone_coordinator.soco.mute = value
            self.speaker_zone_coordinator._mute = int(value)
        else:
            self.soco.mute = value
            self._mute = int(value)

    @property
    def track_uri(self):
        if self.speaker_zone_coordinator is not None:
            logger.debug("forwarding track_uri getter to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            return self.speaker_zone_coordinator.track_uri
        return self._track_uri

    @property
    def track_duration(self):
        if self.speaker_zone_coordinator is not None:
            logger.debug("forwarding track_duration getter to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            return self.speaker_zone_coordinator.track_duration
        if not self._track_duration:
            return "00:00:00"
        return self._track_duration

    @property
    def track_position(self):
        if self.speaker_zone_coordinator is not None:
            logger.debug("forwarding track_position getter to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            return self.speaker_zone_coordinator.track_position
        if not self._track_position:
            return "00:00:00"
        return self._track_position

    @track_position.setter
    def track_position(self, value):
        self._track_position = value

    @property
    def playlist_position(self):
        if self.speaker_zone_coordinator is not None:
            logger.debug("forwarding playlist_position getter to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            return self.speaker_zone_coordinator.playlist_position
        return self._playlist_position

    @playlist_position.setter
    def playlist_position(self, value):
        self._playlist_position = value

    @property
    def streamtype(self):
        if self.speaker_zone_coordinator is not None:
            logger.debug("forwarding streamtype getter to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            return self.speaker_zone_coordinator.streamtype
        return self._streamtype

    @property
    def stop(self):
        if self.speaker_zone_coordinator is not None:
            logger.debug("forwarding stop getter to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            return self.speaker_zone_coordinator.stop
        return self._stop

    @stop.setter
    def stop(self, value):
        if self.speaker_zone_coordinator is not None:
            logger.debug("forwarding stop setter to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            if value:
                self.speaker_zone_coordinator.soco.stop()
                self.speaker_zone_coordinator._stop = True
                self.speaker_zone_coordinator._play = False
                self.speaker_zone_coordinator._pause = False
            else:
                self._speaker_zone_coordinator.play = True
        else:
            if value:
                self.soco.stop()
                self._stop = True
                self._play = False
                self._pause = False
            else:
                self.play = True

    @property
    def play(self):
        if self.speaker_zone_coordinator is not None:
            logger.debug("forwarding play getter to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            return self.speaker_zone_coordinator.play
        return self._play

    @play.setter
    def play(self, value):
        if self.speaker_zone_coordinator is not None:
            logger.debug("forwarding play setter to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            if value:
                self.speaker_zone_coordinator.soco.play()
                self.speaker_zone_coordinator._stop = False
                self.speaker_zone_coordinator._play = True
                self.speaker_zone_coordinator._pause = False
            else:
                self.speaker_zone_coordinator.pause = True
        else:
            if value:
                self.soco.play()
                self._stop = False
                self._play = True
                self._pause = False
            else:
                self.pause = True

    @property
    def pause(self):
        if self.speaker_zone_coordinator is not None:
            logger.debug("forwarding pause getter to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            return self.speaker_zone_coordinator.pause
        return self._pause

    @pause.setter
    def pause(self, value):

        if self.speaker_zone_coordinator is not None:
            logger.debug("forwarding pause setter to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            if value:
                self.speaker_zone_coordinator.soco.pause()
                self.speaker_zone_coordinator._stop = False
                self.speaker_zone_coordinator._play = False
                self.speaker_zone_coordinator._pause = True
            else:
                self.speaker_zone_coordinator.play = True
        else:
            if value:
                self.soco.pause()
                self._stop = False
                self._play = False
                self._pause = True
            else:
                self.play = True

    @property
    def radio_station(self):
        if self.speaker_zone_coordinator is not None:
            logger.debug("forwarding radio_station getter to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            return self.speaker_zone_coordinator.radio_station
        return self._radio_station

    @property
    def radio_show(self):
        if self.speaker_zone_coordinator is not None:
            logger.debug("forwarding radio_show getter to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            return self.speaker_zone_coordinator.radio_show
        return self._radio_show

    @property
    def track_album_art(self):
        if self.speaker_zone_coordinator is not None:
            logger.debug("forwarding track_album_art getter to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            return self.speaker_zone_coordinator.track_album_art
        return self._track_album_art

    @property
    def track_title(self):
        if self.speaker_zone_coordinator is not None:
            logger.debug("forwarding track_title getter to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            return self.speaker_zone_coordinator.track_title
        if not self._track_title:
            return ''
        return self._track_title

    @property
    def track_artist(self):
        if self.speaker_zone_coordinator is not None:
            logger.debug("forwarding track_artist getter to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            return self.speaker_zone_coordinator.track_artist
        if not self._track_artist:
            return ''
        return self._track_artist

    @property
    def max_volume(self):
        return self._max_volume

    @max_volume.setter
    def max_volume(self, value):
        m_volume = int(value)
        if m_volume is not -1:
            self._max_volume = m_volume
            if utils.check_volume_range(self._max_volume):
                if self.volume > self._max_volume:
                    self.volume = self._max_volume
        else:
            self._max_volume = m_volume

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, value):
        # status == 0 -> speaker offline:
        self._status = value

        if self._status == 0:
            self._streamtype = ''
            self._volume = 0
            self._bass = 0
            self._treble = 0
            self._loudness = 0
            self._additional_zone_members = ''
            self._mute = False
            self._led = True
            self._stop = False
            self._play = False
            self._pause = False
            self._track_title = ''
            self._track_artist = ''
            self._track_duration = "00:00:00"
            self._track_position = "00:00:00"
            self._playlist_position = 0
            self._track_uri = ''
            self._track_album_art = ''
            self._radio_show = ''
            self._radio_station = ''
            self._max_volume = -1
            self._zone_id = ''
            self._zone_name = ''
            self._zone_coordinator = ''
            self._zone_icon = ''
            self._playmode = ''

    # ---------------------------------------------------------------------------------
    #
    #          FUNCTIONS
    #
    #---------------------------------------------------------------------------------

    #volume + 2 is the default sonos speaker behaviour, if the volume-up button was pressed
    def volume_up(self):
        vol = self.volume
        vol += 2
        if vol > 100:
            vol = 100
        self.volume = vol

    #volume - 2 is the default sonos speaker behaviour, if the volume-down button was pressed
    def volume_down(self):
        vol = self.volume
        vol -= 2
        if vol < 0:
            vol = 0
        self.volume = vol

    def next(self):
        if self.speaker_zone_coordinator is not None:
            logger.debug("forwarding next command to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            self.speaker_zone_coordinator.next()
        else:
            self.soco.next()

    def previous(self):
        if self.speaker_zone_coordinator is not None:
            logger.debug("forwarding previous command to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            self.speaker_zone_coordinator.previous()
        else:
            self.soco.previous()

    def seek(self, timestamp):
        if self.speaker_zone_coordinator is not None:
            logger.debug("forwarding seek command to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            self.speaker_zone_coordinator.seek(timestamp)
        else:
            self.soco.seek(timestamp)

    def track_info(self):
        if self.speaker_zone_coordinator is not None:
            logger.debug("forwarding track_info command to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            track_info = self._speaker_zone_coordinator.soco.get_current_track_info()
            self.speaker_zone_coordinator.track_position = track_info['position']
            self.speaker_zone_coordinator.playlist_position = int(track_info['playlist_position'])
        else:
            track_info = self.soco.get_current_track_info()
            self.track_position = track_info['position']
            self.playlist_position = int(track_info['playlist_position'])

    def play_uri(self, uri, metadata=None):
        if self.speaker_zone_coordinator is not None:
            logger.debug("forwarding play_uri command to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            self.speaker_zone_coordinator.play_uri(uri, metadata)
        else:
            self.soco.play_uri(uri, metadata)

    @property
    def properties_dict(self):
        return \
            {
                'uid': self.uid,
                'ip': self.ip,
                'mac_address': self.mac_address,
                'software_version': self.software_version,
                'hardware_version': self.hardware_version,
                'serial_number': self.serial_number,
                'led': self.led,
                'volume': self.volume,
                'play': self.play,
                'pause': self.pause,
                'stop': self.stop,
                'mute': self.mute,
                'track_title': self.track_title,
                'track_uri': self.track_uri,
                'track_duration': self.track_duration,
                'track_position': self.track_position,
                'track_artist': self.track_artist,
                'track_album_art': self.track_album_art,
                'radio_station': self.radio_station,
                'radio_show': self.radio_show,
                'playlist_position': self.playlist_position,
                'streamtype': self.streamtype,
                'zone_name': self.zone_name,
                'zone_icon': self.zone_icon,
                'additional_zone_members': ','.join(str(speaker.uid) for speaker in self.additional_zone_members),
                'status': self.status,
                'model': self.model,
                'bass': self.bass,
                'treble': self.treble,
                'loudness': self.loudness,
                'playmode': self.playmode
            }

    def to_json(self):
        return json.dumps(self, default=lambda o: self.properties_dict, sort_keys=True, ensure_ascii=False, indent=4,
                          separators=(',', ': '))

    def play_snippet(self, uri, volume):
        if self._speaker_zone_coordinator is not None:
            logger.debug("forwarding play_snippet command to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            self._speaker_zone_coordinator.play_snippet(uri, volume)
        else:
            t = threading.Thread(target=self._play_snippet_thread, args=(uri, volume))
            t.start()

    def play_tts(self, tts, volume, smb_url, local_share, language, quota):
        if self._speaker_zone_coordinator is not None:
            logger.debug("forwarding play_tts command to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            self._speaker_zone_coordinator.play_tts(tts, volume, smb_url, local_share, language, quota)
        else:
            t = threading.Thread(target=self._play_tts_thread,
                                 args=(tts, volume, smb_url, local_share, language, quota))
            t.start()

    def set_add_to_queue(self, uri):
        self.soco.add_to_queue(uri)

    def send_data(self, force=False):
        #only send data, if something has changed
        data = self.to_json()

        hash_data = sha1(data.encode('utf-8')).hexdigest()
        if hash_data != self._properties_hash:
            self._properties_hash = hash_data
            udp_broker.UdpBroker.udp_send(self.to_json())
        else:
            if force:
                udp_broker.UdpBroker.udp_send(self.to_json())

        #if speaker instance is coordinator and data has changed, send also data for additional group members
        #slaves don't send data in most of the sonos events
        if self.speaker_zone_coordinator is None:
            for speaker in self.additional_zone_members:
                speaker.send_data()

    def join(self, soco_to_join):
        self.soco.join(soco_to_join)

    def unjoin(self):
        self.soco.unjoin()

    def partymode(self):
        self.soco.partymode()

    def event_unsubscribe(self):
        try:
            if self.sub_zone_group is not None:
                self.sub_zone_group.unsubscribe()
            if self.sub_av_transport is not None:
                self.sub_av_transport.unsubscribe()
            if self.sub_rendering_control is not None:
                self.sub_rendering_control.unsubscribe()
        except Exception as err:
            logger.exception(err)

    def event_subscription(self, event_queue):

        try:
            if self.sub_zone_group is None or self._sub_zone_group.time_left == 0:
                self._sub_zone_group = self.soco.zoneGroupTopology.subscribe(None, True, event_queue)

            if self.sub_av_transport is None or self._sub_av_transport.time_left == 0:
                self._sub_av_transport = self.soco.avTransport.subscribe(None, True, event_queue)

            if self.sub_rendering_control is None or self._sub_rendering_control.time_left == 0:
                self._sub_rendering_control = self.soco.renderingControl.subscribe(None, True, event_queue)

        except Exception as err:
            logger.exception(err)

    def _play_tts_thread(self, tts, volume, smb_url, local_share, language, quota):
        try:##
            fname = utils.save_google_tts(local_share, tts, language, quota)

            if smb_url.endswith('/'):
                smb_url = smb_url[:-1]

            url = '{}/{}'.format(smb_url, fname)
            self._play_snippet_thread(url, volume)

        except Exception as err:
            raise err

    def _play_snippet_thread(self, uri, volume):

        self.track_info()
        queued_streamtype = self.streamtype
        queued_uri = self.track_uri
        queued_playlist_position = self.playlist_position
        queued_track_position = self.track_position
        queued_metadata = self.metadata
        queued_play_status = self.play

        queued_volume = self.volume
        if volume == -1:
            volume = queued_volume

        self.volume = 0
        time.sleep(1)

        #ignore max_volume here
        queued_max_volume = self.max_volume
        self.max_volume = -1

        self.volume = volume
        self.play_uri(uri)
        self.track_info()

        h, m, s = self.track_duration.split(":")
        seconds = int(h) * 3600 + int(m) * 60 + int(s) + 1
        time.sleep(seconds)

        self.max_volume = queued_max_volume

        #something changed during playing the audio snippet. Maybe there was command send by an other client (iPad e.g)
        if self.track_uri != uri:
            return

        if queued_playlist_position:
            try:
                if queued_streamtype == "music":
                    self.soco.play_from_queue(int(queued_playlist_position) - 1)
                    self.seek(queued_track_position)
                else:
                    self.play_uri(queued_uri, queued_metadata)
                if not queued_play_status:
                    self.pause = True
            except SoCoUPnPException as err:
                #this happens if there is no track in playlist after snippet was played
                if err.error_code == 701:
                    pass
                else:
                    raise err

        self.volume = queued_volume
