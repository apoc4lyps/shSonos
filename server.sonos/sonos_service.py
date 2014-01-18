# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from xml.dom import minidom
from udp_broker import UdpBroker

__author__ = 'pfischi'

from collections import namedtuple
import threading
from types import MethodType
from xml.sax.saxutils import escape
import requests
from core import SoCo
import exceptions
from utils import really_unicode, really_utf8, prettify
import socket
import select
import definitions
import re
import logging
from time import sleep
from http.client import HTTPConnection

try:
    import xml.etree.cElementTree as XML
except ImportError:
    import xml.etree.ElementTree as XML

log = logging.getLogger(__name__)
Argument = namedtuple('Argument', 'name, vartype')
Action = namedtuple('Action', 'name, in_args, out_args')

#import sys
#sys.path.append('/usr/smarthome/plugins/sonos/server/pycharm-debug-py3k.egg')
#import pydevd


class SonosSpeaker():
    def __init__(self):
        self.uid = ''
        self.ip = ''
        self.model = ''
        self.zone_name = ''
        self.zone_icon = ''
        self.serial_number = ''
        self.software_version = ''
        self.hardware_version = ''
        self.mac_address = ''
        self.id = None
        self.status = 0
        self.subscrition = ''

    def __dir__(self):
        return ['uid', 'ip', 'model', 'zone_name', 'zone_icon', 'serial_number', 'software_version',
                'hardware_version', 'mac_address', 'id', 'status']


