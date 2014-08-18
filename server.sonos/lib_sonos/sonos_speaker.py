# -*- coding: utf-8 -*-
import logging
from lib_sonos.utils import NotifyList
from soco import alarms
from soco.exceptions import SoCoUPnPException
import threading
import time
import json
from lib_sonos import udp_broker
from lib_sonos import utils
from hashlib import sha1
import collections

try:
    import xml.etree.cElementTree as XML
except ImportError:
    import xml.etree.ElementTree as XML

logger = logging.getLogger('')
sonos_speakers = {}
_sonos_lock = threading.Lock()


class SonosSpeaker():
    def __init__(self, soco):
        self._zone_members = NotifyList()
        self._zone_members.register_callback(self.zone_member_changed)
        self._dirty_properties = []
        self._soco = soco
        self._alarms = ''
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
        self._sub_alarm = None
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
        self.dirty_property('model')
        self._model = value

    @property
    def metadata(self):
        return self._metadata

    ### SPEAKER_ZONE_COORDINATOR #######################################################################################
    
    @property
    def speaker_zone_coordinator(self):
        return self._speaker_zone_coordinator    

    @speaker_zone_coordinator.setter
    def speaker_zone_coordinator(self, value):
        self._speaker_zone_coordinator = value

    @property
    def is_coordinator(self):
        if self == self._speaker_zone_coordinator:
            return True
        return False

    ### EVENTS #########################################################################################################    

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
    def sub_alarm(self):
        return self._sub_alarm

    ### SERIAL #########################################################################################################

    @property
    def serial_number(self):
        return self._serial_number

    ### SOFTWARE VERSION ###############################################################################################

    @property
    def software_version(self):
        return self._software_version

    ### HARDWARE VERSION ###############################################################################################

    @property
    def hardware_version(self):
        return self._hardware_version

    ### MAC ADDRESS ####################################################################################################

    @property
    def mac_address(self):
        return self._mac_address

    ### LED ############################################################################################################

    def get_led(self):
        return self._led

    def set_led(self, value, trigger_action=False, group_command=False):
        if trigger_action:
            if group_command:
                for speaker in self._zone_members:
                    speaker.set_led(value, trigger_action=True, group_command=False)
            self.soco.status_light = value
        if value == self._led:
            return
        self._led = value
        self.dirty_property('led')

    ### BASS ###########################################################################################################

    def get_bass(self):
        return self._bass

    def set_bass(self, value, trigger_action=False, group_command=False):
        bass = int(value)
        if trigger_action:
            if group_command:
                for speaker in self._zone_members:
                    speaker.set_bass(bass, trigger_action=True, group_command=False)
            self.soco.bass = bass
        if self._bass == bass:
            return
        self._bass = value
        self.dirty_property('bass')

    ### TREBLE #########################################################################################################

    def get_treble(self):
        return self._treble

    def set_treble(self, value, trigger_action=False, group_command=False):
        treble = int(value)
        if trigger_action:
            if group_command:
                for speaker in self._zone_members:
                    speaker.set_treble(treble, trigger_action=True, group_command=False)
            self.soco.treble = treble
        if self._treble == treble:
            return
        self._treble = treble
        self.dirty_property('treble')

    ### LOUDNESS #######################################################################################################

    def get_loudness(self):
        return self._loudness

    def set_loudness(self, value, trigger_action=False, group_command=False):
        loudness = int(value)
        if trigger_action:
            if group_command:
                for speaker in self._zone_members:
                    speaker.set_loudness(loudness, trigger_action=True, group_command=False)
            self.soco.loudness = loudness
        if self._loudness == loudness:
            return
        self._loudness = value
        self.dirty_property('loudness')

    ### PLAYMODE #######################################################################################################

    def get_playmode(self):
        if not self.is_coordinator:
            logger.debug("forwarding playmode getter to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            return self.speaker_zone_coordinator.playmode
        return self._playmode.lower()

    def set_playmode(self, value, trigger_action=False):
        if not self.is_coordinator:
            logger.debug("forwarding playmode setter to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            self.speaker_zone_coordinator.set_playmode(value, trigger_action)
        if trigger_action:
            self.soco.play_mode = value
        if self._playmode == value:
            return
        self._playmode = value

        self.dirty_property('playmode')

        #dirty properties for all zone members, if coordinator
        if self.is_coordinator:
            for speaker in self._zone_members:
                speaker.dirty_propery('playmode')

    ### ZONE ID ########################################################################################################

    @property
    def zone_id(self):
        return self._zone_id

    ### ZONE NAME ######################################################################################################

    @property
    def zone_name(self):
        if not self.is_coordinator:
            logger.debug("forwarding zone_name getter to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            return self.speaker_zone_coordinator.zone_name
        return self._zone_name

    @property
    def zone_icon(self):
        if not self.is_coordinator:
            logger.debug("forwarding zone_icon getter to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            return self.speaker_zone_coordinator.zone_icon
        return self._zone_icon

    @property
    def zone_members(self):
        return self._zone_members

    def zone_member_changed(self):
        self.dirty_property('additional_zone_members')

    @property
    def additional_zone_members(self):
        ','.join(str(speaker.uid) for speaker in self.zone_members)

    @property
    def ip(self):
        return self._ip

    ### VOLUME #########################################################################################################

    def get_volume(self):
        return self._volume

    def set_volume(self, volume, trigger_action=False, group_command=False):
        volume = int(volume)
        if trigger_action:
            if group_command:
                for speaker in self._zone_members:
                    speaker.set_volume(volume, trigger_action=True, group_command=False)
            utils.check_volume_range(volume)
            if utils.check_max_volume_exceeded(volume, self.max_volume):
                volume = self.max_volume
            self.soco.volume = volume
        if self._volume == volume:
            return
        self._volume = volume
        self.dirty_property('volume')

    ### UID ############################################################################################################

    @property
    def uid(self):
        return self._uid.lower()

    ### MUTE ###########################################################################################################

    def get_mute(self):
        if not self.is_coordinator:
            logger.debug("forwarding mute getter to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            return self.speaker_zone_coordinator.mute
        return self._mute

    def set_mute(self, value, trigger_action=False, group_command=False):
        """
        By default, mute is not a group command, but the sonos app handles the mute command as a group command.
        :param value: mute value [0/1]
        :param trigger_action: triggers a soco action. Otherwise just a property setter
        :param group_command: Acts as a group command, all members in a group will be muted. False by default.
        """
        mute = int(value)
        if trigger_action:
            if group_command:
                for speaker in self._zone_members:
                    speaker.set_mute(mute, trigger_action=True, group_command=False)

            self.soco.mute = mute

        if self._mute == value:
            return
        self._mute = value
        self.dirty_property('mute')

    ### TRACK_URI ######################################################################################################

    @property
    def track_uri(self):
        if not self.is_coordinator:
            logger.debug("forwarding track_uri getter to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            return self.speaker_zone_coordinator.track_uri
        return self._track_uri

    @track_uri.setter
    def track_uri(self, value):
        if self._track_uri == value:
            return
        self._track_uri = value
        self.dirty_property('track_uri')

    @property
    def track_duration(self):
        if not self.is_coordinator:
            logger.debug("forwarding track_duration getter to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            return self.speaker_zone_coordinator.track_duration
        if not self._track_duration:
            return "00:00:00"
        return self._track_duration

    @track_duration.setter
    def track_duration(self, value):
        if self._track_duration == value:
            return
        self.dirty_property('track_duration')
        self._track_duration = value

    @property
    def track_position(self):
        if not self.is_coordinator:
            logger.debug("forwarding track_position getter to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            return self.speaker_zone_coordinator.track_position
        if not self._track_position:
            return "00:00:00"
        return self._track_position

    @track_position.setter
    def track_position(self, value):
        self._track_position = value
        self.dirty_property('track_position')

    @property
    def playlist_position(self):
        if not self.is_coordinator:
            logger.debug("forwarding playlist_position getter to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            return self.speaker_zone_coordinator.playlist_position
        return self._playlist_position

    @playlist_position.setter
    def playlist_position(self, value):
        self._playlist_position = value
        self.dirty_property('playlist_position')

    @property
    def streamtype(self):
        if not self.is_coordinator:
            logger.debug("forwarding streamtype getter to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            return self.speaker_zone_coordinator.streamtype
        return self._streamtype

    @streamtype.setter
    def streamtype(self, value):
        if self._streamtype == value:
            return
        self._streamtype = value
        self.dirty_property('streamtype')

    @property
    def stop(self):
        if not self.is_coordinator:
            logger.debug("forwarding stop getter to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            return self.speaker_zone_coordinator.stop
        return self._stop

    @stop.setter
    def stop(self, value):
        if self._stop == value:
            return
        self._stop = value
        self.dirty_property('stop')

    def trigger_stop(self, value):
        stop = int(value)
        if not self.is_coordinator:
            logger.debug("forwarding stop setter to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            self.speaker_zone_coordinator.trigger_stop(stop)
        else:
            if stop:
                self.soco.stop()
                self.stop = 1
                self.play = 0
                self.pause = 0
            else:
                self.play = 1

    @property
    def play(self):
        if not self.is_coordinator:
            logger.debug("forwarding play getter to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            return self.speaker_zone_coordinator.play
        return self._play

    @play.setter
    def play(self, value):
        if self._play == value:
            return
        self._play = value
        self.dirty_property('play')

    def trigger_play(self, value):
        play = int(value)
        if not self.is_coordinator:
            logger.debug("forwarding play setter to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            self.speaker_zone_coordinator.trigger_play(play)
        else:
            if play:
                self.soco.play()
                self.stop = 0
                self.play = 1
                self.pause = 0
            else:
                self.pause = 1

    @property
    def pause(self):
        if not self.is_coordinator:
            logger.debug("forwarding pause getter to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            return self.speaker_zone_coordinator.pause
        return self._pause

    @pause.setter
    def pause(self, value):
        if self._pause == value:
            return
        self._pause = value
        self.dirty_property('pause')

    def trigger_pause(self, value):
        pause = int(value)
        if not self.is_coordinator:
            logger.debug("forwarding pause setter to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            self.speaker_zone_coordinator.trigger_pause(pause)
        else:
            if pause:
                self.soco.pause()
                self.stop = 0
                self.play = 0
                self.pause = 1
            else:
                self.trigger_play(1)

    @property
    def radio_station(self):
        if not self.is_coordinator:
            logger.debug("forwarding radio_station getter to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            return self.speaker_zone_coordinator.radio_station
        return self._radio_station

    @radio_station.setter
    def radio_station(self, value):
        if self._radio_station == value:
            return
        self._radio_station = value
        self.dirty_property('radio_station')

    @property
    def radio_show(self):
        if not self.is_coordinator:
            logger.debug("forwarding radio_show getter to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            return self.speaker_zone_coordinator.radio_show
        return self._radio_show

    @radio_show.setter
    def radio_show(self, value):
        if self._radio_show == value:
            return
        self._radio_show = value
        self.dirty_property('radio_show')

    @property
    def track_album_art(self):
        if not self.is_coordinator:
            logger.debug("forwarding track_album_art getter to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            return self.speaker_zone_coordinator.track_album_art
        return self._track_album_art

    @track_album_art.setter
    def track_album_art(self, value):
        if self._track_album_art == value:
            return
        self._track_album_art = value
        self.dirty_property('track_album_art')

    @property
    def track_title(self):
        if not self.is_coordinator:
            logger.debug("forwarding track_title getter to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            return self.speaker_zone_coordinator.track_title
        if not self._track_title:
            return ''
        return self._track_title

    @track_title.setter
    def track_title(self, value):
        if self._track_title == value:
            return
        self._track_title = value
        self.dirty_property('track_title')

    @property
    def track_artist(self):
        if not self.is_coordinator:
            logger.debug("forwarding track_artist getter to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            return self.speaker_zone_coordinator.track_artist
        if not self._track_artist:
            return ''
        return self._track_artist

    @track_artist.setter
    def track_artist(self, value):
        if self._track_artist == value:
            return
        self._track_artist = value
        self.dirty_property('track_artist')

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

        self.dirty_property('max_volume')

    @property
    def alarms(self):
        return self._alarms

    @alarms.setter
    def alarms(self, value):
        if value != self._alarms:
            self._alarms = value
            self.dirty_property('alarms')

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
            self._alarms = ''

    # ---------------------------------------------------------------------------------
    #
    # FUNCTIONS
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
        if not self.is_coordinator:
            logger.debug("forwarding next command to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            self.speaker_zone_coordinator.next()
        else:
            self.soco.next()

    def previous(self):
        if not self.is_coordinator:
            logger.debug("forwarding previous command to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            self.speaker_zone_coordinator.previous()
        else:
            self.soco.previous()

    def seek(self, timestamp):
        if not self.is_coordinator:
            logger.debug("forwarding seek command to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            self.speaker_zone_coordinator.seek(timestamp)
        else:
            self.soco.seek(timestamp)

    def track_info(self):
        if not self.is_coordinator:
            logger.debug("forwarding track_info command to coordinator with uid {uid}".
                         format(uid=self.speaker_zone_coordinator.uid))
            track_info = self.speaker_zone_coordinator.soco.get_current_track_info()
            self.speaker_zone_coordinator.track_position = track_info['position']
            self.speaker_zone_coordinator.playlist_position = int(track_info['playlist_position'])
        else:
            track_info = self.soco.get_current_track_info()
            self.track_position = track_info['position']
            self.playlist_position = int(track_info['playlist_position'])

    def play_uri(self, uri, metadata=None):
        if not self.is_coordinator:
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
                'playmode': self.playmode,
                'alarms': self.alarms
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

    def send(self):
        dirty_values = {}
        for prop in self._dirty_properties:
            value = getattr(self, prop)
            dirty_values[prop] = value

        if len(dirty_values) == 0:
            return

        #always add the uid
        dirty_values['uid'] = self.uid

        data = json.dumps(self, default=lambda o: dirty_values, sort_keys=True, ensure_ascii=False, indent=4,
                          separators=(',', ': '))
        udp_broker.UdpBroker.udp_send(data)

        #empty list
        del self._dirty_properties[:]

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
            for speaker in self._additional_zone_members:
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
            if self.sub_zone_group is None or self.sub_zone_group.time_left == 0:
                self._sub_zone_group = self.soco.zoneGroupTopology.subscribe(None, True, event_queue)

            if self.sub_av_transport is None or self.sub_av_transport.time_left == 0:
                self._sub_av_transport = self.soco.avTransport.subscribe(None, True, event_queue)

            if self.sub_rendering_control is None or self.sub_rendering_control.time_left == 0:
                self._sub_rendering_control = self.soco.renderingControl.subscribe(None, True, event_queue)

            if self.sub_alarm is None or self.sub_alarm.time_left == 0:
                self._sub_alarm = self.soco.alarmClock.subscribe(None, True, event_queue)

        except Exception as err:
            logger.exception(err)

    def get_alarms(self):
        """
        Gets all alarms for the speaker
        :return:
        """
        values = alarms.get_alarms(self.soco)
        alarm_dict = {}
        for alarm in values:
            if alarm.zone.uid.lower() != self.uid.lower():
                continue
            dict = SonosSpeaker.alarm_to_dict(alarm)
            alarm_dict[alarm._alarm_id] = dict
        self.alarms = alarm_dict

    @staticmethod
    def alarm_to_dict(alarm):
        return {
            'Enabled': alarm.enabled,
            'Duration': str(alarm.duration),
            'PlayMode': alarm.play_mode,
            'Volume': alarm.volume,
            'Recurrence': alarm.recurrence,
            'StartTime': str(alarm.start_time),
            'IncludedLinkZones': alarm.include_linked_zones
            #'ProgramUri': alarm.program_uri,
            #'ProgramMetadata': alarm.program_metadata,
            #'Uid': alarm.zone.uid
        }

    def _play_tts_thread(self, tts, volume, smb_url, local_share, language, quota):
        try:
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

    def dirty_property(self, prop):
        if prop not in self._dirty_properties:
            self._dirty_properties.append(prop)

    led = property(get_led, set_led)
    bass = property(get_bass, set_bass)
    treble = property(get_treble, set_treble)
    loudness = property(get_loudness, set_loudness)
    volume = property(get_volume, set_volume)
    mute = property(get_mute, set_mute)
    playmode = property(get_playmode, set_playmode)