class SonosService():
    def __init__(self, host, port):

        self.udp_broker = UdpBroker()
        self.host = host
        self.port = port
        self.speakers = {}

        self._sock = socket.socket(
            socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self._sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        threading.Thread(target=self.get_speakers_periodically).start()

    def get_speakers_periodically(self):

        events = ['/MediaRenderer/RenderingControl/Event', '/DeviceProperties/Event']
        sleep_scan = 10 #in seconds
        max_sleep_count = 10 #new devices will always be deep scanned, old speaker every 10 loops
        deep_scan_count = 0

        while 1:

            print('scan devices ...')
            #find all (new and old speaker)
            new_speakers = self.get_speakers()

            if not new_speakers:
                #no speakers found, delete our list
                self.speakers = {}
                deep_scan_count = 0
            else:
                "find any newly added speaker"
                new_uids = set(new_speakers) - set(self.speakers)

            #do a deep scn for all new devices
            for uid in new_uids:
                print('new speaker: {} -- adding to list'.format(uid))
                #add the new speaker to our main list
                speaker = self.get_speaker_info(new_speakers[uid])
                self.speakers[speaker.uid] = speaker

                for event in events:
                    self.subscribe_speaker_event(speaker, event, self.host, self.port, sleep_scan * max_sleep_count * 2)

            #find all offline speaker
            offline_uids = set(self.speakers) - set(new_speakers)

            for u in offline_uids:
                print("offline speaker: {} -- removing from list".format(u))

            if deep_scan_count == max_sleep_count:
                print("Performing deep scan for speakers ...")

                for uid, speaker in self.speakers.items():
                    deep_scan_count = 0
                    speaker = self.get_speaker_info(self.speakers[speaker.uid])
                    #re-subscribe

                    for event in events:
                        self.unsubscribe_speaker_event(speaker, event, speaker.subscription, self.host, self.port)
                        self.subscribe_speaker_event(speaker, event, self.host, self.port,
                                                     sleep_scan * max_sleep_count * 2)
                    self.speakers[speaker.uid] = speaker

            deep_scan_count += 1

            sleep(sleep_scan)

    def get_soco(self, uid):
        speaker = self.speakers[uid.lower()]
        if speaker:
            return SoCo(speaker.ip)
        return None

    def get_speakers(self):
        """ Get a list of ips for Sonos devices that can be controlled """
        speakers = {}
        self._sock.sendto(really_utf8(definitions.PLAYER_SEARCH), (definitions.MCAST_GRP, definitions.MCAST_PORT))

        while True:
            response, _, _ = select.select([self._sock], [], [], 1)
            if response:
                data, addr = self._sock.recvfrom(2048)
                # Look for the model in parentheses in a line like this
                # SERVER: Linux UPnP/1.0 Sonos/22.0-65180 (ZPS5)
                searchmodel = re.search(definitions.model_pattern, data)
                searchuid = re.search(definitions.uid_pattern, data)
                try:
                    model = really_unicode(searchmodel.group(1))
                    uid = really_unicode(searchuid.group(1))
                except AttributeError:
                    model = None
                    uid = None

                # BR100 = Sonos Bridge,        ZPS3 = Zone Player 3
                # ZP120 = Zone Player Amp 120, ZPS5 = Zone Player 5
                # ZP90  = Sonos Connect,       ZPS1 = Zone Player 1
                # If it's the bridge, then it's not a speaker and shouldn't
                # be returned
                if (model and model != "BR100"):
                    speaker = SonosSpeaker()
                    speaker.uid = uid.lower()
                    speaker.ip = addr[0]
                    speaker.model = model
                    speakers[speaker.uid] = speaker
            else:
                break
        return speakers

    def get_speaker_info(self, speaker):

        """ Get information about the Sonos speaker.
        Returns:
        Information about the Sonos speaker, such as the UID, MAC Address, and
        Zone Name.

        """
        response = requests.get('http://' + speaker.ip + ':1400/status/zp')
        dom = XML.fromstring(response.content)

        print(response.text)
        if dom.findtext('.//ZoneName') is not None:
            speaker.zone_name = dom.findtext('.//ZoneName')
            speaker.zone_icon = dom.findtext('.//ZoneIcon')
            speaker.uid = dom.findtext('.//LocalUID').lower()
            speaker.serial_number = dom.findtext('.//SerialNumber')
            speaker.software_version = dom.findtext('.//SoftwareVersion')
            speaker.hardware_version = dom.findtext('.//HardwareVersion')
            speaker.mac_address = dom.findtext('.//MACAddress')
            return speaker

    @staticmethod
    def subscribe_speaker_event(speaker, event, host, port, timeout):

        print("speaker {} (ip {}): registering event '{}' to: {}:{}".format(speaker.uid, speaker.ip, event, host,
                                                                            port))

        headers = {'CALLBACK': '<http://{}:{}>'.format(host, port), 'NT': 'upnp:event',
                   'TIMEOUT': 'Second-{}'.format(timeout)}
        conn = HTTPConnection("{}:1400".format(speaker.ip))
        conn.request("SUBSCRIBE", "{}".format(event), "", headers)

        response = conn.getresponse()
        speaker.subscription = response.headers['SID']
        conn.close()

    @staticmethod
    def unsubscribe_speaker_event(speaker, event, sid, host, port):

        print("speaker {} (ip {}): un-registering event '{}' from: {}:{}".format(speaker.uid, speaker.ip, event,
                                                                                 host, port))

        headers = {'SID': '{}'.format(sid)}
        conn = HTTPConnection("{}:1400".format(speaker.ip))
        conn.request("UNSUBSCRIBE", "{}".format(event), "", headers)

        response = conn.getresponse()
        print(response)
        conn.close()

    def response_parser(self, sid, data):

        """
        <event xmlns="urn:schemas-upnp-org:metadata-1-0/rcs/">
	        <instanceid val="0">
		        <volume channel="master" val="27"/>
		        <volume channel="lf" val="100"/>
		        <volume channel="rf" val="100"/>
		        <mute channel="master" val="0"/>
		        <mute channel="lf" val="0"/>
		        <mute channel="rf" val="0"/>
		        <bass val="0"/><treble val="0"/>
		        <loudness channel="master" val="1"/>
		        <outputfixed val="0"/><headphoneconnected val="0"/>
		        <speakersize val="5"/><subgain val="0"/>
		        <subcrossover val="0"/>
		        <subpolarity val="0"/>
		        <subenabled val="1"/>
		        <presetnamelist val="factorydefaults"/>
	        </instanceid>
        </event>"""

        try:

            response_list = []
            sid_uid = None

            for uid, speaker in self.speakers.items():
                if speaker.subscription == sid:
                    sid_uid = uid
                    break

            if not sid_uid:
                print("No uid found for subscription '{}'".format(sid))
                return None

            print("speaker '{} found for subscription '{}".format(sid_uid, sid))

            dom = minidom.parseString(data).documentElement

            #           pydevd.settrace('192.168.178.44', port=12000, stdoutToServer=True, stderrToServer=True)

            node = dom.getElementsByTagName(
                'LastChange')  #response for subscription '/MediaRenderer/RenderingControl/Event'
            if node:
                #<LastChange>
                #   ..... nodeValue = embedded xml node
                #</LstChange>
                response_list.extend(self.response_lastchange(sid_uid, node[0].firstChild.nodeValue))

            #udp wants a string
            data = ''
            for entry in response_list:
                data = "{}\n{}".format(data, entry)

            self.udp_broker.udp_send(data)

        except Exception as err:
            print(err)
            return None

    def response_lastchange(self, uid, node_data):

        dom = minidom.parseString(node_data).documentElement
        #changed value in smarthome.py response syntax, change this to your preference
        #e.g. speaker/<uid>/volume/<value>
        changed_values = []
        #       pydevd.settrace('192.168.178.44', port=12000, stdoutToServer=True, stderrToServer=True)

        #getting master volume for speaker <volume channel="master" val="27"/><
        volume_nodes = dom.getElementsByTagName('Volume')

        for volume_node in volume_nodes:
            if volume_node.hasAttribute("channel"):
                if volume_node.getAttribute('channel').lower() == 'master':
                    volume = volume_node.getAttribute('val')

                    changed_values.append("speaker/{}/volume/{}".format(uid, volume))

        volume_nodes = dom.getElementsByTagName('Mute')

        for volume_node in volume_nodes:
            if volume_node.hasAttribute("channel"):
                if volume_node.getAttribute('channel').lower() == 'master':
                    volume = volume_node.getAttribute('val')

                    changed_values.append("speaker/{}/mute/{}".format(uid, volume))

        return changed_values


class Service(object):
    """ An class representing a UPnP service. The base class for all Sonos
    Service classes

    This class has a dynamic method dispatcher. Calls to methods which are not
    explicitly defined here are dispatched automatically to the service action
    with the same name.

    """
    soap_body_template = "".join([
        '<?xml version="1.0"?>',
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"',
        ' s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">',
        '<s:Body>',
        '<u:{action} xmlns:u="urn:schemas-upnp-org:service:',
        '{service_type}:{version}">',
        '{arguments}',
        '</u:{action}>',
        '</s:Body>',
        '</s:Envelope>'])  # noqa PEP8

    def __init__(self, soco):
        self.soco = soco
        # Some defaults. Some or all these will need to be overridden
        # specifically in a sub-class. There is other information we could
        # record, but this will do for the moment. Info about a Sonos device is
        # available at <IP_address>/xml/device_description.xml in the
        # <service> tags
        self.service_type = self.__class__.__name__
        self.version = 1
        self.service_id = self.service_type
        self.base_url = 'http://{}:1400'.format(self.soco.speaker_ip)
        self.control_url = '/{}/Control'.format(self.service_type)
        # Service control protocol description
        self.scpd_url = '/xml/{}{}.xml'.format(self.service_type, self.version)
        log.debug(
            "Created service %s, ver %s, id %s, base_url %s, control_url %s",
            self.service_type, self.version, self.service_id, self.base_url,
            self.control_url)

        # From table 3.3 in
        # http://upnp.org/specs/arch/UPnP-arch-DeviceArchitecture-v1.1.pdf
        # This list may not be complete, but should be good enough to be going
        # on with.  Error codes between 700-799 are defined for particular
        # services, and may be overriden in subclasses. Error codes >800
        # are generally SONOS specific. NB It may well be that SONOS does not
        # use some of these error codes.

        self.UPNP_ERRORS = {
            400: 'Bad Request',
            401: 'Invalid Action',
            402: 'Invalid Args',
            404: 'Invalid Var',
            412: 'Precondition Failed',
            501: 'Action Failed',
            600: 'Argument Value Invalid',
            601: 'Argument Value Out of Range',
            602: 'Optional Action Not Implemented',
            603: 'Out Of Memory',
            604: 'Human Intervention Required',
            605: 'String Argument Too Long',
            606: 'Action Not Authorized',
            607: 'Signature Failure',
            608: 'Signature Missing',
            609: 'Not Encrypted',
            610: 'Invalid Sequence',
            611: 'Invalid Control URL',
            612: 'No Such Session',
        }

    def __getattr__(self, action):
        """ A Python magic method which is called whenever an undefined method
        is invoked on the instance.

        The name of the unknown method called is passed as a parameter, and the
        return value is the callable to be invoked.

        """

        # Define a function to be invoked as the method, which calls
        # send_command. It should take 0 or one args
        def _dispatcher(self, *args):
            arg_number = len(args)
            if arg_number > 1:
                raise TypeError(
                    "TypeError: {} takes 0 or 1 argument(s) ({} given)"
                    .format(action, arg_number))
            elif arg_number == 0:
                args = None
            else:
                args = args[0]

            return self.send_command(action, args)

        # rename the function so it appears to be the called method. We
        # probably don't need this, but it doesn't harm
        _dispatcher.__name__ = action

        # _dispatcher is now an unbound menthod, but we need a bound method.
        # This turns an unbound method into a bound method (i.e. one that
        # takes self - an instance of the class - as the first parameter)
        method = MethodType(_dispatcher, self)

        # Now we have a bound method, we cache it on this instance, so that
        # next time we don't have to go through this again
        setattr(self, action, method)
        log.debug("Dispatching method %s", action)

        # return our new bound method, which will be called by Python
        return method

    def wrap_arguments(self, args=None):
        """ Wrap a list of tuples in xml ready to pass into a SOAP request.

        args is a list of (name, value) tuples specifying the name of each
        argument and its value, eg [('InstanceID', 0), ('Speed', 1)]. The value
        can be a string or something with a string representation. The
        arguments are escaped and wrapped in <name> and <value> tags.

        ">>> from soco import SoCo
        ">>> device = SoCo('192.168.1.101')
        ">>> s = Service(device)
        ">>> s.wrap_arguments([('InstanceID', 0), ('Speed', 1)])
        <InstanceID>0</InstanceID><Speed>1</Speed>'

        """
        if args is None:
            args = []
        l = ["<{name}>{value}</{name}>".format(
            name=name, value=escape(str(value), {'"': "&quot;"}))
             for name, value in args]
        xml = "".join(l)
        return xml

    def unwrap_arguments(self, xml_response):
        """ Extract arguments and their values from a SOAP response.

        Given an soap/xml response, return a dict of {argument_name, value)}
        items

        """

        # A UPnP SOAP response (including headers) looks like this:

        # HTTP/1.1 200 OK
        # CONTENT-LENGTH: bytes in body
        # CONTENT-TYPE: text/xml; charset="utf-8" DATE: when response was
        # generated
        # EXT:
        # SERVER: OS/version UPnP/1.0 product/version
        #
        # <?xml version="1.0"?>
        # <s:Envelope
        #   xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
        #   s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
        #   <s:Body>
        #       <u:actionNameResponse
        #           xmlns:u="urn:schemas-upnp-org:service:serviceType:v">
        #           <argumentName>out arg value</argumentName>
        #               ... other out args and their values go here, if any
        #       </u:actionNameResponse>
        #   </s:Body>
        # </s:Envelope>

        # Get all tags in order. Elementree (in python 2.x) seems to prefer to
        # be fed bytes, rather than unicode

        xml_response = xml_response.encode('utf-8')
        tree = XML.fromstring(xml_response)

        # Get the first child of the <Body> tag which will be
        # <{actionNameResponse}> (depends on what actionName is). Turn the
        # children of this into a {tagname, content} dict. XML unescaping
        # is carried out for us by elementree.
        action_response = tree.find(
            ".//{http://schemas.xmlsoap.org/soap/envelope/}Body")[0]
        return {i.tag: i.text or "" for i in action_response}

    def build_command(self, action, args=None):
        """ Build a SOAP request.

        Given the name of an action (a string as specified in the service
        description XML file) to be sent, and the relevant arguments as a list
        of (name, value) tuples, return a tuple containing the POST headers (as
        a dict) and a string containing the relevant SOAP body. Does not set
        content-length, or host headers, which are completed upon sending.

        """

        # A complete request should look something like this:

        # POST path of control URL HTTP/1.1
        # HOST: host of control URL:port of control URL
        # CONTENT-LENGTH: bytes in body
        # CONTENT-TYPE: text/xml; charset="utf-8"
        # SOAPACTION: "urn:schemas-upnp-org:service:serviceType:v#actionName"
        #
        # <?xml version="1.0"?>
        # <s:Envelope
        #   xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
        #   s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
        #   <s:Body>
        #       <u:actionName
        #           xmlns:u="urn:schemas-upnp-org:service:serviceType:v">
        #           <argumentName>in arg value</argumentName>
        #           ... other in args and their values go here, if any
        #       </u:actionName>
        #   </s:Body>
        # </s:Envelope>

        arguments = self.wrap_arguments(args)
        body = self.soap_body_template.format(
            arguments=arguments, action=action, service_type=self.service_type,
            version=self.version)
        soap_action_template = \
            "urn:schemas-upnp-org:service:{service_type}:{version}#{action}"
        soap_action = soap_action_template.format(
            service_type=self.service_type, version=self.version,
            action=action)
        headers = {'Content-Type': 'text/xml; charset="utf-8"',
                   'SOAPACTION': soap_action}
        return (headers, body)

    def send_command(self, action, args=None):
        """ Send a command to a Sonos device.

        Given the name of an action (a string as specified in the service
        description XML file) to be sent, and the relevant arguments as a list
        of (name, value) tuples, send the command to the Sonos device. args
        can be emptyReturn
        a dict of {argument_name, value)} items or True on success. Raise
        an exception on failure.

        """

        headers, body = self.build_command(action, args)
        log.info("Sending %s %s to %s", action, args, self.soco.speaker_ip)
        log.debug("Sending %s, %s", headers, prettify(body))
        response = requests.post(
            self.base_url + self.control_url, headers=headers, data=body)
        log.debug("Received %s, %s", response.headers, response.text)
        status = response.status_code
        if status == 200:
            # The response is good. Get the output params, and return them.
            # NB an empty dict is a valid result. It just means that no
            # params are returned.
            result = self.unwrap_arguments(response.text) or True
            log.info(
                "Received status %s from %s", status, self.soco.speaker_ip)
            return result
        elif status == 500:
            # Internal server error. UPnP requires this to be returned if the
            # device does not like the action for some reason. The returned
            # content will be a SOAP Fault. Parse it and raise an error.
            try:
                self.handle_upnp_error(response.text)
            except Exception as e:
                log.exception(e.message)
                raise
        else:
            # Something else has gone wrong. Probably a network error. Let
            # Requests handle it
            #raise Exception('OOPS')
            response.raise_for_status()

    def handle_upnp_error(self, xml_error):
        """ Disect a UPnP error, and raise an appropriate exception

        xml_error is a unicode string containing the body of the UPnP/SOAP
        Fault response. Raises an exception containing the error code

        """

        # An error code looks something like this:

        # HTTP/1.1 500 Internal Server Error
        # CONTENT-LENGTH: bytes in body
        # CONTENT-TYPE: text/xml; charset="utf-8"
        # DATE: when response was generated
        # EXT:
        # SERVER: OS/version UPnP/1.0 product/version

        # <?xml version="1.0"?>
        # <s:Envelope
        #   xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
        #   s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
        #   <s:Body>
        #       <s:Fault>
        #           <faultcode>s:Client</faultcode>
        #           <faultstring>UPnPError</faultstring>
        #           <detail>
        #               <UPnPError xmlns="urn:schemas-upnp-org:control-1-0">
        #                   <errorCode>error code</errorCode>
        #                   <errorDescription>error string</errorDescription>
        #               </UPnPError>
        #           </detail>
        #       </s:Fault>
        #   </s:Body>
        # </s:Envelope>
        #
        # All that matters for our purposes is the errorCode.
        # errorDescription is not required, and Sonos does not seem to use it.

        # NB need to encode unicode strings before passing to ElementTree
        xml_error = xml_error.encode('utf-8')
        error = XML.fromstring(xml_error)
        log.debug("Error %s", xml_error)
        error_code = error.findtext(
            './/{urn:schemas-upnp-org:control-1-0}errorCode')
        if error_code is not None:
            description = self.UPNP_ERRORS.get(int(error_code), '')
            raise exceptions.SonosUPnPException(
                message='UPnP Error {} received: {} from {}'.format(
                    error_code, description, self.soco.speaker_ip),
                error_code=error_code,
                error_description=description,
                error_xml=xml_error
            )
        else:
            # Unknown error, so just return the entire response
            log.error("Unknown error received from %s", self.soco.speaker_ip)
            raise exceptions.UnknownSonosException(xml_error)

    def iter_actions(self):
        """ Yield the service's actions with their in_arguments (ie parameters
        to pass to the action) and out_arguments (ie returned values).

        Each action is an Action namedtuple, consisting of action_name (a
        string), in_args (a list of Argument namedtuples consisting of name and
        argtype), and out_args (ditto), eg:

        Action(name='SetFormat',
            in_args=[Argument(name='DesiredTimeFormat', vartype='string'),
                     Argument(name='DesiredDateFormat', vartype='string')],
            out_args=[]) """

        # TODO: Provide for Allowed value list, Allowed value range,
        # default value
        ns = '{urn:schemas-upnp-org:service-1-0}'
        scpd_body = requests.get(self.base_url + self.scpd_url).text
        tree = XML.fromstring(scpd_body.encode('utf-8'))
        # parse the state variables to get the relevant variable types
        statevars = tree.iterfind('.//{}stateVariable'.format(ns))
        vartypes = {}
        for s in statevars:
            name = s.findtext('{}name'.format(ns))
            vartypes[name] = s.findtext('{}dataType'.format(ns))
            # find all the actions
        actions = tree.iterfind('.//{}action'.format(ns))
        for i in actions:
            action_name = i.findtext('{}name'.format(ns))
            args_iter = i.iterfind('.//{}argument'.format(ns))
            in_args = []
            out_args = []
            for a in args_iter:
                arg_name = a.findtext('{}name'.format(ns))
                direction = a.findtext('{}direction'.format(ns))
                related_variable = a.findtext(
                    '{}relatedStateVariable'.format(ns))
                vartype = vartypes[related_variable]
                if direction == "in":
                    in_args.append(Argument(arg_name, vartype))
                else:
                    out_args.append(Argument(arg_name, vartype))
            yield Action(action_name, in_args, out_args)


class AlarmClock(Service):
    """ Sonos alarm service, for setting and getting time and alarms. """

    def __init__(self, soco):
        super(AlarmClock, self).__init__(soco)


class MusicServices(Service):
    """ Sonos music services service, for functions related to 3rd party
    music services. """

    def __init__(self, soco):
        super(MusicServices, self).__init__(soco)


class DeviceProperties(Service):
    """ Sonos device properties service, for functions relating to zones,
    LED state, stereo pairs etc. """

    def __init__(self, soco):
        super(DeviceProperties, self).__init__(soco)


class SystemProperties(Service):
    """ Sonos system properties service, for functions relating to
    authentication etc """

    def __init__(self, soco):
        super(SystemProperties, self).__init__(soco)


class ZoneGroupTopology(Service):
    """ Sonos zone group topology service, for functions relating to network
    topology, diagnostics and updates. """

    def __init__(self, soco):
        super(ZoneGroupTopology, self).__init__(soco)


class GroupManagement(Service):
    """ Sonos group management service, for services relating to groups. """

    def __init__(self, soco):
        super(GroupManagement, self).__init__(soco)


class QPlay(Service):
    """ Sonos Tencent QPlay service (a Chinese music service) """

    def __init__(self, soco):
        super(QPlay, self).__init__(soco)


class ContentDirectory(Service):
    """ UPnP standard Content Directory service, for functions relating to
    browsing, searching and listing available music. """

    def __init__(self, soco):
        super(ContentDirectory, self).__init__(soco)
        self.control_url = "/MediaServer/ContentDirectory/Control"
        # For error codes, see table 2.7.16 in
        # http://upnp.org/specs/av/UPnP-av-ContentDirectory-v1-Service.pdf
        self.UPNP_ERRORS.update({
            701: 'No such object',
            702: 'Invalid CurrentTagValue',
            703: 'Invalid NewTagValue',
            704: 'Required tag',
            705: 'Read only tag',
            706: 'Parameter Mismatch',
            708: 'Unsupported or invalid search criteria',
            709: 'Unsupported or invalid sort criteria',
            710: 'No such container',
            711: 'Restricted object',
            712: 'Bad metadata',
            713: 'Restricted parent object',
            714: 'No such source resource',
            715: 'Resource access denied',
            716: 'Transfer busy',
            717: 'No such file transfer',
            718: 'No such destination resource',
            719: 'Destination resource access denied',
            720: 'Cannot process the request',
        })


class MS_ConnectionManager(Service):
    """ UPnP standard connection manager service for the media server."""

    def __init__(self, soco):
        super(MS_ConnectionManager, self).__init__(soco)
        self.service_type = "ConnectionManager"
        self.control_url = "/MediaServer/ConnectionManager/Control"


class RenderingControl(Service):
    """ UPnP standard redering control service, for functions relating to
    playback rendering, eg bass, treble, volume and EQ. """

    def __init__(self, soco):
        super(RenderingControl, self).__init__(soco)
        self.control_url = "/MediaRenderer/RenderingControl/Control"


class MR_ConnectionManager(Service):
    """ UPnP standard connection manager service for the media renderer."""

    def __init__(self, soco):
        super(MR_ConnectionManager, self).__init__(soco)
        self.service_type = "ConnectionManager"
        self.control_url = "/MediaRenderer/ConnectionManager/Control"


class AVTransport(Service):
    """ UPnP standard AV Transport service, for functions relating to
    transport management, eg play, stop, seek, playlists etc. """

    def __init__(self, soco):
        super(AVTransport, self).__init__(soco)
        self.control_url = "/MediaRenderer/AVTransport/Control"
        # For error codes, see
        # http://upnp.org/specs/av/UPnP-av-AVTransport-v1-Service.pdf
        self.UPNP_ERRORS.update({
            701: 'Transition not available',
            702: 'No contents',
            703: 'Read error',
            704: 'Format not supported for playback',
            705: 'Transport is locked',
            706: 'Write error',
            707: 'Media is protected or not writeable',
            708: 'Format not supported for recording',
            709: 'Media is full',
            710: 'Seek mode not supported',
            711: 'Illegal seek target',
            712: 'Play mode not supported',
            713: 'Record quality not supported',
            714: 'Illegal MIME-Type',
            715: 'Content "BUSY"',
            716: 'Resource Not found',
            717: 'Play speed not supported',
            718: 'Invalid InstanceID',
            737: 'No DNS Server',
            738: 'Bad Domain Name',
            739: 'Server Error',
        })


class Queue(Service):
    """ Sonos queue service, for functions relating to queue management, saving
    queues etc. """

    def __init__(self, soco):
        super(Queue, self).__init__(soco)
        self.control_url = "/MediaRenderer/Queue/Control"


class GroupRenderingControl(Service):
    """ Sonos group rendering control service, for functions relating to
    group volume etc. """

    def __init__(self, soco):
        super(GroupRenderingControl, self).__init__(soco)
        self.control_url = "/MediaRenderer/GroupRenderingControl/Control"






